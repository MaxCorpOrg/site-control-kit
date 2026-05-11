from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from ..models import SecretRef


DEFAULT_DIR_MODE = 0o700
DEFAULT_FILE_MODE = 0o600


def _slugify_secret_name(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9._-]+", "-", text)
    text = text.strip("._-")
    return text or "secret"


def _chmod_best_effort(path: Path, mode: int) -> None:
    try:
        os.chmod(path, mode)
    except OSError:
        pass


class SecretStore:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.expanduser()

    def ensure_secure_dir(self, path: Path | None = None) -> Path:
        target = (path or self.base_dir).expanduser()
        target.mkdir(parents=True, exist_ok=True)
        _chmod_best_effort(target, DEFAULT_DIR_MODE)
        return target

    def ref_path(self, ref: str) -> Path:
        return (self.base_dir / str(ref or "").strip()).expanduser()

    def build_ref(self, namespace: str, name: str, *, suffix: str = ".token") -> SecretRef:
        safe_namespace = _slugify_secret_name(namespace)
        digest = hashlib.sha1(str(name or "").strip().encode("utf-8")).hexdigest()[:12]
        filename = f"{_slugify_secret_name(name)}_{digest}{suffix}"
        relative = f"{safe_namespace}/{filename}"
        path = self.ref_path(relative)
        return SecretRef(ref=relative, path=path)

    def save_secret(self, *, namespace: str, name: str, token: str, secret_ref: str = "") -> str:
        access_token = str(token or "").strip()
        if not access_token:
            raise ValueError("secret token is required")
        ref = secret_ref.strip() if secret_ref else self.build_ref(namespace, name).ref
        path = self.ref_path(ref)
        self.ensure_secure_dir(path.parent)
        path.write_text(access_token + "\n", encoding="utf-8")
        _chmod_best_effort(path, DEFAULT_FILE_MODE)
        return ref

    def load_secret(self, secret_ref: str) -> str:
        path = self.ref_path(secret_ref)
        try:
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            return ""

    def delete_secret(self, secret_ref: str) -> Path | None:
        ref = str(secret_ref or "").strip()
        if not ref:
            return None
        path = self.ref_path(ref)
        try:
            path.unlink()
        except FileNotFoundError:
            return None
        except OSError:
            return None
        parent = path.parent
        while parent != self.base_dir and parent.is_dir():
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
        return path

    def save_registry_file(self, path: Path, content: str) -> None:
        self.ensure_secure_dir(path.parent)
        path.write_text(content, encoding="utf-8")
        _chmod_best_effort(path, DEFAULT_FILE_MODE)

    def is_secure(self, path: Path) -> bool:
        resolved_path = path.expanduser()
        if not resolved_path.exists():
            return False
        if os.name == "nt":
            try:
                target = resolved_path.resolve()
                base = self.base_dir.resolve()
            except OSError:
                return False
            return target == base or base in target.parents
        try:
            mode = resolved_path.stat().st_mode & 0o777
        except OSError:
            return False
        if resolved_path.is_dir():
            return mode & 0o077 == 0
        return mode & 0o177 == 0


def mask_secret(value: str) -> str:
    token = str(value or "")
    if len(token) <= 8:
        return "*" * len(token) if token else ""
    return f"{token[:4]}...{token[-4:]}"
