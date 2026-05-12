from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Sequence


class PortableBridge:
    def __init__(self, *, site_control_kit_root: Path, profile_dir: Path, python_bin: str = "python3") -> None:
        self.site_control_kit_root = site_control_kit_root
        self.profile_dir = profile_dir
        self.python_bin = python_bin
        self.script_path = self.site_control_kit_root / "scripts" / "telegram_portable.py"

    def _run(self, *args: str) -> dict:
        cmd = [self.python_bin, str(self.script_path), *args]
        completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
        return json.loads(completed.stdout)

    def status(self) -> dict:
        return self._run("status", "--profile-dir", str(self.profile_dir))

    def launch(self) -> dict:
        return self._run("launch", "--profile-dir", str(self.profile_dir))

    def open_uri(self, uri: str, *, dry_run: bool = False) -> dict:
        args = ["open-uri", "--profile-dir", str(self.profile_dir), "--uri", uri]
        if dry_run:
            args.append("--dry-run")
        return self._run(*args)

    def type_text(self, text: str, *, press_enter: bool = False, dry_run: bool = False) -> dict:
        args = ["type-text", "--profile-dir", str(self.profile_dir), "--text", text]
        if press_enter:
            args.append("--press-enter")
        if dry_run:
            args.append("--dry-run")
        return self._run(*args)

    def accessibility_type_text(
        self,
        *,
        query: str,
        text: str,
        role: str = "",
        match_mode: str = "contains",
        visible_only: bool = False,
        state_filters: Sequence[str] | None = None,
        pick: str = "best",
        index: int = 0,
        clear_first: bool = False,
        press_enter: bool = False,
        dry_run: bool = False,
    ) -> dict:
        args = [
            "accessibility-type-text",
            "--profile-dir",
            str(self.profile_dir),
            "--query",
            query,
            "--text",
            text,
            "--match-mode",
            match_mode,
            "--pick",
            pick,
            "--index",
            str(index),
        ]
        if role:
            args.extend(["--role", role])
        if visible_only:
            args.append("--visible-only")
        for state_filter in state_filters or ():
            args.extend(["--state", str(state_filter)])
        if clear_first:
            args.append("--clear-first")
        if press_enter:
            args.append("--press-enter")
        if dry_run:
            args.append("--dry-run")
        return self._run(*args)

    def accessibility_click(
        self,
        *,
        query: str,
        role: str = "",
        match_mode: str = "contains",
        visible_only: bool = False,
        state_filters: Sequence[str] | None = None,
        pick: str = "best",
        index: int = 0,
        button: int = 1,
        dry_run: bool = False,
    ) -> dict:
        args = [
            "accessibility-click",
            "--profile-dir",
            str(self.profile_dir),
            "--query",
            query,
            "--match-mode",
            match_mode,
            "--pick",
            pick,
            "--index",
            str(index),
            "--button",
            str(button),
        ]
        if role:
            args.extend(["--role", role])
        if visible_only:
            args.append("--visible-only")
        for state_filter in state_filters or ():
            args.extend(["--state", str(state_filter)])
        if dry_run:
            args.append("--dry-run")
        return self._run(*args)

    def press_keys(self, *sequences: str, dry_run: bool = False) -> dict:
        args = ["press-keys", "--profile-dir", str(self.profile_dir)]
        for sequence in sequences:
            args.extend(["--sequence", sequence])
        if dry_run:
            args.append("--dry-run")
        return self._run(*args)

    def window_click(
        self,
        *,
        x_ratio: float,
        y_ratio: float,
        button: int = 1,
        coordinate_space: str = "window_geometry",
        dry_run: bool = False,
    ) -> dict:
        args = [
            "window-click",
            "--profile-dir",
            str(self.profile_dir),
            "--x-ratio",
            str(x_ratio),
            "--y-ratio",
            str(y_ratio),
            "--button",
            str(button),
            "--coordinate-space",
            str(coordinate_space),
        ]
        if dry_run:
            args.append("--dry-run")
        return self._run(*args)
