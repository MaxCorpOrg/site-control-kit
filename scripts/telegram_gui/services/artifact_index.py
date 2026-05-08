from __future__ import annotations

from pathlib import Path

from ..models import ArtifactBundle, ExportResult


def append_index_entry(
    *,
    index_path: Path,
    created_at: str,
    account_label: str,
    chat_title: str,
    chat_ref: str,
    preset_label: str,
    surface_badge: str,
    status: str,
    artifacts: ArtifactBundle,
) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"## {created_at}",
        f"Аккаунт: `{account_label}`",
        f"Чат: `{chat_title or chat_ref}`",
        f"Chat ref: `{chat_ref}`",
        f"Preset: `{preset_label}`",
        f"Surface: `{surface_badge}`",
        f"Status: `{status}`",
    ]
    for label, path in artifacts.entries():
        lines.append(f"{label}: `{path}`")
    entry_text = "\n".join(lines).rstrip() + "\n"
    if index_path.exists():
        previous = index_path.read_text(encoding="utf-8").rstrip()
        prefix = f"{previous}\n\n" if previous else ""
        index_path.write_text(prefix + entry_text, encoding="utf-8")
        return
    index_path.write_text("# Telegram Export Index\n\n" + entry_text, encoding="utf-8")


def usernames_json_for_output(output_path: Path) -> Path | None:
    candidate = output_path.with_name(f"{output_path.stem}_usernames.json")
    return candidate if candidate.exists() else None


def build_artifact_bundle(result: ExportResult) -> ArtifactBundle:
    return ArtifactBundle(
        markdown=result.output_path,
        usernames_txt=result.usernames_txt,
        usernames_json=result.usernames_json or usernames_json_for_output(result.output_path),
        safe_txt=result.safe_txt,
        safe_md=result.safe_md,
        run_log=result.log_path,
        action_log=result.action_log_path,
    )
