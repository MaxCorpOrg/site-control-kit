from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from .models import SyncSource, Target, ToolConfig


@dataclass(slots=True)
class SyncReport:
    source_type: str
    path: str
    enabled: bool
    group_count: int = 0
    contact_count: int = 0
    skipped: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source_type": self.source_type,
            "path": self.path,
            "enabled": self.enabled,
            "group_count": self.group_count,
            "contact_count": self.contact_count,
            "skipped": list(self.skipped),
        }


@dataclass(slots=True)
class ResolvedTargets:
    groups: list[Target]
    contacts: list[Target]
    reports: list[SyncReport] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "groups": [item.to_dict() for item in self.groups],
            "contacts": [item.to_dict() for item in self.contacts],
            "reports": [item.to_dict() for item in self.reports],
        }


def _parse_bool(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"unsupported boolean value: {value}")


def _normalize_text(value: object) -> str:
    return str(value or "").strip()


def _parse_actions(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set, frozenset)):
        raw_items = value
    else:
        raw_items = str(value).replace("\n", ",").replace(";", ",").replace("|", ",").split(",")
    normalized = [str(item).strip() for item in raw_items if str(item).strip()]
    return tuple(dict.fromkeys(normalized))


def _target_key(target: Target) -> tuple[str, str]:
    try:
        normalized = target.domain().casefold()
    except ValueError:
        normalized = target.handle.strip().casefold()
    return (target.kind, normalized)


def _merge_target_lists(*collections: list[Target]) -> list[Target]:
    merged: dict[tuple[str, str], Target] = {}
    ordered: list[Target] = []
    for collection in collections:
        for target in collection:
            key = _target_key(target)
            existing = merged.get(key)
            if existing is None:
                merged[key] = target
                ordered.append(target)
                continue
            existing.allowed_actions = tuple(sorted(set(existing.allowed_actions) | set(target.allowed_actions)))
            existing.consent_confirmed = bool(existing.consent_confirmed or target.consent_confirmed)
            if existing.source != target.source:
                existing.source = f"{existing.source},{target.source}"
            if not existing.label and target.label:
                existing.label = target.label
            if not existing.target_id and target.target_id:
                existing.target_id = target.target_id
    return ordered


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return [{str(key): _normalize_text(value) for key, value in row.items()} for row in reader]


def _extract_handle(value: object) -> str:
    raw = _normalize_text(value)
    if not raw:
        return ""
    if raw.startswith("@") or raw.startswith("tg://") or "t.me/" in raw:
        return raw
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    fragment = str(parsed.fragment or "").strip()
    if fragment.startswith("@") or fragment.startswith("tg://") or "t.me/" in fragment:
        return fragment
    return ""


def _load_allowlist_source(source: SyncSource) -> tuple[list[Target], list[Target], SyncReport]:
    path = Path(source.path).expanduser().resolve()
    report = SyncReport(source_type=source.source_type, path=str(path), enabled=True)
    groups: list[Target] = []
    contacts: list[Target] = []
    for row in _read_csv_rows(path):
        entity_id = _normalize_text(row.get("entity_id"))
        kind_hint = _normalize_text(row.get("kind_hint")).lower()
        username = _normalize_text(row.get("username"))
        if not entity_id or not username:
            report.skipped.append({"entity_id": entity_id, "reason": "missing_entity_id_or_username"})
            continue
        if not _parse_bool(row.get("consent_confirmed"), default=False):
            report.skipped.append({"entity_id": entity_id, "reason": "consent_not_confirmed"})
            continue
        allowed_actions = _parse_actions(row.get("allowed_actions"))
        label = _normalize_text(row.get("title")) or entity_id
        if kind_hint in {"group", "channel"}:
            if not source.include_groups:
                continue
            groups.append(
                Target(
                    target_id=entity_id,
                    label=label,
                    handle=username,
                    kind="group",
                    source="allowlist_csv",
                    allowed_actions=allowed_actions,
                    consent_confirmed=True,
                )
            )
            continue
        if kind_hint in {"user", "contact"}:
            if not source.include_contacts:
                continue
            contacts.append(
                Target(
                    target_id=entity_id,
                    label=label,
                    handle=username,
                    kind="contact",
                    source="allowlist_csv",
                    allowed_actions=allowed_actions,
                    consent_confirmed=True,
                )
            )
            continue
        report.skipped.append({"entity_id": entity_id, "reason": f"unsupported_kind_hint:{kind_hint or 'empty'}"})
    report.group_count = len(groups)
    report.contact_count = len(contacts)
    return groups, contacts, report


def _load_sandbox_config_source(source: SyncSource) -> tuple[list[Target], list[Target], SyncReport]:
    path = Path(source.path).expanduser().resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    enabled_actions = {
        str(item).strip()
        for item in ((payload.get("activity") or {}).get("enabled_actions") or [])
        if str(item).strip()
    }
    can_send = "send_message" in enabled_actions
    report = SyncReport(source_type=source.source_type, path=str(path), enabled=True)
    groups: list[Target] = []
    contacts: list[Target] = []

    for row in payload.get("allowlist_chats", []):
        if not source.include_groups:
            continue
        chat_id = _normalize_text(row.get("chat_id"))
        handle = _extract_handle(row.get("url"))
        if not chat_id or not handle:
            report.skipped.append({"entity_id": chat_id, "reason": "chat_url_has_no_supported_username"})
            continue
        groups.append(
            Target(
                target_id=chat_id,
                label=_normalize_text(row.get("title")) or chat_id,
                handle=handle,
                kind="group",
                source="sandbox_config",
                allowed_actions=("send_message",) if can_send else (),
                consent_confirmed=True,
            )
        )

    for row in payload.get("allowlist_contacts", []):
        if not source.include_contacts:
            continue
        contact_id = _normalize_text(row.get("contact_id"))
        username = _normalize_text(row.get("username"))
        if not contact_id or not username:
            report.skipped.append({"entity_id": contact_id, "reason": "contact_has_no_username"})
            continue
        contacts.append(
            Target(
                target_id=contact_id,
                label=_normalize_text(row.get("display_name")) or contact_id,
                handle=username,
                kind="contact",
                source="sandbox_config",
                allowed_actions=("send_message",) if can_send else (),
                consent_confirmed=True,
            )
        )

    report.group_count = len(groups)
    report.contact_count = len(contacts)
    return groups, contacts, report


def resolve_targets(config: ToolConfig) -> ResolvedTargets:
    groups = list(config.groups)
    contacts = list(config.contacts)
    reports: list[SyncReport] = []

    for source in config.sync_sources:
        if not source.enabled:
            reports.append(
                SyncReport(
                    source_type=source.source_type,
                    path=str(Path(source.path).expanduser()),
                    enabled=False,
                )
            )
            continue
        if source.source_type == "allowlist_csv":
            imported_groups, imported_contacts, report = _load_allowlist_source(source)
        elif source.source_type == "sandbox_config":
            imported_groups, imported_contacts, report = _load_sandbox_config_source(source)
        else:
            raise ValueError(f"unsupported sync source type: {source.source_type}")
        groups.extend(imported_groups)
        contacts.extend(imported_contacts)
        reports.append(report)

    return ResolvedTargets(
        groups=_merge_target_lists(groups),
        contacts=_merge_target_lists(contacts),
        reports=reports,
    )


def build_message_target_candidates(config: ToolConfig, resolved: ResolvedTargets) -> list[Target]:
    if config.message_policy.target_mode == "fixed":
        if not config.message_policy.target_username.strip():
            return []
        return [
            Target(
                target_id="message_policy_target",
                label=config.message_policy.target_username.strip(),
                handle=config.message_policy.target_username.strip(),
                kind="contact",
                source="message_policy",
                allowed_actions=("send_message",),
                consent_confirmed=True,
            )
        ]
    if config.message_policy.message_targets:
        if config.message_policy.target_mode == "rotating_all":
            return list(config.message_policy.message_targets)
        return [item for item in config.message_policy.message_targets if item.kind == "contact"]
    if config.message_policy.target_mode == "rotating_all":
        pool = [*resolved.contacts, *resolved.groups]
        return [item for item in pool if item.can_send_message()]
    return [item for item in resolved.contacts if item.can_send_message()]
