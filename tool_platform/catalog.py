from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .platform_adapters import current_platform_id, get_platform_adapter
from .telegram_runtime import repo_root


DEFAULT_REGISTRY_PATH = (
    repo_root()
    / "tools"
    / "telegram"
    / "platform"
    / "registry"
    / "tools.json"
)


@dataclass(frozen=True)
class ToolDoc:
    doc_id: str
    label: str
    path: Path


@dataclass(frozen=True)
class ToolAction:
    action_id: str
    label: str
    description: str
    argv: tuple[str, ...]
    workdir: Path
    capture_output: bool = True


@dataclass(frozen=True)
class ToolManifest:
    tool_id: str
    display_name: str
    description: str
    kind: str
    standalone: bool
    root_dir: Path
    manifest_path: Path
    docs: tuple[ToolDoc, ...]
    actions: tuple[ToolAction, ...]
    capabilities: tuple[str, ...]
    tags: tuple[str, ...]
    artifacts: dict[str, str]
    supported_platforms: tuple[str, ...]
    required_capabilities: tuple[str, ...]
    degraded_modes: dict[str, str]
    source_label: str


@dataclass(frozen=True)
class ToolCatalog:
    registry_path: Path
    platform_name: str
    tools: tuple[ToolManifest, ...]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _resolve_path(base_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (base_dir / candidate).resolve()


def _load_docs(manifest_path: Path, payload: list[Any]) -> tuple[ToolDoc, ...]:
    docs: list[ToolDoc] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"{manifest_path}: docs entries must be objects")
        raw_path = str(item["path"])
        docs.append(
            ToolDoc(
                doc_id=str(item.get("doc_id") or item.get("id") or Path(raw_path).stem),
                label=str(item.get("label") or raw_path),
                path=_resolve_path(manifest_path.parent, raw_path),
            )
        )
    return tuple(docs)


def _load_actions(
    manifest_path: Path,
    default_root_dir: Path,
    payload: list[Any],
) -> tuple[ToolAction, ...]:
    actions: list[ToolAction] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError(f"{manifest_path}: actions entries must be objects")
        argv = tuple(str(part) for part in item["argv"])
        raw_workdir = str(item.get("workdir", default_root_dir))
        actions.append(
            ToolAction(
                action_id=str(item["action_id"]),
                label=str(item.get("label") or item["action_id"]),
                description=str(item.get("description", "")),
                argv=argv,
                workdir=_resolve_path(manifest_path.parent, raw_workdir),
                capture_output=bool(item.get("capture_output", True)),
            )
        )
    return tuple(actions)


def load_tool_manifest(manifest_path: str | Path, source_label: str = "registry") -> ToolManifest:
    resolved_manifest_path = Path(manifest_path).expanduser().resolve()
    payload = _load_json(resolved_manifest_path)
    root_dir = _resolve_path(
        resolved_manifest_path.parent,
        str(payload.get("root_dir", ".")),
    )
    docs = _load_docs(resolved_manifest_path, list(payload.get("docs", [])))
    actions = _load_actions(
        resolved_manifest_path,
        root_dir,
        list(payload.get("actions", [])),
    )
    return ToolManifest(
        tool_id=str(payload["tool_id"]),
        display_name=str(payload["display_name"]),
        description=str(payload.get("description", "")),
        kind=str(payload.get("kind", "tool")),
        standalone=bool(payload.get("standalone", False)),
        root_dir=root_dir,
        manifest_path=resolved_manifest_path,
        docs=docs,
        actions=actions,
        capabilities=tuple(str(item) for item in payload.get("capabilities", [])),
        tags=tuple(str(item) for item in payload.get("tags", [])),
        artifacts={str(key): str(value) for key, value in payload.get("artifacts", {}).items()},
        supported_platforms=tuple(str(item) for item in payload.get("supported_platforms", [])),
        required_capabilities=tuple(str(item) for item in payload.get("required_capabilities", [])),
        degraded_modes={str(key): str(value) for key, value in payload.get("degraded_modes", {}).items()},
        source_label=source_label,
    )


def load_catalog(registry_path: str | Path = DEFAULT_REGISTRY_PATH) -> ToolCatalog:
    resolved_registry_path = Path(registry_path).expanduser().resolve()
    payload = _load_json(resolved_registry_path)
    tools: list[ToolManifest] = []
    for entry in payload.get("tools", []):
        if not isinstance(entry, dict):
            raise ValueError(f"{resolved_registry_path}: tool entries must be objects")
        if not entry.get("enabled", True):
            continue
        tools.append(
            load_tool_manifest(
                _resolve_path(resolved_registry_path.parent, str(entry["manifest_path"])),
                source_label=str(entry.get("source_label", "registry")),
            )
        )
    catalog = ToolCatalog(
        registry_path=resolved_registry_path,
        platform_name=str(payload.get("platform_name", "Telegram Control Center")),
        tools=tuple(tools),
    )
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: ToolCatalog) -> None:
    seen_ids: set[str] = set()
    known_platforms = {"linux", "windows", "macos"}
    for tool in catalog.tools:
        if tool.tool_id in seen_ids:
            raise ValueError(f"duplicate tool_id in catalog: {tool.tool_id}")
        seen_ids.add(tool.tool_id)
        for platform_id in tool.supported_platforms:
            if platform_id not in known_platforms:
                raise ValueError(f"unknown platform in tool {tool.tool_id}: {platform_id}")
        for platform_id in tool.degraded_modes:
            if platform_id not in known_platforms:
                raise ValueError(f"unknown degraded_modes platform in tool {tool.tool_id}: {platform_id}")
        action_ids: set[str] = set()
        for action in tool.actions:
            if action.action_id in action_ids:
                raise ValueError(
                    f"duplicate action_id for tool {tool.tool_id}: {action.action_id}"
                )
            action_ids.add(action.action_id)


def find_tool(catalog: ToolCatalog, tool_id: str) -> ToolManifest:
    for tool in catalog.tools:
        if tool.tool_id == tool_id:
            return tool
    raise KeyError(f"unknown tool_id: {tool_id}")


def find_action(tool: ToolManifest, action_id: str) -> ToolAction:
    for action in tool.actions:
        if action.action_id == action_id:
            return action
    raise KeyError(f"unknown action_id for {tool.tool_id}: {action_id}")


def catalog_to_dict(catalog: ToolCatalog) -> dict[str, Any]:
    return {
        "registry_path": str(catalog.registry_path),
        "platform_name": catalog.platform_name,
        "tools": [
            {
                "tool_id": tool.tool_id,
                "display_name": tool.display_name,
                "description": tool.description,
                "kind": tool.kind,
                "standalone": tool.standalone,
                "root_dir": str(tool.root_dir),
                "manifest_path": str(tool.manifest_path),
                "source_label": tool.source_label,
                "capabilities": list(tool.capabilities),
                "tags": list(tool.tags),
                "artifacts": dict(tool.artifacts),
                "supported_platforms": list(tool.supported_platforms),
                "required_capabilities": list(tool.required_capabilities),
                "degraded_modes": dict(tool.degraded_modes),
                "docs": [
                    {
                        "doc_id": doc.doc_id,
                        "label": doc.label,
                        "path": str(doc.path),
                    }
                    for doc in tool.docs
                ],
                "actions": [
                    {
                        "action_id": action.action_id,
                        "label": action.label,
                        "description": action.description,
                        "argv": list(action.argv),
                        "workdir": str(action.workdir),
                        "capture_output": action.capture_output,
                    }
                    for action in tool.actions
                ],
            }
            for tool in catalog.tools
        ],
    }


def tool_platform_support(tool: ToolManifest, platform_id: str | None = None) -> dict[str, Any]:
    current_id = platform_id or current_platform_id()
    adapter = get_platform_adapter(current_id)
    capability_map = adapter.capabilities()
    required = list(tool.required_capabilities)
    missing = [
        capability
        for capability in required
        if not bool((capability_map.get(capability) or {}).get("available"))
    ]
    platform_supported = not tool.supported_platforms or current_id in tool.supported_platforms
    return {
        "platform_id": current_id,
        "platform_supported": platform_supported,
        "missing_capabilities": missing,
        "supported": platform_supported and not missing,
        "degraded_mode": tool.degraded_modes.get(current_id, ""),
    }
