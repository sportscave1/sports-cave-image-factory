import json
from pathlib import Path
import re
import tomllib
import unittest

from PIL import Image, ImageChops
from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route
from starlette.testclient import TestClient

import app_branding


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"


class _ComponentsRecorder:
    def __init__(self):
        self.calls = []

    def html(self, body, **kwargs):
        self.calls.append((body, kwargs))


class AppInstallBrandingTests(unittest.TestCase):
    def manifest(self):
        return json.loads(
            (STATIC_ROOT / "sports-cave-os-v1.webmanifest").read_text(
                encoding="utf-8"
            )
        )

    def test_manifest_has_portable_sports_cave_os_identity(self):
        manifest_path = STATIC_ROOT / "sports-cave-os-v1.webmanifest"
        manifest = self.manifest()

        self.assertEqual("Sports Cave OS", manifest["name"])
        self.assertEqual("Sports Cave OS", manifest["short_name"])
        self.assertEqual("/?page=dashboard", manifest["start_url"])
        self.assertEqual("/", manifest["scope"])
        self.assertEqual("standalone", manifest["display"])
        self.assertEqual("#171510", manifest["theme_color"])
        self.assertEqual("#FAF8F1", manifest["background_color"])
        manifest_source = manifest_path.read_text(encoding="utf-8")
        self.assertNotIn("onrender.com", manifest_source)
        self.assertNotIn("http://", manifest_source)
        self.assertNotIn("https://", manifest_source)

    def test_manifest_icons_exist_with_declared_sizes_and_purposes(self):
        manifest = self.manifest()
        declarations = {
            (icon["sizes"], icon["purpose"]): icon for icon in manifest["icons"]
        }

        expected_declarations = {
            ("192x192", "any"),
            ("512x512", "any"),
            ("512x512", "maskable"),
        }
        self.assertEqual(expected_declarations, set(declarations))
        self.assertEqual(3, len(manifest["icons"]))
        for icon in manifest["icons"]:
            self.assertTrue(icon["src"].startswith("/app/static/"))
            self.assertIn("-v2.png", icon["src"])
            icon_path = STATIC_ROOT / icon["src"].removeprefix("/app/static/")
            self.assertTrue(icon_path.is_file())
            with Image.open(icon_path) as image:
                size = int(icon["sizes"].split("x", 1)[0])
                self.assertEqual((size, size), image.size)
                self.assertEqual("image/png", icon["type"])

    def test_any_icons_are_exact_resizes_of_authoritative_webp(self):
        source_path = ROOT / "assets" / "sports-cave-os-app-icon.webp"
        self.assertEqual(
            "assets/sports-cave-os-app-icon.webp",
            app_branding.APP_ICON_SOURCE,
        )
        with Image.open(source_path) as source_image:
            source = source_image.convert("RGBA")
            for size in (192, 512):
                expected = source.resize(
                    (size, size), Image.Resampling.LANCZOS
                )
                output_path = (
                    STATIC_ROOT
                    / "branding"
                    / f"sports-cave-os-icon-{size}-v2.png"
                )
                with Image.open(output_path) as output_image:
                    actual = output_image.convert("RGBA")
                self.assertEqual(expected.tobytes(), actual.tobytes())

    def test_maskable_icon_keeps_the_full_mark_inside_the_safe_zone(self):
        path = (
            STATIC_ROOT
            / "branding"
            / "sports-cave-os-icon-maskable-512-v2.png"
        )
        with Image.open(path) as image:
            rgba = image.convert("RGBA")

        background = Image.new("RGB", rgba.size, (23, 21, 16))
        mark_bounds = ImageChops.difference(rgba.convert("RGB"), background).getbbox()
        self.assertIsNotNone(mark_bounds)

        left, top, right, bottom = mark_bounds
        for x, y in (
            (left, top),
            (right - 1, top),
            (left, bottom - 1),
            (right - 1, bottom - 1),
        ):
            distance = ((x - 256) ** 2 + (y - 256) ** 2) ** 0.5
            self.assertLessEqual(distance, 512 * 0.4)

    def test_maskable_icon_uses_the_exact_authoritative_artwork(self):
        with Image.open(ROOT / app_branding.APP_ICON_SOURCE) as source_image:
            source = source_image.convert("RGBA")
        expected = Image.new("RGBA", (512, 512), (23, 21, 16, 255))
        expected.alpha_composite(
            source.resize((352, 352), Image.Resampling.LANCZOS),
            (80, 80),
        )
        with Image.open(
            STATIC_ROOT
            / "branding"
            / "sports-cave-os-icon-maskable-512-v2.png"
        ) as output_image:
            actual = output_image.convert("RGBA")

        self.assertEqual(expected.tobytes(), actual.tobytes())

    def test_apple_touch_icon_exists_at_180_pixels(self):
        path = (
            STATIC_ROOT
            / "branding"
            / "sports-cave-os-apple-touch-icon-180-v2.png"
        )
        with Image.open(path) as image:
            self.assertEqual((180, 180), image.size)
            self.assertEqual("RGB", image.mode)

    def test_windows_and_png_fallback_icons_are_generated_from_the_source(self):
        png_path = STATIC_ROOT / "branding" / "sports-cave-os-favicon-32-v2.png"
        ico_path = STATIC_ROOT / "branding" / "sports-cave-os-favicon-v2.ico"
        tile_path = STATIC_ROOT / "branding" / "sports-cave-os-ms-tile-144-v2.png"

        with Image.open(ROOT / app_branding.APP_ICON_SOURCE) as source_image:
            source_rgba = source_image.convert("RGBA")
            expected_png = source_rgba.resize(
                (32, 32), Image.Resampling.LANCZOS
            )
        with Image.open(png_path) as png:
            self.assertEqual((32, 32), png.size)
            self.assertEqual(expected_png.tobytes(), png.convert("RGBA").tobytes())
        with Image.open(ico_path) as ico:
            self.assertTrue({(16, 16), (32, 32), (48, 48), (256, 256)}.issubset(ico.ico.sizes()))
            self.assertEqual(
                source_rgba.tobytes(),
                ico.convert("RGBA").tobytes(),
            )
        with Image.open(tile_path) as tile:
            self.assertEqual((144, 144), tile.size)
            self.assertEqual("RGB", tile.mode)

    def test_static_serving_is_enabled(self):
        config = tomllib.loads(
            (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        )
        self.assertIs(True, config["server"]["enableStaticServing"])

    def test_metadata_installer_targets_the_parent_head_idempotently(self):
        html = app_branding.install_metadata_html()

        self.assertIn("window.parent || window", html)
        self.assertIn("doc.head.querySelectorAll(selector)", html)
        self.assertIn("if (duplicate !== element) duplicate.remove()", html)
        self.assertIn('selector: \'link[rel="manifest"]\'', html)
        self.assertIn('selector: \'meta[name="theme-color"]\'', html)
        self.assertEqual(1, html.count('id: "sports-cave-os-manifest"'))
        self.assertEqual(1, html.count('id: "sports-cave-os-theme-color"'))
        self.assertIn(app_branding.APP_MANIFEST_URL, html)
        self.assertIn(app_branding.APP_THEME_COLOR, html)
        self.assertIn("doc.title = 'Sports Cave OS'", html)
        self.assertIn(app_branding.APP_FAVICON_ICO_URL, html)
        self.assertIn(app_branding.APP_FAVICON_PNG_URL, html)
        self.assertIn(app_branding.APP_MS_TILE_ICON_URL, html)

    def test_initial_document_metadata_is_exact_singular_and_idempotent(self):
        shell = """<!doctype html><html><head>
        <link rel="shortcut icon" href="./favicon.png" />
        <title>Streamlit</title>
        </head><body><div id="root"></div></body></html>"""

        once = app_branding.brand_initial_document(shell)
        twice = app_branding.brand_initial_document(once)

        self.assertEqual(once, twice)
        self.assertEqual(1, once.count("<title>Sports Cave OS</title>"))
        self.assertEqual(1, once.count('rel="manifest"'))
        self.assertEqual(1, once.count('name="application-name"'))
        self.assertEqual(1, once.count('name="apple-mobile-web-app-title"'))
        self.assertEqual(1, once.count('name="theme-color"'))
        self.assertNotIn("Streamlit</title>", once)
        self.assertNotIn("Sports Cave Image Factory", once)
        self.assertNotIn("./favicon.png", once)
        self.assertIn(app_branding.APP_FAVICON_ICO_URL, once)
        self.assertIn(app_branding.APP_MANIFEST_URL, once)

    def test_initial_document_middleware_brands_the_top_level_response(self):
        async def shell(_request):
            return HTMLResponse(
                "<html><head><title>Streamlit</title></head><body>App</body></html>"
            )

        starlette_app = Starlette(routes=[Route("/", shell)])
        branded_app = app_branding.InitialDocumentBrandingMiddleware(starlette_app)

        with TestClient(branded_app) as client:
            response = client.get("/")

        self.assertEqual(200, response.status_code)
        self.assertEqual(1, response.text.count("<title>Sports Cave OS</title>"))
        self.assertEqual(1, response.text.count('rel="manifest"'))
        self.assertNotIn("<title>Streamlit</title>", response.text)

    def test_public_root_branding_routes_are_unauthenticated_file_responses(self):
        async def shell(_request):
            return HTMLResponse("<html><head><title>Streamlit</title></head></html>")

        routes = [*app_branding.public_branding_routes(), Route("/", shell)]
        starlette_app = Starlette(routes=routes)
        with TestClient(starlette_app) as client:
            responses = {
                path: client.get(path)
                for path in (
                    "/favicon.ico",
                    "/favicon.png",
                    "/apple-touch-icon.png",
                    "/mstile-144x144.png",
                )
            }

        for path, response in responses.items():
            with self.subTest(path=path):
                self.assertEqual(200, response.status_code)
                self.assertTrue(response.headers["content-type"].startswith("image/"))
                self.assertNotIn(b"<html", response.content.lower())

    def test_metadata_component_has_no_visible_layout_height(self):
        components = _ComponentsRecorder()

        app_branding.render_install_metadata(components)

        self.assertEqual(1, len(components.calls))
        body, kwargs = components.calls[0]
        self.assertEqual(app_branding.install_metadata_html(), body)
        self.assertEqual({"height": 0, "width": 0}, kwargs)

    def test_app_sets_exact_title_before_installing_metadata(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        page_config_index = source.index("st.set_page_config(")
        metadata_index = source.index("app_branding.render_install_metadata(")
        first_streamlit_command = re.search(r"^st\.[A-Za-z_]", source, re.MULTILINE)

        self.assertIsNotNone(first_streamlit_command)
        self.assertEqual(page_config_index, first_streamlit_command.start())
        self.assertIn('page_title="Sports Cave OS"', source)
        self.assertLess(page_config_index, metadata_index)
        self.assertEqual("Sports Cave OS", app_branding.APP_NAME)

    def test_production_server_wraps_streamlit_with_initial_branding(self):
        source = (ROOT / "sports_cave_server.py").read_text(encoding="utf-8")

        self.assertIn("app_branding.public_branding_routes()", source)
        self.assertIn('streamlit_app = App("app.py", routes=routes)', source)
        self.assertIn(
            "app = app_branding.InitialDocumentBrandingMiddleware(streamlit_app)",
            source,
        )

    def test_public_branding_urls_are_origin_relative(self):
        urls = (
            app_branding.APP_MANIFEST_URL,
            app_branding.APP_FAVICON_ICO_URL,
            app_branding.APP_FAVICON_PNG_URL,
            app_branding.APP_ICON_192_URL,
            app_branding.APP_ICON_512_URL,
            app_branding.APP_MASKABLE_ICON_URL,
            app_branding.APP_APPLE_TOUCH_ICON_URL,
            app_branding.APP_MS_TILE_ICON_URL,
        )

        for url in urls:
            self.assertTrue(url.startswith("/"))
            self.assertNotIn("://", url)

    def test_user_facing_install_branding_never_uses_legacy_or_generic_names(self):
        branding_sources = (
            (ROOT / "app_branding.py").read_text(encoding="utf-8"),
            (ROOT / "sports_cave_server.py").read_text(encoding="utf-8"),
            (STATIC_ROOT / "sports-cave-os-v1.webmanifest").read_text(
                encoding="utf-8"
            ),
        )

        for source in branding_sources:
            self.assertNotIn("Sports Cave Image Factory", source)
            self.assertNotIn("<title>Streamlit</title>", source)


if __name__ == "__main__":
    unittest.main()
