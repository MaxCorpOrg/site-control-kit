from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import check_docs


class DocumentationChecksTests(unittest.TestCase):
    def test_current_versions_and_cli_contract_are_documented(self) -> None:
        self.assertEqual([], check_docs.check_versions())
        self.assertEqual([], check_docs.check_required_cli_commands())
        self.assertEqual([], check_docs.check_documented_cli_syntax())

    def test_all_working_directories_have_meaningful_agent_instructions(self) -> None:
        self.assertEqual([], check_docs.check_agent_instructions())

    def test_broken_relative_link_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "guide.md"
            path.write_text("[нет файла](missing.md)\n", encoding="utf-8")
            with patch.object(check_docs, "ROOT", Path(tmp)):
                findings = check_docs.check_links(path)
        self.assertEqual("broken_link", findings[0]["kind"])
        self.assertEqual("missing.md", findings[0]["target"])

    def test_cli_line_parser_accepts_module_and_console_entrypoints(self) -> None:
        self.assertEqual(
            ["browser", "set-text", "--label", "Имя", "Анна"],
            check_docs._cli_args_from_line(
                'PYTHONPATH="$PWD" python3 -m webcontrol browser set-text --label "Имя" "Анна"'
            ),
        )
        self.assertEqual(
            ["session", "lock", "значение", "--tab-id", "1", "--client-id", "значение"],
            check_docs._cli_args_from_line(
                "sitectl session lock <session-id> --tab-id <tab-id> --client-id <client-id>"
            ),
        )

    def test_missing_agent_instruction_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Назначение\nПроверка, ограничения и частые ошибки.\n",
                encoding="utf-8",
            )
            (root / "code").mkdir()
            with (
                patch.object(check_docs, "ROOT", root),
                patch.object(check_docs, "WORKING_DIRECTORIES", ("code",)),
            ):
                findings = check_docs.check_agent_instructions()
        self.assertTrue(any(item["kind"] == "missing_agent_instruction" for item in findings))


if __name__ == "__main__":
    unittest.main()
