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


def processed_slots(campaign_type, *, count=None):
    source = image_bytes()
    slot_specs = ads_image_workflow.campaign_image_slots(campaign_type)
    if campaign_type == "Instant Experience":
        slot_specs = slot_specs[: 1 if count is None else count]
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
        for slot in slot_specs
    }


class AdsImageProcessingTests(unittest.TestCase):
    def test_campaign_slot_counts_are_exact(self):
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Carousel")],
            ["Carousel 1", "Carousel 2", "Carousel 3", "Carousel 4", "Carousel 5"],
        )
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Instant Experience")],
            [
                "Instant Experience cover 1",
                "Cover variation 2 - optional",
                "Cover variation 3 - optional",
                "Cover variation 4 - optional",
                "Cover variation 5 - optional",
            ],
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
            "O'Neal & J\u00fcrgen - Instant Experience 01 - 2026-07-25.jpg",
        )
        self.assertEqual(
            ads_image_workflow.build_meta_image_filename(
                "O'Neal & J\u00fcrgen",
                "Instant Experience",
                position=5,
                iso_date=iso_date,
            ),
            "O'Neal & J\u00fcrgen - Instant Experience 05 - 2026-07-25.jpg",
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
    def setUp(self):
        self.ensure_folder_patcher = patch(
            "ads_page.dropbox_integration.ensure_folder_path",
            side_effect=lambda _token, path, **_kwargs: path,
        )
        self.ensure_folder_path = self.ensure_folder_patcher.start()
        self.addCleanup(self.ensure_folder_patcher.stop)

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
            "ad_notes": {
                "headlines": "Six Laps\nBuilt For Fans",
                "descriptions": "Race Memory\nLimited Edition",
                "primary_text_variations": (
                    "He remembers every lap.\n\nA collector’s piece for the wall."
                ),
                "cards": "Card 1: Six Laps Ahead\nCard 2: Race-day memory",
            },
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

        self.assertEqual(len(upload_batch.call_args_list), 6)
        self.assertTrue(
            all(
                row["status"] == "saved"
                for slot_id, row in outcomes.items()
                if not slot_id.startswith("_")
            )
        )
        expected_folder = (
            "/Sportscave Team Folder/04_OUTPUT/product-images/Baseball Wall Art/"
            "Ad(250726) Shohei Ohtani 50_50 Wall Art (Baseball) USA"
        )
        self.ensure_folder_path.assert_called_with(
            "token",
            expected_folder,
            root_path="/Sportscave Team Folder",
        )
        self.assertEqual(
            [call.args[1] for call in upload_batch.call_args_list[:5]],
            [expected_folder] * 5,
        )
        filenames = [call.args[2][0]["relative_path"] for call in upload_batch.call_args_list[:5]]
        self.assertEqual(
            filenames,
            [
                f"Shohei Ohtani 50_50 Wall Art - Carousel {index:02d} - 2026-07-25.jpg"
                for index in range(1, 6)
            ],
        )
        notes_call = upload_batch.call_args_list[-1]
        self.assertEqual(notes_call.args[1], expected_folder)
        self.assertEqual(notes_call.kwargs["conflict"], "replace")
        notes_item = notes_call.args[2][0]
        self.assertEqual(notes_item["relative_path"], "Ad Copy.txt")
        notes_text = notes_item["data"].decode("utf-8")
        self.assertIn("Sports Cave Ad Setup Notes", notes_text)
        self.assertIn("Campaign type: Carousel", notes_text)
        self.assertIn("HEADLINES\r\n\r\nSix Laps\r\nBuilt For Fans", notes_text)
        self.assertIn(
            "PRIMARY TEXT VARIATIONS\r\n\r\n"
            "He remembers every lap.\r\n\r\nA collector’s piece for the wall.",
            notes_text,
        )
        self.assertIn("Carousel setup checklist", notes_text)
        self.assertNotIn("\n", notes_text.replace("\r\n", ""))
        self.assertEqual(outcomes["_ad_setup_notes"]["status"], "saved")
        self.assertEqual(outcomes["_ad_setup_notes"]["filename"], "Ad Copy.txt")
        self.assertEqual(
            outcomes["_ad_setup_notes"]["path"],
            f"{expected_folder}/Ad Copy.txt",
        )
        self.assertNotIn(".zip", " ".join(filenames).casefold())

    def test_long_campaign_name_uses_short_windows_safe_notes_filename(self):
        result, workflow = self.build_result_and_workflow()
        result.update(
            {
                "product_name": "CR7 Ronaldo Collector’s Series Wall Art",
                "category": "Football",
                "country": "UK",
            }
        )
        workflow["export_date"] = "2026-07-31"
        folder = ads_page.build_ads_export_folder_name(result, workflow)
        filename = ads_page.build_ads_notes_filename(result, workflow)
        dropbox_folder = ads_page._ads_export_folder_path(
            (
                "/Sportscave Team Folder/04_OUTPUT/product-images/"
                "Soccer Wall Art/cr7-ronaldo-collector-s-series"
            ),
            result,
            workflow,
        )
        dropbox_path = ads_page.dropbox_integration.join_upload_path(
            dropbox_folder,
            filename,
        )
        local_path = (
            "C:\\Users\\hello\\Sportscave Dropbox\\Sportscave Team Folder"
            + dropbox_path.removeprefix("/Sportscave Team Folder").replace("/", "\\")
        )

        self.assertEqual(
            folder,
            "Ad(310726) CR7 Ronaldo Collector’s Series Wall Art (Football) UK",
        )
        self.assertEqual(filename, "Ad Copy.txt")
        self.assertNotIn(result["product_name"], filename)
        self.assertNotIn(result["category"], filename)
        self.assertNotIn(result["country"], filename)
        self.assertTrue(
            ads_page.dropbox_integration.path_is_within_root(
                dropbox_path,
                "/Sportscave Team Folder",
            )
        )
        self.assertNotIn("..", dropbox_path)
        self.assertLess(len(local_path), 260)

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_carousel_saves_any_populated_images_without_requiring_all_five(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow()
        workflow["slots"] = {
            slot_id: slot_data
            for slot_id, slot_data in workflow["slots"].items()
            if slot_id in {"carousel-01", "carousel-03"}
        }

        def upload_success(_token, destination, items, **_kwargs):
            filename = items[0]["relative_path"]
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
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

        image_filenames = [
            call.args[2][0]["relative_path"]
            for call in upload_batch.call_args_list
            if str(call.args[2][0]["relative_path"]).endswith(".jpg")
        ]
        self.assertEqual(
            image_filenames,
            [
                "Shohei Ohtani 50_50 Wall Art - Carousel 01 - 2026-07-25.jpg",
                "Shohei Ohtani 50_50 Wall Art - Carousel 03 - 2026-07-25.jpg",
            ],
        )
        self.assertEqual(outcomes["carousel-01"]["status"], "saved")
        self.assertEqual(outcomes["carousel-03"]["status"], "saved")
        self.assertNotIn("carousel-02", outcomes)
        self.assertNotIn("carousel-04", outcomes)
        self.assertNotIn("carousel-05", outcomes)
        self.assertEqual(outcomes["_ad_setup_notes"]["status"], "saved")

    @patch("ads_page.dropbox_integration.upload_batch")
    def test_setup_notes_can_save_before_any_images_are_uploaded(self, upload_batch):
        result, workflow = self.build_result_and_workflow()
        workflow["slots"] = {}
        workflow["ad_notes"] = {
            "headlines": "Launch Headline",
            "descriptions": "Launch Description",
            "cards": "Card 1: Paste from ChatGPT",
        }

        def upload_success(_token, destination, items, **_kwargs):
            filename = items[0]["relative_path"]
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
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

        self.assertEqual(upload_batch.call_count, 1)
        self.assertEqual(upload_batch.call_args.args[2][0]["relative_path"], "Ad Copy.txt")
        self.assertEqual(outcomes["_ad_setup_notes"]["status"], "saved")
        self.assertNotIn("carousel-01", outcomes)

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_resaving_replaces_ad_copy_without_numbered_duplicates(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow()
        workflow["slots"] = {}

        def upload_success(_token, destination, items, **_kwargs):
            filename = items[0]["relative_path"]
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
                    }
                ],
                "failures": [],
            }

        upload_batch.side_effect = upload_success
        destination = "/Sportscave Team Folder/04_OUTPUT/product-images/Baseball Wall Art"
        first = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            destination,
            result,
            workflow,
        )
        workflow["outcomes"] = first
        workflow["ad_notes"]["primary_text_variations"] += "\nUpdated variation"
        second = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            destination,
            result,
            workflow,
        )

        self.assertEqual(upload_batch.call_count, 2)
        for call in upload_batch.call_args_list:
            self.assertEqual(call.args[2][0]["relative_path"], "Ad Copy.txt")
            self.assertEqual(call.kwargs["conflict"], "replace")
        self.assertEqual(second["_ad_setup_notes"]["filename"], "Ad Copy.txt")

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
            "Shohei Ohtani 50_50 Wall Art - Instant Experience 01 - 2026-07-25 (2).jpg"
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

        self.assertEqual(upload_batch.call_count, 2)
        image_call = upload_batch.call_args_list[0]
        self.assertEqual(image_call.kwargs["conflict"], "cancel")
        self.assertTrue(
            image_call.args[2][0]["relative_path"].endswith("(2).jpg")
        )
        self.assertEqual(upload_batch.call_args_list[1].kwargs["conflict"], "replace")

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_ad_copy_export_includes_all_fifteen_values(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        workflow["slots"] = {}
        long_primary = "Opening line\n\nSecond paragraph with O'Neal, J\u00fcrgen and exact spacing."
        workflow["ad_notes"] = {
            "instant_experience": {
                "primary_text": [
                    long_primary,
                    "Primary 2",
                    "Primary 3",
                    "Primary 4",
                    "Primary 5",
                ],
                "headlines": [
                    "Headline 1",
                    "Headline 2",
                    "Headline 3",
                    "Headline 4",
                    "Headline 5",
                ],
                "call_to_action": [
                    "Shop Now",
                    "Learn More",
                    "View Shop",
                    "See More",
                    "Get Offer",
                ],
            }
        }

        def upload_success(_token, destination, items, **_kwargs):
            filename = items[0]["relative_path"]
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
                    }
                ],
                "failures": [],
            }

        upload_batch.side_effect = upload_success
        ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images/Baseball Wall Art",
            result,
            workflow,
        )

        notes_item = upload_batch.call_args.args[2][0]
        notes_text = notes_item["data"].decode("utf-8")
        self.assertEqual(notes_item["relative_path"], "Ad Copy.txt")
        self.assertIn("INSTANT EXPERIENCE AD COPY", notes_text)
        self.assertIn(
            "PRIMARY TEXT\r\n\r\nOPTION 1\r\n"
            "Opening line\r\n\r\nSecond paragraph with O'Neal, J\u00fcrgen and exact spacing.",
            notes_text,
        )
        self.assertIn("OPTION 5\r\nPrimary 5", notes_text)
        self.assertIn("HEADLINES\r\n\r\nOPTION 1\r\nHeadline 1", notes_text)
        self.assertIn("OPTION 5\r\nHeadline 5", notes_text)
        self.assertIn("CALL TO ACTION\r\n\r\nOPTION 1\r\nShop Now", notes_text)
        self.assertIn("OPTION 5\r\nGet Offer", notes_text)
        self.assertNotIn("DESCRIPTIONS", notes_text)
        self.assertNotIn("CAROUSEL CARDS / AD SETUP", notes_text)
        self.assertNotIn("\n", notes_text.replace("\r\n", ""))

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_save_uses_selected_product_not_uploaded_filename(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        workflow["slots"]["instant-experience-01"]["original_name"] = "random-chatgpt-cover.png"
        progress_events = []

        def upload_success(_token, destination, items, **kwargs):
            if kwargs.get("progress_callback"):
                kwargs["progress_callback"](1, 1, items[0]["relative_path"], 5, 10)
                kwargs["progress_callback"](1, 1, items[0]["relative_path"], 10, 10)
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
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
            progress_callback=lambda index, total, label, uploaded, size: progress_events.append(
                (index, total, label, uploaded, size)
            ),
        )

        self.assertEqual(upload_batch.call_count, 2)
        filename = upload_batch.call_args_list[0].args[2][0]["relative_path"]
        self.assertEqual(
            filename,
            "Shohei Ohtani 50_50 Wall Art - Instant Experience 01 - 2026-07-25.jpg",
        )
        self.assertNotIn("random-chatgpt-cover", filename)
        self.assertEqual(outcomes["instant-experience-01"]["status"], "saved")
        self.assertEqual(
            [(event[0], event[1], event[2]) for event in progress_events],
            [(1, 1, "Instant Experience cover 1"), (1, 1, "Instant Experience cover 1")],
        )

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_saves_two_to_five_populated_variations_without_overwrite(
        self,
        upload_batch,
        _metadata,
    ):
        for count in range(2, 6):
            with self.subTest(count=count):
                result, workflow = self.build_result_and_workflow("Instant Experience")
                workflow["slots"] = processed_slots("Instant Experience", count=count)

                def upload_success(_token, destination, items, **_kwargs):
                    filename = items[0]["relative_path"]
                    return {
                        "successes": [
                            {
                                "relative_path": filename,
                                "metadata": {"path_display": f"{destination}/{filename}"},
                            }
                        ],
                        "failures": [],
                    }

                upload_batch.reset_mock()
                upload_batch.side_effect = upload_success
                outcomes = ads_page.save_ads_images_to_dropbox(
                    "token",
                    "/Sportscave Team Folder",
                    "/Sportscave Team Folder/04_OUTPUT/product-images",
                    result,
                    workflow,
                )

                filenames = [
                    call.args[2][0]["relative_path"]
                    for call in upload_batch.call_args_list
                    if str(call.args[2][0]["relative_path"]).endswith(".jpg")
                ]
                self.assertEqual(len(filenames), count)
                self.assertEqual(len(set(filenames)), count)
                self.assertEqual(
                    filenames,
                    [
                        f"Shohei Ohtani 50_50 Wall Art - Instant Experience {index:02d} - 2026-07-25.jpg"
                        for index in range(1, count + 1)
                    ],
                )
                self.assertTrue(all(row["status"] == "saved" for row in outcomes.values()))

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_partial_multi_image_failure_reports_failed_cover(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        workflow["slots"] = processed_slots("Instant Experience", count=3)
        call_index = {"value": 0}

        def partial_upload(_token, destination, items, **_kwargs):
            call_index["value"] += 1
            filename = items[0]["relative_path"]
            if call_index["value"] == 2:
                return {"successes": [], "failures": [{"relative_path": filename, "error": "rate limited"}]}
            return {
                "successes": [
                    {
                        "relative_path": filename,
                        "metadata": {"path_display": f"{destination}/{filename}"},
                    }
                ],
                "failures": [],
            }

        upload_batch.side_effect = partial_upload
        outcomes = ads_page.save_ads_images_to_dropbox(
            "token",
            "/Sportscave Team Folder",
            "/Sportscave Team Folder/04_OUTPUT/product-images",
            result,
            workflow,
        )

        self.assertEqual(
            sum(
                row["status"] == "saved"
                for slot_id, row in outcomes.items()
                if not slot_id.startswith("_")
            ),
            2,
        )
        self.assertEqual(outcomes["instant-experience-02"]["status"], "failed")
        self.assertIn("rate limited", outcomes["instant-experience-02"]["error"])

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
            sum(
                1
                for slot_id, row in first.items()
                if not slot_id.startswith("_") and row["status"] == "saved"
            ),
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

        self.assertEqual(upload_batch.call_count, 2)
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

        self.assertEqual(
            sum(
                row["status"] == "saved"
                for slot_id, row in first.items()
                if not slot_id.startswith("_")
            ),
            4,
        )
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

        self.assertEqual(upload_batch.call_count, 2)
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
