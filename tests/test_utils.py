from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from webcontrol.utils import dump_json


class WebcontrolUtilsTests(unittest.TestCase):
    def test_dump_json_escapes_surrogate_code_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state.json"
            dump_json(path, {"title": "\ud83e", "ok": True})

            raw = path.read_text(encoding="utf-8")
            self.assertIn("\\ud83e", raw)

            payload = json.loads(raw)
            self.assertEqual(payload["title"], "\ud83e")
            self.assertTrue(payload["ok"])


if __name__ == "__main__":
    unittest.main()
