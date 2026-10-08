"""All registered destinations dispatch only their selected renderer, offline."""
import ast
from pathlib import Path
from types import SimpleNamespace
import time
import unittest
from unittest.mock import patch

import ads_navigation
import analytics_navigation
import os_accounts
import seo_navigation
import social_media


class RouteIsolationTests(unittest.TestCase):
    def test_every_registered_route_dispatches_once_without_other_page_loads(self):
        source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == "render_selected_page")
        calls = []

        class Page:
            def __getattr__(self, name):
                return lambda *args, **kwargs: calls.append(name)

        page = Page()
        namespace = dict(time=time, os_accounts=os_accounts, social_media=social_media,
                         analytics_nav=analytics_navigation, seo_nav=seo_navigation, ads_nav=ads_navigation,
                         current_os_user=lambda: {"id": "fixture", "role": "admin"},
                         safe_startup_print=lambda *_: None, prompt_editing_allowed=lambda: False,
                         set_current_page=lambda *a, **kw: calls.append("redirect"),
                         st=SimpleNamespace(rerun=lambda: None))
        for name in (n.id for n in ast.walk(node) if isinstance(n, ast.Name)):
            if name.startswith("get_") and name != "get_current_page": namespace[name] = lambda: page
            if name.startswith("render_") and name != "render_selected_page": namespace[name] = lambda *a, **kw: calls.append("render")
        exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
        modules = {name: page for name in ("image_protection_ui", "wall_preview_inbox", "reviews_page", "crm_page")}
        modules["social_media_ui"] = SimpleNamespace(inject_styles=lambda: None)
        with patch.dict("sys.modules", modules):
            for route in [p["route"] for p in os_accounts.PAGE_REGISTRY] + ["Settings", "Marketing Factory"]:
                with self.subTest(route=route):
                    calls.clear()
                    namespace["render_selected_page"](route)
                    self.assertEqual(len(calls), 1, calls)


if __name__ == "__main__": unittest.main()
