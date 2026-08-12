import json
from pathlib import Path
import re
import tomllib
import unittest

from PIL import Image, ImageChops

import app_branding


ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "static"


class _ComponentsRecorder:
    def __init__(self):
        self.calls = []

    def html(self, body, **kwargs):
        self.calls.append((body, kwargs))


class AppInstallBrandingTests(unittest.TestCase):
    def test_manifest_has_portable_sports_cave_os_identity(self):
        manifest_path = STATIC_ROOT / "sports-cave-os-v1.webmanifest"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

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
        manifest = json.loads(
            (STATIC_ROOT / "sports-cave-os-v1.webmanifest").read_text(
                encoding="utf-8"
            )
        )
        declarations = {
            (icon["sizes"], icon["purpose"]): icon for icon in manifest["icons"]
        }

        expected_declarations = {
            ("192x192", "any"),
            ("512x512", "any"),
            ("512x512", "maskable"),
        }
        self.assertEqual(expected_declarations, set(declarations))
        for icon in manifest["icons"]:
            self.assertTrue(icon["src"].startswith("/app/static/"))
            icon_path = STATIC_ROOT / icon["src"].removeprefix("/app/static/")
            self.assertTrue(icon_path.is_file())
            with Image.open(icon_path) as image:
                size = int(icon["sizes"].split("x", 1)[0])
                self.assertEqual((size, size), image.size)
                self.assertEqual("image/png", icon["type"])

    def test_any_icons_are_exact_resizes_of_authoritative_webp(self):
        source_path = ROOT / "assets" / "sports-cave-os-app-icon.webp"
        with Image.open(source_path) as source_image:
            source = source_image.convert("RGBA")
            for size in (192, 512):
                expected = source.resize(
                    (size, size), Image.Resampling.LANCZOS
                )
                output_path = (
                    STATIC_ROOT
                    / "branding"
                    / f"sports-cave-os-icon-{size}-v1.png"
                )
                with Image.open(output_path) as output_image:
                    actual = output_image.convert("RGBA")
                self.assertEqual(expected.tobytes(), actual.tobytes())

    def test_maskable_icon_keeps_the_full_mark_inside_the_safe_zone(self):
        path = (
            STATIC_ROOT
            / "branding"
            / "sports-cave-os-icon-maskable-512-v1.png"
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

    def test_apple_touch_icon_exists_at_180_pixels(self):
        path = (
            STATIC_ROOT
            / "branding"
            / "sports-cave-os-apple-touch-icon-180-v1.png"
        )
        with Image.open(path) as image:
            self.assertEqual((180, 180), image.size)
            self.assertEqual("RGB", image.mode)

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

    def test_public_branding_urls_are_origin_relative(self):
        urls = (
            app_branding.APP_MANIFEST_URL,
            app_branding.APP_ICON_192_URL,
            app_branding.APP_ICON_512_URL,
            app_branding.APP_MASKABLE_ICON_URL,
            app_branding.APP_APPLE_TOUCH_ICON_URL,
        )

        for url in urls:
            self.assertTrue(url.startswith("/app/static/"))
            self.assertNotIn("://", url)


if __name__ == "__main__":
    unittest.main()
