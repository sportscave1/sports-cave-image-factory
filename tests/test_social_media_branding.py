import io
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import social_media_branding as branding


def branding_plan(**overrides):
    values = {
        "content_format": "Story sequence",
        "label": "Frame 1",
        "headline": "WHEN RACING WAS RAW.",
        "subline": "THE RIVALS",
        "cta": "",
        "native_sticker_space": "none",
    }
    values.update(overrides)
    return branding.build_branding_plan(**values)


class SocialBrandAssetTests(unittest.TestCase):
    def test_verified_website_assets_and_brand_tokens_are_centralised(self):
        manifest = branding.brand_manifest()

        self.assertEqual(
            manifest["logo_asset"],
            "assets/sports-cave-logo-landscape-gold-transparent.webp",
        )
        self.assertEqual(manifest["logo_sha256"], branding.LOGO_SHA256)
        self.assertEqual(manifest["font_family"], "Montserrat")
        self.assertEqual(manifest["colours"]["near_black"], "#0B0B0D")
        self.assertEqual(manifest["colours"]["gold"], "#D4A54C")
        self.assertTrue(branding.require_brand_assets())

    def test_watermark_overlay_uses_pixels_from_the_exact_logo_asset(self):
        plan = branding_plan()
        overlay = branding.render_overlay(plan, mode="watermark")
        source = Image.open(branding.LOGO_ASSET_PATH).convert("RGBA")
        logo_width = int(
            plan["canvas"]["width"] * (plan["logo"]["width_percent"] / 100)
        )
        logo_height = int(source.height * (logo_width / source.width))
        expected = source.resize(
            (logo_width, logo_height),
            Image.Resampling.LANCZOS,
        )
        logo_x, logo_y = branding._logo_position(
            plan,
            expected.size,
            overlay.size,
        )
        actual = overlay.crop(
            (logo_x, logo_y, logo_x + logo_width, logo_y + logo_height)
        )

        self.assertEqual(actual.size, expected.size)
        self.assertLessEqual(
            max(
                abs(left - right)
                for left, right in zip(actual.tobytes(), expected.tobytes())
            ),
            1,
        )

    def test_image_export_produces_separate_srgb_clean_and_branded_files(self):
        source = Image.new("RGB", (320, 240), "#47515B")
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")
        plan = branding_plan(cta="SEE THE EDITION.")

        clean_data, clean_extension = branding.prepare_clean_asset(
            buffer.getvalue(),
            "png",
            plan,
        )
        branded_data, branded_extension = branding.compose_branded_asset(
            clean_data,
            clean_extension,
            plan,
        )
        clean = Image.open(io.BytesIO(clean_data))
        branded = Image.open(io.BytesIO(branded_data))

        self.assertEqual(clean_extension, "png")
        self.assertEqual(branded_extension, "png")
        self.assertEqual(clean.size, (1080, 1920))
        self.assertEqual(branded.size, clean.size)
        self.assertNotEqual(clean.tobytes(), branded.tobytes())
        self.assertTrue(clean.info.get("icc_profile"))
        self.assertTrue(branded.info.get("icc_profile"))

    def test_unverified_claim_prevents_branded_export(self):
        plan = branding_plan(
            publish_ready=False,
            blockers=("[VERIFY EDITION LIMIT]",),
        )
        source = Image.new("RGB", (1080, 1920), "#0B0B0D")
        buffer = io.BytesIO()
        source.save(buffer, format="PNG")
        clean_data, extension = branding.prepare_clean_asset(
            buffer.getvalue(),
            "png",
            plan,
        )

        with self.assertRaises(branding.SocialBrandClaimError):
            branding.compose_branded_asset(clean_data, extension, plan)

    def test_video_export_produces_clean_and_exactly_branded_mp4_files(self):
        executable = branding._ffmpeg_executable()
        plan = branding_plan(
            content_format="Reel",
            label="Reel master",
            cta="SEE THE EDITION.",
        )
        with tempfile.TemporaryDirectory(prefix="social-brand-test-") as temp:
            source_path = Path(temp) / "source.mp4"
            completed = subprocess.run(
                [
                    executable,
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=0x47515B:s=320x240:d=1",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    str(source_path),
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            self.assertEqual(
                completed.returncode,
                0,
                completed.stderr.decode("utf-8", errors="replace"),
            )
            clean_data, clean_extension = branding.prepare_clean_asset(
                source_path.read_bytes(),
                "mp4",
                plan,
            )
            branded_data, branded_extension = branding.compose_branded_asset(
                clean_data,
                clean_extension,
                plan,
            )

        self.assertEqual(clean_extension, "mp4")
        self.assertEqual(branded_extension, "mp4")
        self.assertGreater(len(clean_data), 1_000)
        self.assertGreater(len(branded_data), len(clean_data))
        self.assertNotEqual(clean_data, branded_data)


if __name__ == "__main__":
    unittest.main()
