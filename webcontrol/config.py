from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class HubConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    token: str = "CHANGE_ME"
    state_file: Path = Path.home() / ".site-control-kit" / "state.json"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"
