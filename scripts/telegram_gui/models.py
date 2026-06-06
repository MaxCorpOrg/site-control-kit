from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


def normalize_operation_kind(value: str | None) -> str:
    return "public_phones" if str(value or "").strip() == "public_phones" else "usernames"


def operation_metric_label(operation_kind: str) -> str:
    return "номеров" if normalize_operation_kind(operation_kind) == "public_phones" else "@username"


def operation_metric_count(*, operation_kind: str, usernames_found: int, phones_found: int) -> int:
    if normalize_operation_kind(operation_kind) == "public_phones":
        return max(int(phones_found or 0), 0)
    return max(int(usernames_found or 0), 0)


def operation_metric_summary(
    operation_kind: str,
    usernames_found: int,
    phones_found: int,
    private_phones_found: int = 0,
) -> str:
    count = operation_metric_count(
        operation_kind=operation_kind,
        usernames_found=usernames_found,
        phones_found=phones_found,
    )
    if normalize_operation_kind(operation_kind) == "public_phones":
        private_count = max(int(private_phones_found or 0), 0)
        public_count = max(count - private_count, 0)
        if private_count > 0:
            return f"номеров {count} (public: {public_count}, private: {private_count})"
        return f"номеров {count}"
    return f"@{count}"


@dataclass(frozen=True)
class AccountOption:
    key: str
    label: str
    name: str
    token: str
    profile_source: str
    source_kind: str
    sort_key: tuple[int, str, str]
    secret_ref: str = ""
    slot_number: str = ""
    token_source: str = ""
    availability_state: str = "ready"
    availability_detail: str = ""
    portable_source_path: str = ""
    portable_source_kind: str = ""
    portable_runtime_state: str = ""
    portable_profile_dir: str = ""
    portable_profile_name: str = ""
    portable_profile_label: str = ""


@dataclass(frozen=True)
class PortableSourceInfo:
    slot_number: str
    path: Path | None
    kind: str
    detail: str = ""
    tdata_dir: Path | None = None


@dataclass(frozen=True)
class PortableRuntimeState:
    slot_number: str
    state: str
    detail: str
    source_path: Path | None = None
    source_kind: str = ""
    runtime_dir: Path | None = None
    tdata_dir: Path | None = None
    binary_path: Path | None = None
    source_signature: str = ""
    ready_for_export: bool = False
    needs_rebuild: bool = False
    authorized: bool = False
    launch_dir: Path | None = None
    helper_dir: Path | None = None
    helper_source: str = ""
    last_sync_at: str = ""


@dataclass(frozen=True)
class PortableProfile:
    profile_id: str
    profile_name: str
    profile_dir: Path
    binary_path: Path | None
    portable_dir: Path
    tdata_dir: Path
    metadata_path: Path
    account_username: str = ""
    account_label: str = ""
    runtime_version: str = ""
    runtime_source: str = ""
    source_kind: str = ""
    source_path: Path | None = None
    slot_number: str = ""
    managed: bool = False


@dataclass(frozen=True)
class PortableProfileStatus:
    profile: PortableProfile
    running: bool
    pid: int | None
    state: str
    detail: str
    window_title: str = ""
    log_path: Path | None = None

    @property
    def profile_dir(self) -> Path:
        return self.profile.profile_dir

    @property
    def profile_name(self) -> str:
        return self.profile.profile_name

    @property
    def account_username(self) -> str:
        return self.profile.account_username

    @property
    def account_label(self) -> str:
        return self.profile.account_label


@dataclass(frozen=True)
class PortableProfileRemovalResult:
    profile_dir: Path
    profile_label: str
    profile_kind: str
    removed_paths: tuple[Path, ...]
    external_data_preserved: bool
    secret_removed: bool = False


@dataclass(frozen=True)
class BrowserTarget:
    client_id: str
    tab_id: int
    tab_title: str
    tab_url: str


@dataclass(frozen=True)
class ChatOption:
    title: str
    subtitle: str
    url: str
    fragment: str
    peer_id: str
    active: bool
    visible: bool
    ordinal: int
    source_kind: str = "live"


@dataclass(frozen=True)
class ArtifactBundle:
    markdown: Path
    usernames_txt: Path | None
    usernames_json: Path | None = None
    phones_txt: Path | None = None
    phones_json: Path | None = None
    private_phones_txt: Path | None = None
    private_phones_json: Path | None = None
    safe_txt: Path | None = None
    safe_md: Path | None = None
    run_log: Path | None = None
    action_log: Path | None = None
    summary_json: Path | None = None
    artifacts_json: Path | None = None
    events_jsonl: Path | None = None

    def entries(self) -> list[tuple[str, Path]]:
        rows: list[tuple[str, Path]] = [("Markdown", self.markdown)]
        optional = (
            ("Usernames TXT", self.usernames_txt),
            ("Usernames JSON", self.usernames_json),
            ("Phones TXT", self.phones_txt),
            ("Phones JSON", self.phones_json),
            ("Private Phones TXT", self.private_phones_txt),
            ("Private Phones JSON", self.private_phones_json),
            ("Safe TXT", self.safe_txt),
            ("Safe MD", self.safe_md),
            ("Run log", self.run_log),
            ("Action log", self.action_log),
            ("Summary JSON", self.summary_json),
            ("Artifacts JSON", self.artifacts_json),
            ("Events JSONL", self.events_jsonl),
        )
        for label, path in optional:
            if path is not None:
                rows.append((label, path))
        return rows

    def to_json(self) -> dict[str, str]:
        return {
            key: str(value)
            for key, value in {
                "markdown": self.markdown,
                "usernames_txt": self.usernames_txt,
                "usernames_json": self.usernames_json,
                "phones_txt": self.phones_txt,
                "phones_json": self.phones_json,
                "private_phones_txt": self.private_phones_txt,
                "private_phones_json": self.private_phones_json,
                "safe_txt": self.safe_txt,
                "safe_md": self.safe_md,
                "run_log": self.run_log,
                "action_log": self.action_log,
                "summary_json": self.summary_json,
                "artifacts_json": self.artifacts_json,
                "events_jsonl": self.events_jsonl,
            }.items()
            if value is not None
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> ArtifactBundle:
        return cls(
            markdown=Path(str(payload.get("markdown") or "")),
            usernames_txt=Path(str(payload["usernames_txt"])) if payload.get("usernames_txt") else None,
            usernames_json=Path(str(payload["usernames_json"])) if payload.get("usernames_json") else None,
            phones_txt=Path(str(payload["phones_txt"])) if payload.get("phones_txt") else None,
            phones_json=Path(str(payload["phones_json"])) if payload.get("phones_json") else None,
            private_phones_txt=Path(str(payload["private_phones_txt"])) if payload.get("private_phones_txt") else None,
            private_phones_json=Path(str(payload["private_phones_json"])) if payload.get("private_phones_json") else None,
            safe_txt=Path(str(payload["safe_txt"])) if payload.get("safe_txt") else None,
            safe_md=Path(str(payload["safe_md"])) if payload.get("safe_md") else None,
            run_log=Path(str(payload["run_log"])) if payload.get("run_log") else None,
            action_log=Path(str(payload["action_log"])) if payload.get("action_log") else None,
            summary_json=Path(str(payload["summary_json"])) if payload.get("summary_json") else None,
            artifacts_json=Path(str(payload["artifacts_json"])) if payload.get("artifacts_json") else None,
            events_jsonl=Path(str(payload["events_jsonl"])) if payload.get("events_jsonl") else None,
        )


@dataclass(frozen=True)
class ExportResult:
    output_path: Path
    usernames_txt: Path | None
    safe_count: int
    history_messages_scanned: int
    usernames_found: int
    interrupted: bool
    safe_txt: Path | None
    safe_md: Path | None
    log_path: Path
    action_log_path: Path
    operation_kind: str = "usernames"
    phones_found: int = 0
    usernames_json: Path | None = None
    phones_txt: Path | None = None
    phones_json: Path | None = None
    private_phones_found: int = 0
    private_phones_txt: Path | None = None
    private_phones_json: Path | None = None
    surface_key: str = ""
    surface_label: str = ""
    surface_badge: str = ""
    preset_key: str = ""
    preset_label: str = ""
    started_at: str = ""
    finished_at: str = ""
    duration_sec: int = 0
    status: str = ""
    failure_reason: str = ""
    security_mode: str = ""
    summary_path: Path | None = None
    artifacts_path: Path | None = None
    events_path: Path | None = None

    def artifact_bundle(self) -> ArtifactBundle:
        return ArtifactBundle(
            markdown=self.output_path,
            usernames_txt=self.usernames_txt,
            usernames_json=self.usernames_json,
            phones_txt=self.phones_txt,
            phones_json=self.phones_json,
            private_phones_txt=self.private_phones_txt,
            private_phones_json=self.private_phones_json,
            safe_txt=self.safe_txt,
            safe_md=self.safe_md,
            run_log=self.log_path,
            action_log=self.action_log_path,
            summary_json=self.summary_path,
            artifacts_json=self.artifacts_path,
            events_jsonl=self.events_path,
        )


@dataclass
class ExportProgressState:
    chat_ref: str = ""
    messages_scanned: int = 0
    usernames_found: int = 0
    phones_found: int = 0
    started_at: float = 0.0
    last_update_at: float = 0.0
    stage: str = ""
    interrupted: bool = False
    done: bool = False
    failed: bool = False
    total_messages_hint: int | None = None
    operation_kind: str = "usernames"


@dataclass(frozen=True)
class ProgressEvent:
    stage: str
    messages_scanned: int = 0
    usernames_found: int = 0
    phones_found: int = 0
    chat_ref: str = ""
    interrupted: bool = False
    done: bool = False
    error: str = ""

    @classmethod
    def from_progress_line(cls, payload: dict[str, str] | None) -> ProgressEvent:
        if not payload:
            return cls(stage="")
        return cls(
            stage=str(payload.get("stage") or "").strip(),
            messages_scanned=int(str(payload.get("messages") or "0").strip() or "0"),
            usernames_found=int(str(payload.get("usernames") or "0").strip() or "0"),
            phones_found=int(str(payload.get("phones") or "0").strip() or "0"),
            chat_ref=str(payload.get("chat") or "").strip(),
            interrupted=bool(int(str(payload.get("interrupted") or "0").strip() or "0")),
            done=bool(int(str(payload.get("done") or "0").strip() or "0")),
            error=str(payload.get("error") or "").strip(),
        )


@dataclass(frozen=True)
class SecretRef:
    ref: str
    path: Path


@dataclass(frozen=True)
class WorkspaceHealth:
    workspace_writable: bool
    runtime_writable: bool
    logs_writable: bool
    helper_available: bool
    collector_python_available: bool
    node_available: bool
    hub_reachable: bool
    stale_runtime_files: int = 0
    warning: str = ""


@dataclass(frozen=True)
class PreflightStatus:
    key: str
    label: str
    state: str
    detail: str


@dataclass(frozen=True)
class FallbackReadiness:
    surface_key: str
    surface_label: str
    surface_badge: str
    state: str
    detail: str
    target: BrowserTarget | None = None
    action_label: str = ""


@dataclass(frozen=True)
class RunStatusSummary:
    status: str
    safe_count: int
    usernames_found: int
    history_messages_scanned: int
    duration_sec: int
    interrupted: bool
    operation_kind: str = "usernames"
    phones_found: int = 0
    private_phones_found: int = 0
    failure_reason: str = ""

    def metric_count(self) -> int:
        return operation_metric_count(
            operation_kind=self.operation_kind,
            usernames_found=self.usernames_found,
            phones_found=self.phones_found,
        )

    def metric_label(self) -> str:
        return operation_metric_label(self.operation_kind)

    def metric_summary(self) -> str:
        return operation_metric_summary(
            self.operation_kind,
            self.usernames_found,
            self.phones_found,
            self.private_phones_found,
        )


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    created_at: str
    surface_key: str
    surface_label: str
    surface_badge: str
    preset_key: str
    preset_label: str
    account_key: str
    account_label: str
    chat_ref: str
    chat_title: str
    output_path: Path
    interrupted: bool
    safe_count: int
    usernames_found: int
    history_messages_scanned: int
    artifacts: ArtifactBundle
    operation_kind: str = "usernames"
    phones_found: int = 0
    private_phones_found: int = 0
    status: str = ""
    duration_sec: int = 0
    started_at: str = ""
    finished_at: str = ""
    security_mode: str = ""
    failure_reason: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "surface_key": self.surface_key,
            "surface_label": self.surface_label,
            "surface_badge": self.surface_badge,
            "preset_key": self.preset_key,
            "preset_label": self.preset_label,
            "account_key": self.account_key,
            "account_label": self.account_label,
            "chat_ref": self.chat_ref,
            "chat_title": self.chat_title,
            "output_path": str(self.output_path),
            "interrupted": self.interrupted,
            "safe_count": self.safe_count,
            "usernames_found": self.usernames_found,
            "history_messages_scanned": self.history_messages_scanned,
            "operation_kind": normalize_operation_kind(self.operation_kind),
            "phones_found": self.phones_found,
            "private_phones_found": self.private_phones_found,
            "status": self.status,
            "duration_sec": self.duration_sec,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "security_mode": self.security_mode,
            "failure_reason": self.failure_reason,
            "artifacts": self.artifacts.to_json(),
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> RunRecord:
        return cls(
            run_id=str(payload.get("run_id") or ""),
            created_at=str(payload.get("created_at") or ""),
            surface_key=str(payload.get("surface_key") or ""),
            surface_label=str(payload.get("surface_label") or ""),
            surface_badge=str(payload.get("surface_badge") or ""),
            preset_key=str(payload.get("preset_key") or ""),
            preset_label=str(payload.get("preset_label") or ""),
            account_key=str(payload.get("account_key") or ""),
            account_label=str(payload.get("account_label") or ""),
            chat_ref=str(payload.get("chat_ref") or ""),
            chat_title=str(payload.get("chat_title") or ""),
            output_path=Path(str(payload.get("output_path") or "")),
            interrupted=bool(payload.get("interrupted")),
            safe_count=int(payload.get("safe_count") or 0),
            usernames_found=int(payload.get("usernames_found") or 0),
            history_messages_scanned=int(payload.get("history_messages_scanned") or 0),
            operation_kind=normalize_operation_kind(str(payload.get("operation_kind") or "usernames")),
            phones_found=int(payload.get("phones_found") or 0),
            private_phones_found=int(payload.get("private_phones_found") or 0),
            status=str(payload.get("status") or ("partial" if payload.get("interrupted") else "done")),
            duration_sec=int(payload.get("duration_sec") or 0),
            started_at=str(payload.get("started_at") or ""),
            finished_at=str(payload.get("finished_at") or ""),
            security_mode=str(payload.get("security_mode") or ""),
            failure_reason=str(payload.get("failure_reason") or ""),
            artifacts=ArtifactBundle.from_json(payload.get("artifacts") or {}),
        )

    def summary(self) -> RunStatusSummary:
        return RunStatusSummary(
            status=self.status or ("partial" if self.interrupted else "done"),
            safe_count=self.safe_count,
            usernames_found=self.usernames_found,
            history_messages_scanned=self.history_messages_scanned,
            duration_sec=self.duration_sec,
            interrupted=self.interrupted,
            operation_kind=self.operation_kind,
            phones_found=self.phones_found,
            private_phones_found=self.private_phones_found,
            failure_reason=self.failure_reason,
        )


@dataclass(frozen=True)
class SessionResumeState:
    account_key: str
    account_label: str
    chat_ref: str
    chat_title: str
    output_path: Path
    surface_key: str
    surface_label: str
    surface_badge: str
    preset_key: str
    preset_label: str
    created_at: str
    operation_kind: str = "usernames"
    last_surface_reason: str = ""
    last_output_dir: Path | None = None
    last_status: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "account_key": self.account_key,
            "account_label": self.account_label,
            "chat_ref": self.chat_ref,
            "chat_title": self.chat_title,
            "output_path": str(self.output_path),
            "surface_key": self.surface_key,
            "surface_label": self.surface_label,
            "surface_badge": self.surface_badge,
            "preset_key": self.preset_key,
            "preset_label": self.preset_label,
            "created_at": self.created_at,
            "operation_kind": normalize_operation_kind(self.operation_kind),
            "last_surface_reason": self.last_surface_reason,
            "last_output_dir": str(self.last_output_dir) if self.last_output_dir is not None else "",
            "last_status": self.last_status,
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> SessionResumeState:
        return cls(
            account_key=str(payload.get("account_key") or ""),
            account_label=str(payload.get("account_label") or ""),
            chat_ref=str(payload.get("chat_ref") or ""),
            chat_title=str(payload.get("chat_title") or ""),
            output_path=Path(str(payload.get("output_path") or "")),
            surface_key=str(payload.get("surface_key") or ""),
            surface_label=str(payload.get("surface_label") or ""),
            surface_badge=str(payload.get("surface_badge") or ""),
            preset_key=str(payload.get("preset_key") or ""),
            preset_label=str(payload.get("preset_label") or ""),
            created_at=str(payload.get("created_at") or ""),
            operation_kind=normalize_operation_kind(str(payload.get("operation_kind") or "usernames")),
            last_surface_reason=str(payload.get("last_surface_reason") or ""),
            last_output_dir=Path(str(payload.get("last_output_dir") or "")).expanduser()
            if str(payload.get("last_output_dir") or "").strip()
            else None,
            last_status=str(payload.get("last_status") or ""),
        )


@dataclass(frozen=True)
class PreflightInfo:
    surface_key: str
    surface_label: str
    surface_badge: str
    is_primary: bool
    tdata_ready: bool
    helper_ready: bool
    output_path: Path | None
    preset_key: str
    preset_label: str
    history_limit: str
    timeout_sec: int | None
    resume_available: bool
    notes: tuple[str, ...] = field(default_factory=tuple)
    statuses: tuple[PreflightStatus, ...] = field(default_factory=tuple)
    security_mode: str = ""
    security_state: str = ""
    workspace_health: WorkspaceHealth | None = None
    surface_reason: str = ""
    security_token_source: str = ""
    security_detail: str = ""
    security_attention_required: bool = False
    security_setup_available: bool = False
    security_setup_label: str = ""
    security_restart_available: bool = False
    security_restart_label: str = ""
    fallback_bridge: FallbackReadiness | None = None
    fallback_cdp: FallbackReadiness | None = None
    portable_source: PortableSourceInfo | None = None
    portable_runtime: PortableRuntimeState | None = None
    portable_profile: PortableProfileStatus | None = None
