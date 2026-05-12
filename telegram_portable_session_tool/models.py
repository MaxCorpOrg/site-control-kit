from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal
from urllib.parse import parse_qs, urlparse


TargetKind = Literal["group", "contact"]
MessageTargetMode = Literal["fixed", "rotating_contacts", "rotating_all"]
MessageSendStrategy = Literal["send_button", "double_return", "send_button_then_return", "return_then_button"]
SyncSourceType = Literal["allowlist_csv", "sandbox_config"]
VisitMode = Literal["explicit_targets", "current_profile_sidebar"]
VisitKind = Literal["group", "contact", "existing_chat"]
VisitAction = Literal["open_uri", "sidebar_click"]


def normalize_handle(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("handle is required")
    if raw.startswith("tg://"):
        parsed = urlparse(raw)
        query = parse_qs(parsed.query)
        domain = (query.get("domain") or [""])[0].strip()
        if not domain:
            raise ValueError(f"cannot extract domain from handle: {value}")
        return domain.lstrip("@")
    if "t.me/" in raw:
        parsed = urlparse(raw if "://" in raw else f"https://{raw}")
        return parsed.path.strip("/").lstrip("@")
    return raw.lstrip("@").strip("/")


@dataclass(slots=True)
class Target:
    target_id: str
    label: str
    handle: str
    kind: TargetKind
    source: str = "manual"
    allowed_actions: tuple[str, ...] = ()
    consent_confirmed: bool = True

    def domain(self) -> str:
        return normalize_handle(self.handle)

    def uri(self) -> str:
        return f"tg://resolve?domain={self.domain()}"

    def username(self) -> str:
        return f"@{self.domain()}"

    def can_send_message(self) -> bool:
        if self.allowed_actions:
            return "send_message" in set(self.allowed_actions)
        return self.kind == "contact"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SessionSettings:
    max_group_views_per_run: int = 3
    max_contact_views_per_run: int = 3
    view_min_seconds: int = 3
    view_max_seconds: int = 6
    visit_mode: VisitMode = "explicit_targets"
    random_walk_visits_per_run: int = 6
    sidebar_x_ratio: float = 0.14
    sidebar_y_min_ratio: float = 0.18
    sidebar_y_max_ratio: float = 0.82
    message_input_x_ratio: float = 0.55
    message_input_y_ratio: float = 0.975
    message_open_delay_seconds: float = 1.0
    message_focus_delay_seconds: float = 0.4
    message_send_delay_seconds: float = 0.2
    message_send_button_x_ratio: float = 0.962
    message_send_button_y_ratio: float = 0.94
    message_send_strategy: MessageSendStrategy = "send_button_then_return"


@dataclass(slots=True)
class MessagePolicy:
    templates: list[str]
    target_username: str = ""
    target_mode: MessageTargetMode = "fixed"
    drafts_per_run: int = 2
    auto_send: bool = False
    total_message_limit: int = 0
    message_targets: list[Target] = field(default_factory=list)

    def target_uri(self) -> str:
        return f"tg://resolve?domain={normalize_handle(self.target_username)}"


@dataclass(slots=True)
class SyncSource:
    source_type: SyncSourceType
    path: str
    enabled: bool = True
    include_groups: bool = True
    include_contacts: bool = True


@dataclass(slots=True)
class ToolConfig:
    version: int
    tool_name: str
    site_control_kit_root: str
    portable_profile_dir: str
    python_bin: str
    session: SessionSettings
    message_policy: MessagePolicy
    sync_sources: list[SyncSource] = field(default_factory=list)
    groups: list[Target] = field(default_factory=list)
    contacts: list[Target] = field(default_factory=list)


@dataclass(slots=True)
class VisitPlanItem:
    target_id: str
    label: str
    kind: VisitKind
    view_seconds: int
    action: VisitAction = "open_uri"
    uri: str = ""
    x_ratio: float | None = None
    y_ratio: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class MessageDraft:
    index: int
    text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SessionPlan:
    seed: str
    visits: list[VisitPlanItem]
    message_target_username: str
    message_target_uri: str
    message_drafts: list[MessageDraft]

    def to_dict(self) -> dict:
        return {
            "seed": self.seed,
            "visits": [item.to_dict() for item in self.visits],
            "message_target_username": self.message_target_username,
            "message_target_uri": self.message_target_uri,
            "message_drafts": [item.to_dict() for item in self.message_drafts],
        }
