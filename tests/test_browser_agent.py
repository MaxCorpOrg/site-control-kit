from __future__ import annotations

import unittest

from webcontrol.browser_agent import (
    WAIT_STATES,
    agent_api_schema,
    build_locator,
)
from webcontrol.cli import build_parser


class BrowserAgentContractTests(unittest.TestCase):
    def test_build_role_locator_with_accessible_name(self) -> None:
        locator = build_locator(role="button", name="Save", exact=True)
        self.assertEqual(
            locator,
            {
                "strategy": "role",
                "value": "button",
                "name": "Save",
                "exact": True,
            },
        )

    def test_build_ref_locator_with_nth_is_supported_but_validated(self) -> None:
        locator = build_locator(ref="e12")
        self.assertEqual(locator["strategy"], "ref")
        self.assertEqual(locator["value"], "e12")

        with self.assertRaisesRegex(ValueError, "--nth"):
            build_locator(selector="button", nth=-1)

    def test_build_locator_requires_exactly_one_strategy(self) -> None:
        with self.assertRaisesRegex(ValueError, "Exactly one locator"):
            build_locator()
        with self.assertRaisesRegex(ValueError, "Exactly one locator"):
            build_locator(selector="button", text="Save")

    def test_name_is_only_valid_for_role(self) -> None:
        with self.assertRaisesRegex(ValueError, "--name"):
            build_locator(selector="button", name="Save")

    def test_agent_schema_is_versioned_and_lists_core_commands(self) -> None:
        schema = agent_api_schema()
        self.assertEqual(schema["schema_version"], "1.0")
        self.assertEqual(schema["wait_states"], list(WAIT_STATES))
        self.assertIn("snapshot", schema["commands"])
        self.assertIn("smart_click", schema["commands"])
        self.assertIn("wait_for", schema["commands"])
        self.assertTrue(schema["compatibility"]["legacy_css_commands"])

    def test_cli_parses_semantic_agent_commands(self) -> None:
        parser = build_parser()
        click = parser.parse_args(
            [
                "browser",
                "--tab-id",
                "42",
                "smart-click",
                "--role",
                "button",
                "--name",
                "Save",
                "--exact",
            ]
        )
        self.assertEqual(click.browser_action, "smart-click")
        self.assertEqual(click.role, "button")
        self.assertEqual(click.name, "Save")

        wait = parser.parse_args(
            [
                "browser",
                "wait-for",
                "--test-id",
                "status",
                "--state",
                "text",
                "--expected-text",
                "Ready",
            ]
        )
        self.assertEqual(wait.browser_action, "wait-for")
        self.assertEqual(wait.test_id, "status")
        self.assertEqual(wait.expected_text, "Ready")


if __name__ == "__main__":
    unittest.main()
