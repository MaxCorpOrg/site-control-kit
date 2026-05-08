from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.telegram_gui.models import WorkspaceHealth
from scripts.telegram_gui.services.preflight import PreflightService


class PreflightServiceTests(unittest.TestCase):
    def test_security_mode_flags_default_token_as_warning(self) -> None:
        service = PreflightService(workspace_root=Path("/tmp/workspace"), default_token="local-bridge-quickstart-2026")
        self.assertEqual(service.security_mode(""), ("No token configured", "blocked"))
        self.assertEqual(service.security_mode("local-bridge-quickstart-2026"), ("Insecure local token", "warning"))
        self.assertEqual(service.security_mode("secure-token"), ("Local secure token", "ok"))

    def test_build_marks_fallback_surface_and_output_blockers(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace_root = Path(td) / "workspace"
            service = PreflightService(workspace_root=workspace_root, default_token="default-token")
            health = WorkspaceHealth(
                workspace_writable=True,
                runtime_writable=True,
                logs_writable=True,
                helper_available=False,
                collector_python_available=False,
                node_available=True,
                hub_reachable=False,
                stale_runtime_files=2,
                warning="Порт 8765 занят внешним process.",
            )
            info = service.build(
                surface_key="fallback",
                surface_label="Fallback surface",
                surface_badge="Fallback required",
                surface_reason="tdata недоступен; будет использован fallback adapter.",
                is_primary=False,
                tdata_ready=False,
                helper_ready=False,
                output_path=None,
                preset_key="quick_check",
                preset_label="Quick Check",
                history_limit="400",
                timeout_sec=300,
                resume_available=False,
                token="default-token",
                token_source="quickstart",
                workspace_health=health,
                connection_label="Hub ещё не подключён.",
                hub_token_status="foreign_mismatch",
                hub_token_detail="На :8765 уже живёт внешний hub/process с другим токеном.",
                hub_restart_available=False,
                notes=("collector helper недоступен",),
            )

        statuses = {item.key: item for item in info.statuses}
        self.assertEqual(statuses["hub"].state, "blocked")
        self.assertEqual(statuses["surface"].state, "blocked")
        self.assertEqual(statuses["output"].state, "blocked")
        self.assertEqual(statuses["security"].state, "warning")
        self.assertTrue(info.security_attention_required)
        self.assertTrue(info.security_setup_available)
        self.assertIn("quickstart fallback", info.security_detail)
        self.assertIn("внешний hub/process", info.security_detail)

    def test_build_marks_pending_surface_as_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace_root = Path(td) / "workspace"
            service = PreflightService(workspace_root=workspace_root, default_token="default-token")
            health = WorkspaceHealth(
                workspace_writable=True,
                runtime_writable=True,
                logs_writable=True,
                helper_available=True,
                collector_python_available=True,
                node_available=True,
                hub_reachable=False,
            )
            info = service.build(
                surface_key="pending",
                surface_label="Telegram pending",
                surface_badge="Surface pending",
                surface_reason="Профиль ещё не выбран.",
                is_primary=False,
                tdata_ready=False,
                helper_ready=True,
                output_path=None,
                preset_key="full_history",
                preset_label="Full History",
                history_limit="0",
                timeout_sec=None,
                resume_available=False,
                token="",
                token_source="missing",
                workspace_health=health,
                connection_label="Hub ещё не подключён.",
                hub_token_status="pending",
                hub_token_detail="Hub token state будет доступен после выбора профиля.",
                hub_restart_available=False,
                notes=("bootstrap pending",),
            )

        statuses = {item.key: item for item in info.statuses}
        self.assertEqual(statuses["surface"].state, "pending")
        self.assertEqual(statuses["hub"].state, "pending")
