from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT_DIR / "extension" / "manifest.json"


class ExtensionManifestTests(unittest.TestCase):
    def test_manifest_declares_firefox_background_fallback(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

        self.assertEqual(manifest["manifest_version"], 3)

        background = manifest["background"]
        self.assertEqual(background["service_worker"], "background.js")
        self.assertEqual(background["scripts"], ["background.js"])
        self.assertEqual(background["type"], "module")
        self.assertIn("service_worker", background["preferred_environment"])
        self.assertIn("document", background["preferred_environment"])

        gecko = manifest["browser_specific_settings"]["gecko"]
        self.assertEqual(gecko["id"], "site-control-bridge@maxcorp.local")


if __name__ == "__main__":
    unittest.main()
