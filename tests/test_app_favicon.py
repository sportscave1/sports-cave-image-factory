from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AppFaviconTests(unittest.TestCase):
    def test_app_uses_sports_cave_os_icon_asset(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        icon = ROOT / "assets" / "sports-cave-os-app-icon.webp"

        self.assertTrue(icon.is_file())
        self.assertTrue(icon.read_bytes().startswith(b"RIFF"))
        self.assertIn("APP_ICON_PATH", source)
        self.assertIn("APP_FAVICON_PATH", source)
        self.assertIn('"assets" / "sports-cave-os-app-icon.webp"', source)
        self.assertIn("APP_FAVICON_PATH = APP_ICON_PATH", source)
        self.assertIn("page_icon=str(APP_FAVICON_PATH)", source)
        self.assertIn("asset_data_uri(str(APP_ICON_PATH))", source)
        self.assertIn('class="sc-sidebar-logo"', source)
        self.assertIn("SPORTS CAVE OS", source)
        self.assertIn("OPERATIONS SYSTEM", source)


if __name__ == "__main__":
    unittest.main()
