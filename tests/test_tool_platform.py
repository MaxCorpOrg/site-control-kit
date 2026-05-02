from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tool_platform.catalog import find_action, find_tool, load_catalog
from tool_platform.cli import execute_action


class ToolPlatformCatalogTests(unittest.TestCase):
    def _write_json(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def test_load_catalog_resolves_relative_and_absolute_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            embedded_dir = root / "embedded_tool"
            external_dir = root / "external_tool"
            registry_dir = root / "registry"
            embedded_dir.mkdir()
            external_dir.mkdir()
            registry_dir.mkdir()

            embedded_manifest = embedded_dir / "tool_manifest.json"
            external_manifest = external_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            self._write_json(
                embedded_manifest,
                {
                    "schema_version": 1,
                    "tool_id": "embedded_tool",
                    "display_name": "Embedded Tool",
                    "root_dir": ".",
                    "docs": [{"doc_id": "readme", "label": "README", "path": "README.md"}],
                    "actions": [
                        {
                            "action_id": "help",
                            "label": "Help",
                            "argv": ["echo", "embedded"],
                            "workdir": ".",
                        }
                    ],
                },
            )
            self._write_json(
                external_manifest,
                {
                    "schema_version": 1,
                    "tool_id": "external_tool",
                    "display_name": "External Tool",
                    "root_dir": ".",
                    "actions": [
                        {
                            "action_id": "help",
                            "label": "Help",
                            "argv": ["echo", "external"],
                            "workdir": ".",
                        }
                    ],
                },
            )
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "platform_name": "Test Platform",
                    "tools": [
                        {
                            "manifest_path": "../embedded_tool/tool_manifest.json",
                            "enabled": True,
                            "source_label": "embedded",
                        },
                        {
                            "manifest_path": str(external_manifest),
                            "enabled": True,
                            "source_label": "external",
                        },
                    ],
                },
            )

            catalog = load_catalog(registry_path)

            self.assertEqual(catalog.platform_name, "Test Platform")
            self.assertEqual([tool.tool_id for tool in catalog.tools], ["embedded_tool", "external_tool"])
            embedded_tool = find_tool(catalog, "embedded_tool")
            self.assertEqual(embedded_tool.docs[0].path, embedded_dir / "README.md")
            self.assertEqual(embedded_tool.source_label, "embedded")
            external_tool = find_tool(catalog, "external_tool")
            self.assertEqual(external_tool.source_label, "external")

    def test_duplicate_tool_ids_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            registry_dir = root / "registry"
            registry_dir.mkdir()
            tool_a_dir = root / "tool_a"
            tool_b_dir = root / "tool_b"
            tool_a_dir.mkdir()
            tool_b_dir.mkdir()
            tool_a_manifest = tool_a_dir / "tool_manifest.json"
            tool_b_manifest = tool_b_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            manifest_payload = {
                "schema_version": 1,
                "tool_id": "duplicate_id",
                "display_name": "Duplicate",
                "root_dir": ".",
                "actions": [],
            }
            self._write_json(tool_a_manifest, manifest_payload)
            self._write_json(tool_b_manifest, manifest_payload)
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "tools": [
                        {"manifest_path": str(tool_a_manifest), "enabled": True},
                        {"manifest_path": str(tool_b_manifest), "enabled": True},
                    ],
                },
            )

            with self.assertRaisesRegex(ValueError, "duplicate tool_id"):
                load_catalog(registry_path)

    def test_execute_action_dry_run_returns_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            manifest_dir = root / "tool"
            registry_dir = root / "registry"
            manifest_dir.mkdir()
            registry_dir.mkdir()
            manifest_path = manifest_dir / "tool_manifest.json"
            registry_path = registry_dir / "tools.json"

            self._write_json(
                manifest_path,
                {
                    "schema_version": 1,
                    "tool_id": "sample_tool",
                    "display_name": "Sample Tool",
                    "root_dir": ".",
                    "actions": [
                        {
                            "action_id": "echo_help",
                            "label": "Echo",
                            "argv": ["echo", "hello"],
                            "workdir": ".",
                        }
                    ],
                },
            )
            self._write_json(
                registry_path,
                {
                    "schema_version": 1,
                    "tools": [{"manifest_path": str(manifest_path), "enabled": True}],
                },
            )

            catalog = load_catalog(registry_path)
            tool = find_tool(catalog, "sample_tool")
            action = find_action(tool, "echo_help")
            result = execute_action(action, dry_run=True)

            self.assertEqual(result["status"], "dry_run")
            self.assertIn("echo hello", result["command"])


if __name__ == "__main__":
    unittest.main()
