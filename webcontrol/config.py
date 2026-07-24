from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .settings import load_runtime_settings


@dataclass(slots=True)
class HubConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = ""
    state_file: Path = field(
        default_factory=lambda: load_runtime_settings(mutate=False).hub_state_file
    )
    lease_duration_ms: int = 60_000
    max_attempts: int = 3
    artifacts_root: Path | None = None
    allowed_origins: tuple[str, ...] = (
        "chrome-extension://*",
        "moz-extension://*",
        "http://127.0.0.1:*",
        "http://localhost:*",
    )

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
