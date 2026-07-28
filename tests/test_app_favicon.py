from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class AppFaviconTests(unittest.TestCase):
    def test_app_uses_sports_cave_gold_favicon_asset(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        favicon = ROOT / "assets" / "sports-cave-sc-gold-favicon.svg"

        self.assertTrue(favicon.is_file())
        self.assertIn("APP_FAVICON_PATH", source)
        self.assertIn('"assets" / "sports-cave-sc-gold-favicon.svg"', source)
        self.assertIn("page_icon=str(APP_FAVICON_PATH)", source)
        self.assertIn("Sports Cave SC gold favicon", favicon.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
