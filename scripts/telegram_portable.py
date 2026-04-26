#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

DEFAULT_TELEGRAM_LINUX_URL = "https://telegram.org/dl/desktop/linux"
DEFAULT_OUTPUT_ROOT = Path.home()
DEFAULT_RUNTIME_CACHE_DIR = Path.home() / ".cache" / "site-control-kit" / "telegram-portable-runtime"
PROFILE_PREFIX = "TelegramPortable-"


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _print_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def sanitize_profile_name(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("profile name is required")
    raw = re.sub(rf"^{re.escape(PROFILE_PREFIX)}", "", raw, flags=re.I)
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-._")
    if not normalized:
        raise ValueError(f"unable to derive safe profile name from: {value}")
    return normalized[:80]


def profile_dir_for(output_root: Path, profile_name: str) -> Path:
    safe_name = sanitize_profile_name(profile_name)
    return output_root.expanduser().resolve() / f"{PROFILE_PREFIX}{safe_name}"


def _validated_member_destination(root_dir: Path, member_name: str) -> Path:
    destination = (root_dir / member_name).resolve()
    root_resolved = root_dir.resolve()
    if os.path.commonpath([str(root_resolved), str(destination)]) != str(root_resolved):
        raise ValueError(f"archive contains unsafe path: {member_name}")
    return destination


def _zip_member_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def safe_extract_zip(archive_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive_path) as zf:
        members = zf.infolist()
        if not members:
            raise ValueError(f"zip archive is empty: {archive_path}")
        for member in members:
            name = member.filename
            if not name:
                continue
            if Path(name).is_absolute():
                raise ValueError(f"zip archive contains absolute path: {name}")
            if _zip_member_is_symlink(member):
                raise ValueError(f"zip archive contains unsupported symlink entry: {name}")
            _validated_member_destination(destination, name)
        zf.extractall(destination)


def safe_extract_tar(archive_path: Path, destination: Path) -> None:
    with tarfile.open(archive_path, mode="r:*") as tf:
        members = tf.getmembers()
        if not members:
            raise ValueError(f"tar archive is empty: {archive_path}")
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"tar archive contains unsupported link entry: {member.name}")
            _validated_member_destination(destination, member.name)
        tf.extractall(destination, filter="data")


def discover_tdata_dir(extracted_root: Path) -> Path:
    if (extracted_root / "key_datas").is_file():
        return extracted_root

    candidates: list[tuple[int, int, str, Path]] = []
    for key_datas_path in extracted_root.rglob("key_datas"):
        if not key_datas_path.is_file():
            continue
        parent = key_datas_path.parent
        try:
            depth = len(parent.relative_to(extracted_root).parts)
        except ValueError:
            continue
        named_tdata = 0 if parent.name == "tdata" else 1
        candidates.append((named_tdata, depth, str(parent), parent))

    if not candidates:
        raise ValueError(f"tdata directory with key_datas was not found in zip: {extracted_root}")

    candidates.sort()
    return candidates[0][3]


def discover_runtime_dir(extracted_root: Path) -> Path:
    direct = extracted_root / "Telegram"
    if direct.is_dir() and (direct / "Telegram").is_file():
        return direct

    candidates: list[tuple[int, str, Path]] = []
    for binary_path in extracted_root.rglob("Telegram"):
        if not binary_path.is_file():
            continue
        parent = binary_path.parent
        try:
            depth = len(parent.relative_to(extracted_root).parts)
        except ValueError:
            continue
        candidates.append((depth, str(parent), parent))

    if not candidates:
        raise ValueError(f"Telegram runtime directory was not found in archive: {extracted_root}")

    candidates.sort()
    return candidates[0][2]


def clear_directory_contents(directory: Path) -> None:
    if not directory.exists():
        return
    for child in directory.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()


def copy_tree_contents(source_dir: Path, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    for child in source_dir.iterdir():
        destination = target_dir / child.name
        if child.is_dir() and not child.is_symlink():
            shutil.copytree(child, destination)
        else:
            shutil.copy2(child, destination)


def ensure_executable(path: Path) -> None:
    if not path.exists():
        return
    current_mode = path.stat().st_mode
    path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "site-control-kit telegram portable helper"})
    with urlopen(request, timeout=300) as response, destination.open("wb") as fh:
        shutil.copyfileobj(response, fh)


def ensure_runtime_cache(
    *,
    runtime_cache_dir: Path,
    runtime_archive: str | None,
    download_url: str,
    refresh_runtime: bool,
) -> dict[str, Any]:
    runtime_cache_dir = runtime_cache_dir.expanduser().resolve()
    cached_binary = runtime_cache_dir / "Telegram"
    if cached_binary.is_file() and not refresh_runtime:
        return {
            "runtime_dir": str(runtime_cache_dir),
            "source": "cache",
        }

    archive_source = "download"
    with tempfile.TemporaryDirectory(prefix="telegram-portable-runtime.") as tmpdir:
        temp_root = Path(tmpdir)
        archive_path = temp_root / "telegram-runtime.tar.xz"
        if runtime_archive:
            source_path = Path(runtime_archive).expanduser().resolve()
            if not source_path.is_file():
                raise FileNotFoundError(f"runtime archive not found: {source_path}")
            shutil.copy2(source_path, archive_path)
            archive_source = "archive"
        else:
            download_file(download_url, archive_path)

        extracted_root = temp_root / "runtime"
        extracted_root.mkdir(parents=True, exist_ok=True)
        safe_extract_tar(archive_path, extracted_root)
        runtime_source_dir = discover_runtime_dir(extracted_root)

        runtime_cache_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(runtime_cache_dir)
        copy_tree_contents(runtime_source_dir, runtime_cache_dir)
        ensure_executable(runtime_cache_dir / "Telegram")
        ensure_executable(runtime_cache_dir / "Updater")

    return {
        "runtime_dir": str(runtime_cache_dir),
        "source": archive_source,
    }


def _read_proc_cmdline_args(pid: str) -> list[str]:
    cmdline_path = Path("/proc") / pid / "cmdline"
    try:
        raw = cmdline_path.read_bytes()
    except OSError:
        return []
    return [part.decode("utf-8", errors="ignore") for part in raw.split(b"\0") if part]


def find_running_pids(binary_path: Path) -> list[int]:
    binary_path = binary_path.expanduser().resolve()
    proc_root = Path("/proc")
    if not proc_root.exists():
        return []

    pids: list[int] = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = entry.name
        exe_path = entry / "exe"
        try:
            if exe_path.exists() and exe_path.resolve() == binary_path:
                pids.append(int(pid))
                continue
        except OSError:
            pass

        cmdline_args = _read_proc_cmdline_args(pid)
        if any(arg == str(binary_path) for arg in cmdline_args):
            pids.append(int(pid))
    return sorted(set(pids))


def write_profile_metadata(target_dir: Path, payload: dict[str, Any]) -> Path:
    metadata_path = target_dir / "portable-profile.json"
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata_path


def launch_portable(target_dir: Path) -> dict[str, Any]:
    binary_path = target_dir / "Telegram"
    if not binary_path.is_file():
        raise FileNotFoundError(f"Telegram binary not found: {binary_path}")

    log_path = target_dir / "portable-launch.log"
    existing_pids = find_running_pids(binary_path)
    if existing_pids:
        return {
            "status": "already_running",
            "pids": existing_pids,
            "log_path": str(log_path),
        }

    with log_path.open("ab") as log_fh:
        process = subprocess.Popen(
            [str(binary_path)],
            cwd=str(target_dir),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    return {
        "status": "started",
        "pid": int(process.pid),
        "log_path": str(log_path),
    }


def import_zip(
    *,
    zip_path: Path,
    profile_name: str,
    output_root: Path,
    runtime_cache_dir: Path,
    runtime_archive: str | None,
    download_url: str,
    refresh_runtime: bool,
    launch_after_import: bool,
) -> dict[str, Any]:
    zip_path = zip_path.expanduser().resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(f"zip archive not found: {zip_path}")

    safe_profile_name = sanitize_profile_name(profile_name)
    target_dir = profile_dir_for(output_root, safe_profile_name)
    target_existed = target_dir.exists()
    if target_existed:
        running_pids = find_running_pids(target_dir / "Telegram")
        if running_pids:
            raise RuntimeError(
                f"profile {safe_profile_name} is already running via {target_dir}; close it before replacing the tdata"
            )

    runtime_info = ensure_runtime_cache(
        runtime_cache_dir=runtime_cache_dir,
        runtime_archive=runtime_archive,
        download_url=download_url,
        refresh_runtime=refresh_runtime,
    )

    with tempfile.TemporaryDirectory(prefix="telegram-portable-import.") as tmpdir:
        temp_root = Path(tmpdir)
        extracted_zip_root = temp_root / "zip"
        extracted_zip_root.mkdir(parents=True, exist_ok=True)
        safe_extract_zip(zip_path, extracted_zip_root)
        tdata_source_dir = discover_tdata_dir(extracted_zip_root)

        target_dir.mkdir(parents=True, exist_ok=True)
        clear_directory_contents(target_dir)
        copy_tree_contents(Path(runtime_info["runtime_dir"]), target_dir)
        ensure_executable(target_dir / "Telegram")
        ensure_executable(target_dir / "Updater")

        portable_root = target_dir / "TelegramForcePortable"
        portable_root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(tdata_source_dir, portable_root / "tdata")

    metadata = {
        "status": "completed",
        "imported_at": now_utc(),
        "profile_name": safe_profile_name,
        "profile_dir": str(target_dir),
        "binary_path": str(target_dir / "Telegram"),
        "portable_dir": str(target_dir / "TelegramForcePortable"),
        "tdata_dir": str(target_dir / "TelegramForcePortable" / "tdata"),
        "source_zip": str(zip_path),
        "runtime": {
            "cache_dir": str(Path(runtime_info["runtime_dir"])),
            "source": str(runtime_info["source"]),
        },
    }
    metadata_path = write_profile_metadata(target_dir, metadata)

    launch_result = {"status": "not_requested"}
    if launch_after_import:
        launch_result = launch_portable(target_dir)

    return {
        "status": "completed",
        "mode": "updated" if target_existed else "created",
        "profile_name": safe_profile_name,
        "profile_dir": str(target_dir),
        "binary_path": str(target_dir / "Telegram"),
        "portable_dir": str(target_dir / "TelegramForcePortable"),
        "tdata_dir": str(target_dir / "TelegramForcePortable" / "tdata"),
        "source_zip": str(zip_path),
        "metadata_path": str(metadata_path),
        "runtime": metadata["runtime"],
        "launch": launch_result,
    }


def command_import_zip(args: argparse.Namespace) -> int:
    profile_name = args.profile_name or Path(args.zip).stem
    payload = import_zip(
        zip_path=Path(args.zip),
        profile_name=profile_name,
        output_root=Path(args.output_root),
        runtime_cache_dir=Path(args.runtime_cache_dir),
        runtime_archive=args.runtime_archive,
        download_url=args.download_url,
        refresh_runtime=bool(args.refresh_runtime),
        launch_after_import=bool(args.launch),
    )
    _print_json(payload)
    return 0


def command_launch(args: argparse.Namespace) -> int:
    target_dir = profile_dir_for(Path(args.output_root), args.profile_name)
    payload = {
        "status": "completed",
        "profile_name": sanitize_profile_name(args.profile_name),
        "profile_dir": str(target_dir),
        "binary_path": str(target_dir / "Telegram"),
        "launch": launch_portable(target_dir),
    }
    _print_json(payload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Telegram Desktop portable helper for Linux profiles backed by TelegramForcePortable."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser(
        "import-zip",
        help="Import a tdata zip into a dedicated Linux Telegram portable profile and optionally launch it.",
    )
    import_parser.add_argument("--zip", required=True, help="Path to the zip archive that contains tdata.")
    import_parser.add_argument("--profile-name", help="Readable profile suffix. Defaults to the zip filename stem.")
    import_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    import_parser.add_argument("--runtime-cache-dir", default=str(DEFAULT_RUNTIME_CACHE_DIR))
    import_parser.add_argument("--runtime-archive", help="Optional local Telegram Desktop archive (.tar.xz/.tar.gz) for offline setup.")
    import_parser.add_argument("--download-url", default=DEFAULT_TELEGRAM_LINUX_URL)
    import_parser.add_argument("--refresh-runtime", action="store_true", help="Re-download or re-import the runtime into the cache.")
    import_parser.add_argument("--launch", action="store_true", help="Launch the imported portable profile after extracting it.")
    import_parser.set_defaults(func=command_import_zip)

    launch_parser = subparsers.add_parser("launch", help="Launch an existing Telegram portable profile.")
    launch_parser.add_argument("--profile-name", required=True)
    launch_parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT))
    launch_parser.set_defaults(func=command_launch)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
