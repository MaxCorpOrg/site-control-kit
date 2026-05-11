from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..models import PortableProfile, PortableProfileRemovalResult, PortableProfileStatus


TDATA_SIGNATURE_FILES = ("key_datas", "D877F783D5D3EF8Cs", "D877F783D5D3EF8C/maps")
WORKSPACE_LINK_FILENAME = ".portable-link.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slugify(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-zа-я0-9._-]+", "-", text, flags=re.I)
    text = text.strip("._-")
    return text or "portable-profile"


def _portable_dir_slug(value: str) -> str:
    return _slugify(value).replace("_", "-")


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _chmod_best_effort(path, 0o600)


def _read_workspace_link_target(path: Path) -> Path | None:
    payload = _read_json(path / WORKSPACE_LINK_FILENAME)
    raw = str(payload.get("target") or "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def _write_workspace_link(path: Path, target: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _chmod_best_effort(path, 0o700)
    _write_json(path / WORKSPACE_LINK_FILENAME, {"target": str(target.resolve())})


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _tdata_dir_looks_valid(path: Path) -> bool:
    if not path.is_dir():
        return False
    return any((path / relative).exists() for relative in TDATA_SIGNATURE_FILES) or (path / "key_datas").exists()


def _replace_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.copytree(source, target)
    _chmod_best_effort(target, 0o700)


def _extract_tdata_zip(archive: Path, target_dir: Path) -> None:
    extract_root = target_dir.parent / f".extract_{archive.stem}"
    if extract_root.exists():
        shutil.rmtree(extract_root, ignore_errors=True)
    extract_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(archive) as handle:
            handle.extractall(extract_root)
        candidates: list[Path] = []
        if (extract_root / "tdata").is_dir():
            candidates.append(extract_root / "tdata")
        for item in extract_root.iterdir():
            if item.is_dir() and (item / "tdata").is_dir():
                candidates.append(item / "tdata")
        if not candidates:
            raise RuntimeError(f"В ZIP не найден каталог tdata: {archive}")
        shutil.copytree(candidates[0], target_dir)
        _chmod_best_effort(target_dir, 0o700)
    finally:
        shutil.rmtree(extract_root, ignore_errors=True)


def _detect_import_payload(source: Path) -> tuple[str, Path, Path | None]:
    candidate = source.expanduser().resolve()
    if candidate.is_file() and candidate.suffix.lower() == ".zip":
        return ("zip", candidate, None)
    if candidate.is_dir():
        zip_candidates = sorted(candidate.glob("tdata-*.zip"), key=lambda item: item.stat().st_mtime, reverse=True)
        if zip_candidates:
            return ("zip", zip_candidates[0], None)
        extracted = sorted(
            (item for item in candidate.iterdir() if item.is_dir() and item.name.startswith("tdata-") and (item / "tdata").is_dir()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        if extracted:
            return ("folder", extracted[0], extracted[0] / "tdata")
        if (candidate / "tdata").is_dir():
            return ("tdata", candidate, candidate / "tdata")
        if candidate.name == "tdata" and candidate.is_dir():
            return ("tdata", candidate, candidate)
    raise RuntimeError(f"Не удалось распознать portable source: {candidate}")


def _normalize_adopt_profile_root(source: Path) -> tuple[Path, Path]:
    root = source.expanduser().resolve()
    if (root / "portable-profile.json").is_file():
        portable_dir = _portable_dir_from_metadata(root / "portable-profile.json") or (root / "TelegramForcePortable")
        tdata_dir = _tdata_dir_from_metadata(root / "portable-profile.json") or (portable_dir / "tdata")
        if _tdata_dir_looks_valid(tdata_dir):
            return (root, portable_dir)
    if (root / "TelegramForcePortable" / "tdata").is_dir():
        return (root, root / "TelegramForcePortable")
    if root.name == "TelegramForcePortable" and (root / "tdata").is_dir():
        return (root.parent, root)
    raise RuntimeError("В выбранной папке не найден portable Telegram Desktop профиль.")


def _tdata_signature_from_dir(tdata_dir: Path) -> tuple[str, ...]:
    rows: list[str] = []
    for relative in TDATA_SIGNATURE_FILES:
        path = tdata_dir / relative
        if not path.is_file():
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        rows.append(f"{relative}:{len(data)}:{hashlib.sha1(data).hexdigest()}")
    return tuple(rows)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_pid(pid: int, *, timeout_sec: float = 5.0) -> bool:
    if pid <= 0:
        return True
    if not _pid_is_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return not _pid_is_alive(pid)
    deadline = time.monotonic() + max(timeout_sec, 0.5)
    while time.monotonic() < deadline:
        if not _pid_is_alive(pid):
            return True
        time.sleep(0.1)
    return not _pid_is_alive(pid)


def _find_running_pid(portable_dir: Path) -> int | None:
    proc_root = Path("/proc")
    needle = str(portable_dir.resolve())
    if not proc_root.exists():
        return None
    for item in proc_root.iterdir():
        if not item.name.isdigit():
            continue
        try:
            cmdline = (item / "cmdline").read_text(encoding="utf-8", errors="ignore").replace("\x00", " ").strip()
        except OSError:
            continue
        if not cmdline or "Telegram" not in cmdline or needle not in cmdline:
            continue
        return int(item.name)
    return None


def _window_title_for_pid(pid: int) -> str:
    if pid <= 0:
        return ""
    wmctrl = shutil.which("wmctrl")
    if not wmctrl:
        return ""
    result = subprocess.run([wmctrl, "-lp"], capture_output=True, text=True, check=False)
    for raw in result.stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        if parts[2].isdigit() and int(parts[2]) == pid:
            return parts[4].strip()
    return ""


def _portable_dir_from_metadata(path: Path) -> Path | None:
    payload = _read_json(path)
    raw = str(payload.get("portable_dir") or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def _tdata_dir_from_metadata(path: Path) -> Path | None:
    payload = _read_json(path)
    raw = str(payload.get("tdata_dir") or "").strip()
    return Path(raw).expanduser().resolve() if raw else None


def portable_profile_label(status: PortableProfileStatus) -> str:
    label = status.account_label or status.account_username or status.profile_name
    if status.account_label and status.profile_name and status.account_label != status.profile_name:
        label = f"{status.account_label} ({status.profile_name})"
    state = "запущен" if status.running else "остановлен"
    return f"{label} [{state}]"


def portable_profile_kind(status: PortableProfileStatus) -> str:
    if status.profile.source_kind == "slot_runtime" or status.profile.slot_number:
        return "legacy"
    if status.profile.source_kind == "adopted_folder" and not status.profile.managed:
        return "adopted"
    return "managed"


class PortableProfileRegistry:
    def __init__(
        self,
        *,
        workspace_root: Path,
        binary_finder: Callable[[Path], Path | None],
        logger: Callable[[str], None] | None = None,
    ):
        self.workspace_root = workspace_root
        self.binary_finder = binary_finder
        self.logger = logger
        self.profiles_root = workspace_root / "PortableProfiles"

    def ensure_roots(self) -> None:
        self.profiles_root.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(self.profiles_root, 0o700)

    def list_profiles(self) -> list[PortableProfileStatus]:
        self.ensure_roots()
        rows: list[PortableProfileStatus] = []
        rows.extend(self._scan_managed_profiles())
        rows.extend(self._scan_legacy_slot_profiles())
        deduped: list[PortableProfileStatus] = []
        seen: set[str] = set()
        for item in rows:
            key = str(item.profile_dir.resolve())
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        deduped.sort(
            key=lambda item: (
                0 if item.running else 1,
                (item.account_label or item.account_username or item.profile_name).lower(),
                str(item.profile_dir).lower(),
            )
        )
        return deduped

    def status(self, profile_dir: str | Path) -> PortableProfileStatus | None:
        root = Path(profile_dir).expanduser().resolve()
        metadata_path = root / "portable-profile.json"
        if not metadata_path.is_file():
            link_target = _read_workspace_link_target(root)
            if link_target is None:
                return None
            root = link_target
            metadata_path = root / "portable-profile.json"
            if not metadata_path.is_file():
                return None
        payload = _read_json(metadata_path)
        profile = self._profile_from_payload(payload, metadata_path=metadata_path)
        if profile is None:
            return None
        runtime_workdir = self._runtime_workdir_from_payload(payload, profile.portable_dir)
        pid = self._resolve_profile_pid(payload, runtime_workdir)
        running = bool(pid and _pid_is_alive(pid))
        binary_path = profile.binary_path or self.binary_finder(profile.profile_dir)
        if binary_path is None and running:
            state = "running"
            detail = "Профиль запущен, но путь к Telegram binary не удалось определить."
        elif running:
            state = "running"
            detail = "Portable профиль уже запущен."
        elif not _tdata_dir_looks_valid(profile.tdata_dir):
            state = "missing"
            detail = "Не найден TelegramForcePortable/tdata."
        elif binary_path is None:
            state = "binary_missing"
            detail = "Не найден Telegram binary для этого portable профиля."
        else:
            state = "ready"
            detail = "Portable профиль готов к запуску и дальнейшему использованию."
        window_title = _window_title_for_pid(pid or 0)
        return PortableProfileStatus(
            profile=PortableProfile(
                profile_id=profile.profile_id,
                profile_name=profile.profile_name,
                profile_dir=profile.profile_dir,
                binary_path=binary_path,
                portable_dir=profile.portable_dir,
                tdata_dir=profile.tdata_dir,
                metadata_path=profile.metadata_path,
                account_username=profile.account_username,
                account_label=profile.account_label,
                runtime_version=profile.runtime_version,
                runtime_source=profile.runtime_source,
                source_kind=profile.source_kind,
                source_path=profile.source_path,
                slot_number=profile.slot_number,
                managed=profile.managed,
            ),
            running=running,
            pid=pid if running else None,
            state=state,
            detail=detail,
            window_title=window_title,
            log_path=runtime_workdir / "log.txt",
        )

    def import_zip(
        self,
        source_path: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
        launch: bool = False,
    ) -> PortableProfileStatus:
        self.ensure_roots()
        kind, source, tdata_dir = _detect_import_payload(Path(source_path))
        profile_dir = self._unique_managed_profile_dir(profile_name or source.stem)
        portable_dir = profile_dir / "TelegramForcePortable"
        portable_dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(profile_dir, 0o700)
        _chmod_best_effort(portable_dir, 0o700)
        target_tdata = portable_dir / "tdata"
        if target_tdata.exists():
            if target_tdata.is_symlink() or target_tdata.is_file():
                target_tdata.unlink(missing_ok=True)
            else:
                shutil.rmtree(target_tdata)
        if kind == "zip":
            _extract_tdata_zip(source, target_tdata)
        else:
            if tdata_dir is None or not tdata_dir.is_dir():
                raise RuntimeError(f"В source не найден tdata: {source}")
            shutil.copytree(tdata_dir, target_tdata)
            _chmod_best_effort(target_tdata, 0o700)
        binary_path = self._ensure_profile_runtime_links(profile_dir)
        metadata = self._write_metadata(
            profile_dir=profile_dir,
            portable_dir=portable_dir,
            tdata_dir=target_tdata,
            binary_path=binary_path,
            profile_name=profile_name or source.stem,
            account_username=account_username,
            account_label=account_label,
            runtime_source="cached_runtime",
            source_kind=kind,
            source_path=source,
            slot_number="",
            managed=True,
        )
        status = self.status(metadata.profile_dir)
        if status is None:
            raise RuntimeError("Не удалось прочитать metadata нового portable профиля.")
        if launch:
            status, _already_running = self.launch_profile(status.profile_dir)
        self._log(
            f"portable_profile_imported profile={status.profile_dir} source_kind={kind} source={source}"
        )
        return status

    def adopt_profile(
        self,
        profile_path: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
    ) -> PortableProfileStatus:
        self.ensure_roots()
        root, portable_dir = _normalize_adopt_profile_root(Path(profile_path))
        tdata_dir = portable_dir / "tdata"
        if not _tdata_dir_looks_valid(tdata_dir):
            raise RuntimeError("В portable папке не найден валидный tdata.")
        binary_path = self._ensure_profile_runtime_links(root)
        metadata = self._write_metadata(
            profile_dir=root,
            portable_dir=portable_dir,
            tdata_dir=tdata_dir,
            binary_path=binary_path,
            profile_name=profile_name or root.name,
            account_username=account_username,
            account_label=account_label,
            runtime_source="existing_portable",
            source_kind="adopted_folder",
            source_path=root,
            slot_number="",
            managed=root.is_relative_to(self.profiles_root) if hasattr(root, "is_relative_to") else str(root).startswith(str(self.profiles_root)),
        )
        if not self._is_under_profiles_root(root):
            link_path = self._unique_managed_profile_dir(profile_name or root.name, prefix="LinkedPortable")
            if not link_path.exists():
                try:
                    link_path.symlink_to(root, target_is_directory=True)
                except OSError:
                    _write_workspace_link(link_path, root)
        status = self.status(metadata.profile_dir)
        if status is None:
            raise RuntimeError("Не удалось подготовить metadata принятого portable профиля.")
        self._log(f"portable_profile_adopted profile={status.profile_dir}")
        return status

    def launch_profile(
        self,
        profile_dir: str | Path,
        *,
        workdir_override: Path | None = None,
    ) -> tuple[PortableProfileStatus, bool]:
        status = self.status(profile_dir)
        if status is None:
            raise RuntimeError(f"Portable профиль не найден: {profile_dir}")
        if status.running:
            return (status, True)
        binary_path = status.profile.binary_path or self.binary_finder(status.profile.profile_dir)
        if binary_path is None:
            raise RuntimeError("Не найден Telegram binary для запуска portable профиля.")
        try:
            mode = binary_path.stat().st_mode
            if mode & 0o111 == 0:
                binary_path.chmod(mode | 0o755)
        except OSError as exc:
            raise RuntimeError(f"Не удалось подготовить Telegram binary: {exc}") from exc
        try:
            workdir = (workdir_override or status.profile.portable_dir).expanduser().resolve()
            workdir.mkdir(parents=True, exist_ok=True)
            _chmod_best_effort(workdir, 0o700)
            process = subprocess.Popen(
                [str(binary_path), "-workdir", str(workdir)],
                cwd=str(binary_path.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise RuntimeError(f"Не удалось запустить portable профиль: {exc}") from exc
        payload = _read_json(status.profile.metadata_path)
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        if not isinstance(runtime, dict):
            runtime = {}
        runtime.update(
            {
                "last_pid": process.pid,
                "last_launch_at": _now_iso(),
                "launch_workdir": str(workdir),
            }
        )
        payload["runtime"] = runtime
        payload["updated_at"] = _now_iso()
        _write_json(status.profile.metadata_path, payload)
        self._log(f"portable_profile_launch profile={status.profile_dir} pid={process.pid} workdir={workdir}")
        latest = self.status(status.profile_dir)
        if latest is None:
            raise RuntimeError("Portable профиль запущен, но status не прочитался повторно.")
        return (latest, False)

    def remove_profile(self, profile_dir: str | Path) -> PortableProfileRemovalResult:
        root = Path(profile_dir).expanduser().resolve()
        status = self.status(root)
        if status is None:
            accounts_root = self.workspace_root / "accounts"
            try:
                root.relative_to(accounts_root.resolve())
            except ValueError:
                pass
            else:
                raise RuntimeError("Legacy slot profile нельзя убрать из панели в этом цикле.")
            kind = "managed" if self._is_under_profiles_root(root) else "adopted"
            removed_paths: list[Path] = []
            external_data_preserved = kind == "adopted"
            if kind == "managed":
                if root.exists():
                    shutil.rmtree(root, ignore_errors=True)
                    removed_paths.append(root)
            else:
                for link_path in self._workspace_links_for_profile(root):
                    try:
                        if link_path.is_dir() and not link_path.is_symlink():
                            shutil.rmtree(link_path, ignore_errors=True)
                        else:
                            link_path.unlink()
                    except OSError:
                        continue
                    removed_paths.append(link_path)
            self._log(f"portable_profile_removed profile={root} kind={kind} missing=1")
            return PortableProfileRemovalResult(
                profile_dir=root,
                profile_label=root.name or str(root),
                profile_kind=kind,
                removed_paths=tuple(removed_paths),
                external_data_preserved=external_data_preserved,
            )
        kind = portable_profile_kind(status)
        if kind == "legacy":
            raise RuntimeError("Legacy slot profile нельзя убрать из панели в этом цикле.")
        if status.pid and not _terminate_pid(status.pid):
            raise RuntimeError("Не удалось остановить Telegram для удаления portable профиля.")
        removed_paths: list[Path] = []
        external_data_preserved = kind == "adopted"
        if kind == "managed":
            target_root = status.profile.profile_dir
            if target_root.exists():
                shutil.rmtree(target_root, ignore_errors=True)
                removed_paths.append(target_root)
        else:
            for link_path in self._workspace_links_for_profile(status.profile.profile_dir):
                try:
                    if link_path.is_dir() and not link_path.is_symlink():
                        shutil.rmtree(link_path, ignore_errors=True)
                    else:
                        link_path.unlink()
                except OSError:
                    continue
                removed_paths.append(link_path)
        self._log(f"portable_profile_removed profile={status.profile_dir} kind={kind}")
        return PortableProfileRemovalResult(
            profile_dir=status.profile_dir,
            profile_label=portable_profile_label(status),
            profile_kind=kind,
            removed_paths=tuple(removed_paths),
            external_data_preserved=external_data_preserved,
        )

    def sync_legacy_slot_profile(
        self,
        slot_number: str,
        *,
        profile_name: str = "",
        account_username: str = "",
        account_label: str = "",
    ) -> PortableProfileStatus | None:
        slot_text = str(slot_number or "").strip()
        if not slot_text:
            return None
        runtime_root = self.workspace_root / "accounts" / slot_text / "runtime"
        legacy_tdata = runtime_root / "portable_tdata"
        fallback_tdata = runtime_root / "tdata"
        target_tdata = legacy_tdata if _tdata_dir_looks_valid(legacy_tdata) else fallback_tdata
        if not _tdata_dir_looks_valid(target_tdata):
            return None
        portable_dir = runtime_root / "TelegramForcePortable"
        portable_dir.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(runtime_root, 0o700)
        _chmod_best_effort(portable_dir, 0o700)
        alias_tdata = portable_dir / "tdata"
        if alias_tdata.is_symlink():
            try:
                if alias_tdata.resolve() != target_tdata.resolve():
                    alias_tdata.unlink(missing_ok=True)
            except OSError:
                alias_tdata.unlink(missing_ok=True)
        elif alias_tdata.exists():
            shutil.rmtree(alias_tdata, ignore_errors=True)
        if not alias_tdata.exists():
            try:
                alias_tdata.symlink_to(target_tdata, target_is_directory=True)
            except OSError:
                _replace_tree(target_tdata, alias_tdata)
        binary_path = self._ensure_profile_runtime_links(runtime_root)
        metadata = self._write_metadata(
            profile_dir=runtime_root,
            portable_dir=portable_dir,
            tdata_dir=alias_tdata,
            binary_path=binary_path,
            profile_name=profile_name or f"slot-{slot_text}",
            account_username=account_username,
            account_label=account_label or f"Слот {slot_text}",
            runtime_source="slot_runtime_clone",
            source_kind="slot_runtime",
            source_path=target_tdata,
            slot_number=slot_text,
            managed=False,
        )
        return self.status(metadata.profile_dir)

    def _profile_from_payload(self, payload: dict[str, Any], *, metadata_path: Path) -> PortableProfile | None:
        profile_dir = Path(str(payload.get("profile_dir") or metadata_path.parent)).expanduser().resolve()
        portable_dir = Path(str(payload.get("portable_dir") or profile_dir / "TelegramForcePortable")).expanduser().resolve()
        tdata_dir = Path(str(payload.get("tdata_dir") or portable_dir / "tdata")).expanduser().resolve()
        account = payload.get("account") if isinstance(payload.get("account"), dict) else {}
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        binary_raw = str(payload.get("binary_path") or "").strip()
        binary_path = Path(binary_raw).expanduser().resolve() if binary_raw else None
        return PortableProfile(
            profile_id=str(payload.get("profile_id") or hashlib.sha1(str(profile_dir).encode("utf-8")).hexdigest()[:16]),
            profile_name=str(payload.get("profile_name") or profile_dir.name),
            profile_dir=profile_dir,
            binary_path=binary_path,
            portable_dir=portable_dir,
            tdata_dir=tdata_dir,
            metadata_path=metadata_path,
            account_username=str(account.get("username") or "").strip(),
            account_label=str(account.get("label") or "").strip(),
            runtime_version=str(runtime.get("version") or "").strip(),
            runtime_source=str(runtime.get("source") or "").strip(),
            source_kind=str(source.get("kind") or "").strip(),
            source_path=Path(str(source.get("path") or "")).expanduser().resolve()
            if str(source.get("path") or "").strip()
            else None,
            slot_number=str(payload.get("slot_number") or "").strip(),
            managed=bool(payload.get("managed")),
        )

    def _resolve_profile_pid(self, payload: dict[str, Any], portable_dir: Path) -> int | None:
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        pid = 0
        if isinstance(runtime, dict):
            try:
                pid = int(runtime.get("last_pid") or 0)
            except (TypeError, ValueError):
                pid = 0
        if pid > 0 and _pid_is_alive(pid):
            return pid
        return _find_running_pid(portable_dir)

    def _runtime_workdir_from_payload(self, payload: dict[str, Any], portable_dir: Path) -> Path:
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        raw = str(runtime.get("launch_workdir") or "").strip() if isinstance(runtime, dict) else ""
        if not raw:
            return portable_dir
        return Path(raw).expanduser().resolve()

    def _scan_managed_profiles(self) -> list[PortableProfileStatus]:
        rows: list[PortableProfileStatus] = []
        if not self.profiles_root.exists():
            return rows
        for item in sorted(self.profiles_root.iterdir(), key=lambda path: path.name.lower()):
            metadata_path = item / "portable-profile.json"
            if not metadata_path.is_file() and _read_workspace_link_target(item) is None:
                continue
            status = self.status(item)
            if status is not None:
                rows.append(status)
        return rows

    def _scan_legacy_slot_profiles(self) -> list[PortableProfileStatus]:
        rows: list[PortableProfileStatus] = []
        accounts_dir = self.workspace_root / "accounts"
        if not accounts_dir.exists():
            return rows
        for slot_dir in sorted((item for item in accounts_dir.iterdir() if item.is_dir()), key=lambda path: path.name):
            metadata_path = slot_dir / "runtime" / "portable-profile.json"
            if not metadata_path.is_file():
                continue
            status = self.status(metadata_path.parent)
            if status is not None:
                rows.append(status)
        return rows

    def _unique_managed_profile_dir(self, profile_name: str, *, prefix: str = "TelegramPortable") -> Path:
        base_slug = _portable_dir_slug(profile_name)
        candidate = self.profiles_root / f"{prefix}-{base_slug}"
        if not candidate.exists():
            return candidate
        suffix = 2
        while True:
            next_candidate = self.profiles_root / f"{prefix}-{base_slug}-{suffix}"
            if not next_candidate.exists():
                return next_candidate
            suffix += 1

    def _ensure_profile_runtime_links(self, profile_dir: Path) -> Path | None:
        binary_path = self.binary_finder(profile_dir)
        if binary_path is None:
            return None
        binary_link = profile_dir / "Telegram"
        if not binary_link.exists():
            try:
                binary_link.symlink_to(binary_path)
            except OSError:
                pass
        updater = binary_path.parent / "Updater"
        updater_link = profile_dir / "Updater"
        if updater.is_file() and not updater_link.exists():
            try:
                updater_link.symlink_to(updater)
            except OSError:
                pass
        return binary_link.resolve() if binary_link.exists() else binary_path.resolve()

    def _workspace_links_for_profile(self, profile_dir: Path) -> list[Path]:
        target = profile_dir.expanduser().resolve()
        rows: list[Path] = []
        if not self.profiles_root.exists():
            return rows
        for item in self.profiles_root.iterdir():
            if item.is_symlink():
                try:
                    if item.resolve() == target:
                        rows.append(item)
                except OSError:
                    continue
                continue
            pointer_target = _read_workspace_link_target(item)
            if pointer_target is not None and pointer_target == target:
                rows.append(item)
        return rows

    def _write_metadata(
        self,
        *,
        profile_dir: Path,
        portable_dir: Path,
        tdata_dir: Path,
        binary_path: Path | None,
        profile_name: str,
        account_username: str,
        account_label: str,
        runtime_source: str,
        source_kind: str,
        source_path: Path | None,
        slot_number: str,
        managed: bool,
    ) -> PortableProfile:
        metadata_path = profile_dir / "portable-profile.json"
        previous = _read_json(metadata_path)
        created_at = str(previous.get("created_at") or "").strip() or _now_iso()
        runtime_id = hashlib.sha1(str((binary_path or profile_dir).resolve()).encode("utf-8")).hexdigest()[:16]
        previous_runtime = previous.get("runtime") if isinstance(previous.get("runtime"), dict) else {}
        previous_source = previous.get("source") if isinstance(previous.get("source"), dict) else {}
        runtime_payload = dict(previous_runtime) if isinstance(previous_runtime, dict) else {}
        runtime_payload.update(
            {
                "runtime_id": str(runtime_payload.get("runtime_id") or runtime_id) or runtime_id,
                "version": str(runtime_payload.get("version") or "") or "cached-runtime",
                "source": runtime_source,
                "cache_dir": str((binary_path.parent if binary_path is not None else profile_dir).resolve()),
                "last_pid": int(runtime_payload.get("last_pid") or 0),
            }
        )
        source_payload = dict(previous_source) if isinstance(previous_source, dict) else {}
        source_payload.update(
            {
                "kind": source_kind,
                "path": str(source_path.resolve()) if source_path is not None else "",
                "signature": list(_tdata_signature_from_dir(tdata_dir.resolve())),
            }
        )
        payload = {
            "profile_id": str(previous.get("profile_id") or hashlib.sha1(str(profile_dir.resolve()).encode("utf-8")).hexdigest()[:16]),
            "profile_name": profile_name,
            "profile_dir": str(profile_dir.resolve()),
            "binary_path": str(binary_path.resolve()) if binary_path is not None else "",
            "portable_dir": str(portable_dir.resolve()),
            "tdata_dir": str(tdata_dir.resolve()),
            "account": {
                "username": str(account_username or "").strip(),
                "label": str(account_label or "").strip(),
            },
            "runtime": runtime_payload,
            "source": source_payload,
            "slot_number": str(slot_number or "").strip(),
            "managed": bool(managed),
            "created_at": created_at,
            "updated_at": _now_iso(),
        }
        _write_json(metadata_path, payload)
        profile = self._profile_from_payload(payload, metadata_path=metadata_path)
        if profile is None:
            raise RuntimeError(f"Не удалось записать portable metadata: {metadata_path}")
        return profile

    def _is_under_profiles_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.profiles_root.resolve())
        except ValueError:
            return False
        return True

    def _log(self, message: str) -> None:
        if self.logger is not None:
            self.logger(message)
