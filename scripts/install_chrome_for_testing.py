#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.request import urlopen

METADATA_URL = (
    "https://googlechromelabs.github.io/chrome-for-testing/"
    "last-known-good-versions-with-downloads.json"
)
PLATFORMS = {
    ("Linux", "x86_64"): ("linux64", "chrome-linux64/chrome"),
    ("Darwin", "x86_64"): (
        "mac-x64",
        "chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    ),
    ("Darwin", "arm64"): (
        "mac-arm64",
        "chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
    ),
    ("Windows", "AMD64"): ("win64", "chrome-win64/chrome.exe"),
}


def platform_info() -> tuple[str, str]:
    key = (platform.system(), platform.machine())
    if key not in PLATFORMS:
        supported = ", ".join(f"{system}/{machine}" for system, machine in PLATFORMS)
        raise RuntimeError(
            f"Платформа {key[0]}/{key[1]} не поддержана. Поддерживаются: {supported}"
        )
    return PLATFORMS[key]


def fetch_metadata() -> dict:
    with urlopen(METADATA_URL, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def resolve_download(metadata: dict, channel: str, platform_name: str) -> tuple[str, str]:
    channels = metadata.get("channels", {})
    selected = channels.get(channel)
    if not selected:
        raise RuntimeError(f"В официальном индексе нет канала {channel}")
    downloads = selected.get("downloads", {}).get("chrome", [])
    match = next((item for item in downloads if item.get("platform") == platform_name), None)
    if not match:
        raise RuntimeError(f"В канале {channel} нет Chrome для {platform_name}")
    return str(selected["version"]), str(match["url"])


def restore_executable_bits(version_root: Path) -> None:
    executable_names = {
        "chrome",
        "chrome.exe",
        "chrome_crashpad_handler",
        "chrome_sandbox",
        "xdg-mime",
        "xdg-settings",
    }
    for candidate in version_root.rglob("*"):
        if candidate.is_file() and candidate.name in executable_names:
            candidate.chmod(candidate.stat().st_mode | 0o111)


def install(destination: Path, channel: str, force: bool) -> Path:
    platform_name, binary_relative = platform_info()
    metadata = fetch_metadata()
    version, download_url = resolve_download(metadata, channel, platform_name)
    version_root = destination.resolve() / version
    binary = version_root / binary_relative
    if binary.exists() and not force:
        restore_executable_bits(version_root)
        return binary

    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="site-control-cft-") as temporary:
        archive = Path(temporary) / "chrome.zip"
        with urlopen(download_url, timeout=180) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        extracted = Path(temporary) / "extracted"
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extracted)
        if version_root.exists():
            shutil.rmtree(version_root)
        shutil.move(str(extracted), str(version_root))

    if not binary.exists():
        raise RuntimeError(f"После распаковки не найден браузер: {binary}")
    restore_executable_bits(version_root)
    (version_root / "source.json").write_text(
        json.dumps(
            {
                "version": version,
                "channel": channel,
                "platform": platform_name,
                "url": download_url,
                "metadata_url": METADATA_URL,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return binary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Установить официальную сборку Chrome for Testing")
    parser.add_argument(
        "--destination",
        default=".cache/chrome-for-testing",
        help="Каталог кэша версий",
    )
    parser.add_argument(
        "--channel",
        choices=("Stable", "Beta", "Dev", "Canary"),
        default="Stable",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    try:
        binary = install(Path(args.destination), args.channel, args.force)
    except Exception as exc:
        print(f"Не удалось установить Chrome for Testing: {exc}", file=sys.stderr)
        return 1
    print(binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
