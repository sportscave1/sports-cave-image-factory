from datetime import datetime, timezone
import hashlib
import io
import unittest
import zipfile
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
        slot_specs = slot_specs[: len(slot_specs) if count is None else count]

        def processed_instant_slot(slot):
            details = ads_image_workflow.inspect_instant_experience_original(
                source,
                original_name=f"{slot['concept_id']}.png",
            )
            preview = ads_image_workflow.build_instant_experience_preview_thumbnail(
                source,
                source_hash=details["source_hash"],
            )
            return {
                **details,
                **preview,
                "data": source,
                "output_format": details["source_format"],
                "output_width": details["source_width"],
                "output_height": details["source_height"],
                "output_size": details["source_size"],
                "slot_id": slot["id"],
                "label": slot["label"],
                "concept_id": slot["concept_id"],
                "display_name": slot["display_name"],
                "supporting_label": slot["supporting_label"],
                "position": slot["position"],
                "valid": True,
                "error": "",
            }

        return {slot["id"]: processed_instant_slot(slot) for slot in slot_specs}
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


def instant_experience_ad_notes():
    return {
        "instant_experience_concepts": {
            concept["id"]: [
                {
                    "primary_text": f"{concept['display_name']} primary {index}\n\nSecond paragraph.",
                    "headline": f"{concept['display_name']} headline {index}",
                    "cta": f"{concept['display_name']} CTA {index}",
                }
                for index in range(1, 4)
            ]
            for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS
        }
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
                "Nostalgia Cover",
                "Ownership Cover",
                "Scarcity Cover",
            ],
        )
        self.assertEqual(ads_image_workflow.campaign_image_slots("Single Image / Video"), ())

    def test_instant_experience_originals_are_inspected_without_reencoding(self):
        source = image_bytes("PNG", size=(1024, 1024), color=(12, 34, 56))

        details = ads_image_workflow.inspect_instant_experience_original(
            source,
            original_name="nostalgia.png",
        )

        self.assertEqual(details["source_width"], 1024)
        self.assertEqual(details["source_height"], 1024)
        self.assertEqual(details["source_format"], "PNG")
        self.assertEqual(details["source_size"], len(source))
        self.assertEqual(details["source_hash"], hashlib.sha256(source).hexdigest())

    def test_instant_experience_preview_thumbnail_is_lightweight_cached_and_not_cropped(self):
        ads_image_workflow.instant_experience_preview_cache_clear()
        source = image_bytes("PNG", size=(1600, 1200), color=(12, 34, 56))
        source_hash = ads_image_workflow.source_image_signature(source)

        first = ads_image_workflow.build_instant_experience_preview_thumbnail(
            source,
            source_hash=source_hash,
        )
        cache_after_first = ads_image_workflow.instant_experience_preview_cache_info()
        second = ads_image_workflow.build_instant_experience_preview_thumbnail(
            source,
            source_hash=source_hash,
        )
        cache_after_second = ads_image_workflow.instant_experience_preview_cache_info()

        self.assertLessEqual(max(first["preview_width"], first["preview_height"]), 460)
        self.assertEqual(first["preview_width"], 460)
        self.assertEqual(first["preview_height"], 345)
        self.assertEqual(first["preview_data"], second["preview_data"])
        self.assertGreater(cache_after_second.hits, cache_after_first.hits)
        self.assertLess(len(first["preview_data"]), len(source))
        with Image.open(io.BytesIO(first["preview_data"])) as preview:
            preview.load()
            self.assertEqual(preview.size, (460, 345))

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

    def test_instant_experience_target_export_is_verified_srgb_1024_png(self):
        first = ads_image_workflow.optimize_meta_image(
            image_bytes("WEBP"),
            original_name="instant.webp",
            output_edge=ads_image_workflow.INSTANT_EXPERIENCE_IMAGE_EDGE,
            output_format="PNG",
        )
        second = ads_image_workflow.optimize_meta_image(
            image_bytes("WEBP"),
            original_name="instant.webp",
            output_edge=ads_image_workflow.INSTANT_EXPERIENCE_IMAGE_EDGE,
            output_format="PNG",
        )

        self.assertEqual(first["data"], second["data"])
        self.assertEqual(first["output_format"], "PNG")
        with Image.open(io.BytesIO(first["data"])) as output:
            output.load()
            self.assertEqual(output.format, "PNG")
            self.assertEqual(output.mode, "RGB")
            self.assertEqual(output.size, (1024, 1024))
            self.assertTrue(output.info.get("icc_profile"))

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
        if campaign_type == "Instant Experience":
            workflow["ad_notes"] = instant_experience_ad_notes()
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
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_package_uses_concept_folders_and_replace_conflict(
        self,
        upload_batch,
        numbered_path,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")

        def upload_success(_token, destination, items, **_kwargs):
            return {
                "successes": [
                    {
                        "relative_path": item["relative_path"],
                        "metadata": {
                            "name": item["relative_path"].split("/")[-1],
                            "path_display": f"{destination}/{item['relative_path']}",
                            "size": item["size"],
                        },
                    }
                    for item in items
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
        )

        numbered_path.assert_not_called()
        self.assertEqual(upload_batch.call_count, 1)
        self.assertEqual(upload_batch.call_args.kwargs["conflict"], "replace")
        self.assertEqual(
            [item["relative_path"] for item in upload_batch.call_args.args[2]],
            [
                "01-nostalgia/nostalgia-cover-original.png",
                "01-nostalgia/ad-copy.txt",
                "02-ownership/ownership-cover-original.png",
                "02-ownership/ad-copy.txt",
                "03-scarcity/scarcity-cover-original.png",
                "03-scarcity/ad-copy.txt",
            ],
        )
        self.assertEqual(outcomes["_instant_experience_package"]["status"], "saved")

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_ad_copy_exports_three_variations_per_concept(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        long_primary = "Opening line\n\nSecond paragraph with O'Neal, J\u00fcrgen and exact spacing."
        workflow["ad_notes"] = instant_experience_ad_notes()
        workflow["ad_notes"]["instant_experience_concepts"]["nostalgia"][0] = {
            "primary_text": long_primary,
            "headline": "Remember The Kid",
            "cta": "See the Edition",
        }

        def upload_success(_token, destination, items, **_kwargs):
            return {
                "successes": [
                    {
                        "relative_path": item["relative_path"],
                        "metadata": {"path_display": f"{destination}/{item['relative_path']}"},
                    }
                    for item in items
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

        notes_item = next(
            item
            for item in upload_batch.call_args.args[2]
            if item["relative_path"] == "01-nostalgia/ad-copy.txt"
        )
        notes_text = notes_item["data"].decode("utf-8")
        self.assertEqual(notes_item["relative_path"], "01-nostalgia/ad-copy.txt")
        self.assertIn("SPORTS CAVE INSTANT EXPERIENCE", notes_text)
        self.assertIn("CONCEPT:\r\nNostalgia", notes_text)
        self.assertIn(
            "VARIATION 1\r\n\r\nPRIMARY TEXT:\r\n"
            "Opening line\r\n\r\nSecond paragraph with O'Neal, J\u00fcrgen and exact spacing.",
            notes_text,
        )
        self.assertIn("HEADLINE:\r\nRemember The Kid", notes_text)
        self.assertIn("CTA:\r\nSee the Edition", notes_text)
        self.assertIn("VARIATION 3", notes_text)
        self.assertNotIn("VARIATION 4", notes_text)
        self.assertNotIn("DESCRIPTIONS", notes_text)
        self.assertNotIn("CAROUSEL CARDS / AD SETUP", notes_text)
        self.assertNotIn("\n", notes_text.replace("\r\n", ""))

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_individual_items_preserve_original_cover_bytes(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        original_hash = hashlib.sha256(
            workflow["slots"]["instant-experience-nostalgia"]["data"]
        ).hexdigest()
        progress_events = []

        def upload_success(_token, destination, items, **kwargs):
            if kwargs.get("progress_callback"):
                kwargs["progress_callback"](1, len(items), items[0]["relative_path"], 5, 10)
                kwargs["progress_callback"](1, len(items), items[0]["relative_path"], 10, 10)
            return {
                "successes": [
                    {
                        "relative_path": item["relative_path"],
                        "metadata": {
                            "name": item["relative_path"].split("/")[-1],
                            "path_display": f"{destination}/{item['relative_path']}",
                            "size": item["size"],
                        },
                    }
                    for item in items
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

        self.assertEqual(upload_batch.call_count, 1)
        nostalgia_item = next(
            item
            for item in upload_batch.call_args.args[2]
            if item["relative_path"] == "01-nostalgia/nostalgia-cover-original.png"
        )
        self.assertEqual(hashlib.sha256(nostalgia_item["data"]).hexdigest(), original_hash)
        self.assertEqual(outcomes["instant-experience-nostalgia"]["status"], "saved")
        self.assertEqual(outcomes["instant-experience-nostalgia"]["concept"], "Nostalgia")
        self.assertEqual(
            [(event[0], event[1], event[2]) for event in progress_events],
            [(1, 6, "Nostalgia Cover"), (1, 6, "Nostalgia Cover")],
        )

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_saves_three_populated_covers_without_overwrite(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        workflow["slots"] = processed_slots("Instant Experience", count=3)

        def upload_success(_token, destination, items, **_kwargs):
            return {
                "successes": [
                    {
                        "relative_path": item["relative_path"],
                        "metadata": {"path_display": f"{destination}/{item['relative_path']}"},
                    }
                    for item in items
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
        )

        filenames = [
            item["relative_path"]
            for item in upload_batch.call_args.args[2]
            if str(item["relative_path"]).endswith(".png")
        ]
        self.assertEqual(len(filenames), 3)
        self.assertEqual(len(set(filenames)), 3)
        self.assertEqual(
            filenames,
            [
                "01-nostalgia/nostalgia-cover-original.png",
                "02-ownership/ownership-cover-original.png",
                "03-scarcity/scarcity-cover-original.png",
            ],
        )
        self.assertTrue(all(row["status"] == "saved" for row in outcomes.values()))

    def test_instant_experience_package_zip_contains_three_folders_and_originals(self):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        source_hashes = {
            concept["id"]: hashlib.sha256(
                workflow["slots"][f"instant-experience-{concept['id']}"]["data"]
            ).hexdigest()
            for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS
        }

        archive_bytes = ads_page.build_instant_experience_package_zip(result, workflow)

        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = archive.namelist()
            root = ads_page.build_ads_export_folder_name(result, workflow)
            self.assertEqual(
                names,
                [
                    f"{root}/01-nostalgia/nostalgia-cover-original.png",
                    f"{root}/01-nostalgia/ad-copy.txt",
                    f"{root}/02-ownership/ownership-cover-original.png",
                    f"{root}/02-ownership/ad-copy.txt",
                    f"{root}/03-scarcity/scarcity-cover-original.png",
                    f"{root}/03-scarcity/ad-copy.txt",
                ],
            )
            self.assertFalse(any("preview" in name.casefold() for name in names))
            for concept in ads_page.INSTANT_EXPERIENCE_CONCEPTS:
                image_name = (
                    f"{root}/{concept['folder']}/"
                    f"{concept['filename_prefix']}.png"
                )
                self.assertEqual(
                    hashlib.sha256(archive.read(image_name)).hexdigest(),
                    source_hashes[concept["id"]],
                )
                copy_text = archive.read(f"{root}/{concept['folder']}/ad-copy.txt").decode("utf-8")
                self.assertIn("VARIATION 1\r\n", copy_text)
                self.assertIn("VARIATION 3\r\n", copy_text)
                self.assertNotIn("VARIATION 4", copy_text)

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_partial_multi_image_failure_reports_failed_cover(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        workflow["slots"] = processed_slots("Instant Experience", count=3)

        def partial_upload(_token, destination, items, **_kwargs):
            successes = []
            failures = []
            for item in items:
                filename = item["relative_path"]
                if filename == "02-ownership/ownership-cover-original.png":
                    failures.append({"relative_path": filename, "error": "rate limited"})
                else:
                    successes.append(
                        {
                            "relative_path": filename,
                            "metadata": {"path_display": f"{destination}/{filename}"},
                        }
                    )
            return {
                "successes": successes,
                "failures": failures,
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
                if slot_id.startswith("instant-experience-")
            ),
            2,
        )
        self.assertEqual(outcomes["instant-experience-ownership"]["status"], "failed")
        self.assertIn("rate limited", outcomes["instant-experience-ownership"]["error"])

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
