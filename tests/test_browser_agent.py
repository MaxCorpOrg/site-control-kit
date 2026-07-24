from __future__ import annotations

import unittest

from webcontrol.browser_agent import agent_api_schema, build_locator


class BrowserAgentContractTests(unittest.TestCase):
    def test_locator_accepts_frame_scoped_reference(self) -> None:
        locator = build_locator(ref="f12:e7", frame_id=12)
        self.assertEqual(locator["strategy"], "ref")
        self.assertEqual(locator["frame_id"], 12)

    def test_locator_requires_one_strategy(self) -> None:
        with self.assertRaises(ValueError):
            build_locator(selector="#save", role="button")

    def test_schema_describes_reliable_delivery_and_frames(self) -> None:
        schema = agent_api_schema()
        self.assertEqual(schema["protocol_version"], "2.0")
        self.assertIn("dead_letter", schema["delivery"]["states"])
        self.assertIn("delivery_id", schema["delivery"]["identifiers"])
        self.assertIn("frame_id", schema["frames"]["strategies"])


if __name__ == "__main__":
    unittest.main()
