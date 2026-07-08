from pathlib import Path
import tempfile
import unittest
import zipfile

import social_media_reels_studio_page as reels


ROOT = Path(__file__).resolve().parents[1]


class SocialMediaReelsStudioPageTests(unittest.TestCase):
    def test_app_sidebar_and_router_include_reels_studio_page(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")

        self.assertIn('"Social Media Reels Studio"', source)
        self.assertIn("get_social_media_reels_studio_page().render_page()", source)

    def test_video_filename_generator_for_required_handles(self):
        handles = [
            "roger-federer",
            "cristiano-ronaldo-black-framed-soccer-sports-wall-art",
            "legends-never-die-kobe-jordan",
            "mbappe-born-for-the-world-stage",
        ]

        for handle in handles:
            with self.subTest(handle=handle):
                self.assertEqual(
                    reels.video_filename(handle, "collector-admire", "v01", "final"),
                    f"{handle}__meta-reel__collector-admire__9x16__v01__final.mp4",
                )
                self.assertEqual(
                    reels.image_mockup_filename(handle, "wall-only"),
                    f"{handle}__mockup__wall-only__1x1__v01__final.png",
                )

    def test_handle_sanitizer_and_filename_status_version(self):
        self.assertEqual(reels.sanitize_handle("Mbappe Born For The World Stage!!"), "mbappe-born-for-the-world-stage")
        self.assertEqual(
            reels.video_filename("Roger Federer", "wall-admire", "2", "ad-test"),
            "roger-federer__meta-reel__wall-admire__9x16__v02__ad-test.mp4",
        )

    def test_zip_export_creates_required_folder_structure_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir)
            product = run_dir / "source" / "product-mockup-original.png"
            background = run_dir / "source" / "selected-background-original.jpg"
            mockup = run_dir / "social-media-mockups" / reels.image_mockup_filename("roger-federer", "collector-admire")
            video = run_dir / "social-media-reels" / reels.video_filename("roger-federer", "collector-admire")
            for path, payload in (
                (product, b"product"),
                (background, b"background"),
                (mockup, b"mockup"),
                (video, b"video"),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(payload)

            state = {
                "files": {
                    "product_mockup": {"path": str(product), "filename": product.name},
                    "selected_background": {"path": str(background), "filename": background.name},
                    "image_mockups": {
                        "collector-admire": {
                            "path": str(mockup),
                            "filename": mockup.name,
                            "original_name": "mockup.png",
                        }
                    },
                    "videos": {
                        "collector-admire": {
                            "path": str(video),
                            "filename": video.name,
                            "original_name": "video.mp4",
                            "version": "v01",
                            "status": "final",
                        }
                    },
                }
            }

            background_prompt = reels.build_background_finder_prompt(
                "roger-federer",
                "Roger Federer Wall Art",
                "Tennis",
                "Luxury collector room",
            )
            image_prompts = reels.build_image_prompts("roger-federer", "Roger Federer Wall Art", "Tennis", "")
            video_prompts = reels.build_video_prompts("roger-federer", "Roger Federer Wall Art", "Tennis")

            zip_path = reels.build_social_media_reels_zip(
                run_dir,
                "roger-federer",
                "Roger Federer Wall Art",
                "Tennis",
                state,
                background_prompt,
                image_prompts,
                video_prompts,
            )

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
                manifest = archive.read("manifest.json").decode("utf-8")

            self.assertIn("mockup-backgrounds/", names)
            self.assertIn("social-media-mockups/", names)
            self.assertIn("social-media-reels/", names)
            self.assertIn("social-media-video-content/", names)
            self.assertIn("sport-videos/", names)
            self.assertIn("mockup-backgrounds/roger-federer/product-mockup-original.png", names)
            self.assertIn("mockup-backgrounds/roger-federer/selected-background-original.jpg", names)
            self.assertIn("mockup-backgrounds/roger-federer/background-finder-prompt.txt", names)
            self.assertIn(f"social-media-mockups/roger-federer/{mockup.name}", names)
            self.assertIn("social-media-mockups/roger-federer/image-prompts.txt", names)
            self.assertIn(f"social-media-reels/roger-federer/{video.name}", names)
            self.assertIn(f"social-media-video-content/roger-federer/final/{video.name}", names)
            self.assertIn(f"sport-videos/tennis/roger-federer/{video.name}", names)
            self.assertIn("README-INSTRUCTIONS.txt", names)
            self.assertIn('"product_handle": "roger-federer"', manifest)


if __name__ == "__main__":
    unittest.main()
