"""Focused verified-source tests. No application execution or active companion calls."""
import json
from pathlib import Path
import shutil
import tempfile
import time
import unittest
import source_navigation as nav

ROOT = Path(__file__).resolve().parents[2]

class NavigationTests(unittest.TestCase):
    def test_crm_static_route_sequence(self):
        model = nav.page_model(ROOT, "crm_campaigns_manage", "test", 1)
        self.assertIn("crm_page.py", [r["path"] for r in model["files"]])
        self.assertIsNotNone(model["primary"])

    def test_page_filtering_and_primary(self):
        orders = nav.page_model(ROOT, "orders", "test", 1)
        home = nav.page_model(ROOT, "dashboard", "test", 1)
        self.assertEqual(orders["primary"]["path"], "orders_page.py")
        self.assertIn("orders_page.css", [r["path"] for r in orders["files"]])
        self.assertNotIn("orders_page.css", [r["path"] for r in home["files"]])
        self.assertEqual(home["primary"]["path"], "app.py")

    def test_orders_key_with_form_context(self):
        hit = nav.resolve(ROOT, "orders", {"kind":"input","streamlit_key":"orders_search_text",
                         "streamlit_keys":["orders_search_text","orders-search-form"]}, "test", 1)
        self.assertEqual(hit["location"]["path"], "orders_page.py")
        self.assertTrue(hit["exact"])
        lines = (ROOT/"orders_page.py").read_text(encoding="utf-8").splitlines()
        self.assertIn("text_input", "\n".join(lines[hit["location"]["line"]-1:hit["location"]["end_line"]]))

    def test_table_and_ambiguous_fallback(self):
        hit = nav.resolve(ROOT, "orders", {"kind":"table","streamlit_key":"orders-table"}, "test", 1)
        self.assertEqual(hit["location"]["path"], "orders_page.py")
        self.assertFalse(hit["exact"])
        self.assertIn("enclosing",hit["reason"])
        fallback = nav.resolve(ROOT,"ads",{"kind":"section","text":"Unmapped synthetic card"},"test",1)
        self.assertFalse(fallback["exact"])
        self.assertEqual(fallback["location"]["path"], "ads_page.py")
        self.assertIn("unavailable", fallback["reason"])

    def test_signin_setting_and_panel(self):
        hit = nav.resolve(ROOT,"__signin__",{"component":"title"},"test",1)
        self.assertTrue(hit["exact"])
        self.assertEqual(hit["location"]["path"],"signin_presentation.py")
        panel = nav.resolve(ROOT,"__signin__",{"component":"panel"},"test",1)
        self.assertEqual(panel["location"]["path"],"components/sign_in/presentation.html")
        self.assertTrue(panel["exact"])

    def test_legacy_signin_no_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in ["app.py","os_accounts.py","social_media.py","ads_navigation.py","analytics_navigation.py","seo_navigation.py","crm_navigation.py"]:
                shutil.copy2(ROOT/file,root/file)
            before = (root/"app.py").read_bytes()
            model = nav.page_model(root,"__signin__","legacy",8)
            self.assertTrue(model["limitations"])
            self.assertEqual(model["primary"]["path"],"app.py")
            self.assertEqual(before,(root/"app.py").read_bytes())

    def test_cache_invalidation_external_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for file in ["app.py","os_accounts.py","social_media.py","ads_navigation.py","analytics_navigation.py","seo_navigation.py","crm_navigation.py","orders_page.py","orders_page.css"]:
                shutil.copy2(ROOT/file,root/file)
            old=nav.page_model(root,"orders","cache",1)
            path=root/"orders_page.css";path.write_text(path.read_text(encoding="utf-8")+"\n/* external edit */\n",encoding="utf-8")
            new=nav.page_model(root,"orders","cache",1)
            old_hash=next(r["hash"] for r in old["files"] if r["path"]=="orders_page.css")
            new_hash=next(r["hash"] for r in new["files"] if r["path"]=="orders_page.css")
            self.assertNotEqual(old_hash,new_hash)

if __name__ == "__main__":
    unittest.main()

