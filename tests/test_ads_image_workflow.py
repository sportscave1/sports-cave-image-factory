from datetime import datetime, timezone
import io
import unittest
from unittest.mock import patch

from PIL import Image

import ads_image_workflow
import ads_page


def image_bytes(image_format="PNG", size=(96, 96), color=(34, 68, 102), *, exif=None):
    buffer = io.BytesIO()
    image = Image.new("RGB", size, color)
    save_options = {"exif": exif} if exif is not None else {}
    image.save(buffer, format=image_format, **save_options)
    image.close()
    return buffer.getvalue()


def processed_slots(campaign_type):
    source = image_bytes()
    return {
        slot["id"]: {
            **ads_image_workflow.optimize_meta_image(
                source,
                original_name=f"{slot['id']}.png",
            ),
            "slot_id": slot["id"],
            "label": slot["label"],
            "position": slot["position"],
            "valid": True,
            "error": "",
        }
        for slot in ads_image_workflow.campaign_image_slots(campaign_type)
    }


class AdsImageProcessingTests(unittest.TestCase):
    def test_campaign_slot_counts_are_exact(self):
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Carousel")],
            ["Carousel 1", "Carousel 2", "Carousel 3", "Carousel 4", "Carousel 5"],
        )
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Instant Experience")],
            ["Instant Experience Image"],
        )
        self.assertEqual(ads_image_workflow.campaign_image_slots("Single Image / Video"), ())

    def test_jpeg_png_and_webp_become_verified_srgb_1080_jpegs(self):
        for image_format in ("JPEG", "PNG", "WEBP"):
            with self.subTest(image_format=image_format):
                result = ads_image_workflow.optimize_meta_image(
                    image_bytes(image_format),
                    original_name=f"source.{image_format.casefold()}",
                )
                with Image.open(io.BytesIO(result["data"])) as output:
                    output.load()
                    self.assertEqual(output.format, "JPEG")
                    self.assertEqual(output.mode, "RGB")
                    self.assertEqual(output.size, (1080, 1080))
                    self.assertTrue(output.info.get("icc_profile"))
                    self.assertTrue(output.info.get("progressive") or output.info.get("progression"))
                    self.assertEqual(len(output.getexif()), 0)

    def test_corrupt_unsupported_and_non_square_images_are_rejected(self):
        with self.assertRaisesRegex(ads_image_workflow.AdsImageValidationError, "corrupt"):
            ads_image_workflow.optimize_meta_image(b"not an image", original_name="bad.png")
        with self.assertRaisesRegex(ads_image_workflow.AdsImageValidationError, "Unsupported"):
            ads_image_workflow.optimize_meta_image(
                image_bytes("GIF"),
                original_name="animation.gif",
            )
        with self.assertRaisesRegex(ads_image_workflow.AdsImageValidationError, "will not crop"):
            ads_image_workflow.optimize_meta_image(
                image_bytes("PNG", size=(120, 80)),
                original_name="wide.png",
            )

    def test_exif_orientation_is_applied_before_square_validation(self):
        exif = Image.Exif()
        exif[274] = 6
        with self.assertRaisesRegex(ads_image_workflow.AdsImageValidationError, "80 x 120"):
            ads_image_workflow.optimize_meta_image(
                image_bytes("JPEG", size=(120, 80), exif=exif),
                original_name="rotated.jpg",
            )

    def test_names_preserve_readable_characters_and_make_slashes_safe(self):
        iso_date = "2026-07-25"
        self.assertEqual(
            ads_image_workflow.build_meta_image_filename(
                "Shohei Ohtani 50/50 Wall Art",
                "Carousel",
                position=1,
                iso_date=iso_date,
            ),
            "Shohei Ohtani 50_50 Wall Art - Carousel 01 - 2026-07-25.jpg",
        )
        self.assertEqual(
            ads_image_workflow.build_meta_image_filename(
                "O'Neal & J\u00fcrgen",
                "Instant Experience",
                iso_date=iso_date,
            ),
            "O'Neal & J\u00fcrgen - Instant Experience - 2026-07-25.jpg",
        )

    def test_account_timezone_controls_iso_date_with_sydney_fallback(self):
        now = datetime(2026, 7, 24, 16, 30, tzinfo=timezone.utc)
        self.assertEqual(
            ads_image_workflow.account_iso_date("Australia/Sydney", now=now),
            "2026-07-25",
        )
        self.assertEqual(
            ads_image_workflow.account_iso_date("America/Los_Angeles", now=now),
            "2026-07-24",
        )
        self.assertEqual(
            ads_image_workflow.account_iso_date("Not/AZone", now=now),
            "2026-07-25",
        )


class AdsImageDropboxSaveTests(unittest.TestCase):
    def build_result_and_workflow(self, campaign_type="Carousel"):
        result = ads_page.build_ads_result_record(
            "Shohei Ohtani 50/50 Wall Art",
            "Baseball",
            "USA",
            campaign_type,
            product_id="product-1",
            variation_token="save-test",
        )
        workflow = {
            "context_key": result["context_key"],
            "campaign_type": campaign_type,
            "slots": processed_slots(campaign_type),
            "widget_nonces": {},
            "export_date": "2026-07-25",
            "save_open": True,
            "saving": False,
            "destination_path": "",
            "picker_path": "",
            "outcomes": {},
        }
        return result, workflow

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_carousel_saves_five_individual_files_to_selected_destination(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow()

        def upload_success(_token, destination, items, **_kwargs):
            filename = items[0]["relative_path"]
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {
                            "name": filename,
                            "path_display": f"{destination}/{filename}",
                            "size": items[0]["size"],
                        },
                    }
                ],
                "failures": [],
            }

        upload_batch.side_effect = upload_success
        outcomes = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images/Baseball Wall Art",
            result,
            workflow,
        )

        self.assertEqual(len(upload_batch.call_args_list), 5)
        self.assertTrue(all(row["status"] == "saved" for row in outcomes.values()))
        self.assertEqual(
            [call.args[1] for call in upload_batch.call_args_list],
            ["/Sportscave Team Folder/04_OUTPUT/product-images/Baseball Wall Art"] * 5,
        )
        filenames = [call.args[2][0]["relative_path"] for call in upload_batch.call_args_list]
        self.assertEqual(
            filenames,
            [
                f"Shohei Ohtani 50_50 Wall Art - Carousel {index:02d} - 2026-07-25.jpg"
                for index in range(1, 6)
            ],
        )
        self.assertNotIn(".zip", " ".join(filenames).casefold())

    @patch("ads_page.dropbox_integration.windows_numbered_path")
    @patch("ads_page.dropbox_integration.get_metadata_if_exists")
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_collision_uses_numbered_name_without_overwrite(
        self,
        upload_batch,
        metadata,
        numbered_path,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        metadata.return_value = {".tag": "file"}
        numbered_path.return_value = (
            "/Sportscave Team Folder/04_OUTPUT/product-images/"
            "Shohei Ohtani 50_50 Wall Art - Instant Experience - 2026-07-25 (2).jpg"
        )
        upload_batch.return_value = {
            "successes": [
                {
                    "relative_path": "numbered.jpg",
                    "metadata": {"path_display": numbered_path.return_value},
                }
            ],
            "failures": [],
        }

        ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
        )

        self.assertEqual(upload_batch.call_count, 1)
        self.assertEqual(upload_batch.call_args.kwargs["conflict"], "cancel")
        self.assertTrue(
            upload_batch.call_args.args[2][0]["relative_path"].endswith("(2).jpg")
        )

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_partial_retry_skips_already_saved_files(self, upload_batch, _metadata):
        result, workflow = self.build_result_and_workflow()
        call_index = {"value": 0}

        def first_attempt(_token, destination, items, **_kwargs):
            call_index["value"] += 1
            filename = items[0]["relative_path"]
            if call_index["value"] == 3:
                return {"successes": [], "failures": [{"relative_path": filename, "error": "network"}]}
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
                    }
                ],
                "failures": [],
            }

        upload_batch.side_effect = first_attempt
        first = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
        )
        self.assertEqual(
            sum(1 for row in first.values() if row["status"] == "saved"),
            4,
        )
        workflow["outcomes"] = first
        upload_batch.reset_mock()
        upload_batch.side_effect = lambda _token, destination, items, **_kwargs: {
            "successes": [
                {
                    "relative_path": items[0]["relative_path"],
                    "metadata": {
                        "path_display": f"{destination}/{items[0]['relative_path']}"
                    },
                }
            ],
            "failures": [],
        }

        second = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
        )

        self.assertEqual(upload_batch.call_count, 1)
        self.assertTrue(all(row["status"] == "saved" for row in second.values()))

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_raised_upload_error_keeps_other_successes_for_retry(self, upload_batch, _metadata):
        result, workflow = self.build_result_and_workflow()
        call_index = {"value": 0}

        def first_attempt(_token, destination, items, **_kwargs):
            call_index["value"] += 1
            filename = items[0]["relative_path"]
            if call_index["value"] == 3:
                raise OSError("connection interrupted")
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
                    }
                ],
                "failures": [],
            }

        upload_batch.side_effect = first_attempt
        first = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
        )

        self.assertEqual(sum(row["status"] == "saved" for row in first.values()), 4)
        self.assertEqual(first["carousel-03"]["status"], "failed")
        self.assertIn("connection interrupted", first["carousel-03"]["error"])

        workflow["outcomes"] = first
        upload_batch.reset_mock()
        upload_batch.side_effect = lambda _token, destination, items, **_kwargs: {
            "successes": [
                {
                    "relative_path": items[0]["relative_path"],
                    "metadata": {
                        "path_display": f"{destination}/{items[0]['relative_path']}"
                    },
                }
            ],
            "failures": [],
        }
        second = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
        )

        self.assertEqual(upload_batch.call_count, 1)
        self.assertTrue(all(row["status"] == "saved" for row in second.values()))

    def test_destination_outside_secure_root_is_rejected(self):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        with self.assertRaisesRegex(ValueError, "outside"):
            ads_page.save_ads_images_to_dropbox(
                "token",
                "/Sportscave Team Folder",
                "/Outside",
                result,
                workflow,
            )


if __name__ == "__main__":
    unittest.main()
