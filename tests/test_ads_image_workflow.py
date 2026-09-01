from datetime import datetime, timezone
import hashlib
import io
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch
import zipfile

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
    concepts = {}
    for concept_index, concept in enumerate(ads_page.INSTANT_EXPERIENCE_CONCEPTS):
        variations = []
        for index in range(1, 4):
            description_variant = ads_page._instant_experience_description_variant(index)
            cta = ads_page.INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS[
                (concept_index + index - 1)
                % len(ads_page.INSTANT_EXPERIENCE_APPROVED_CREATIVE_CTAS)
            ]
            if index == 1:
                cta = ads_page.INSTANT_EXPERIENCE_PRIMARY_IMAGE_CTAS[concept["id"]]
            variations.append(
                {
                    "description_key": description_variant["key"],
                    "description_label": description_variant["label"],
                    "primary_text": (
                        f"{concept['display_name']} primary {index}\n\nSecond paragraph. "
                        f"{ads_page.INSTANT_EXPERIENCE_PRIMARY_TEXT_CTA_ENDINGS[cta]}"
                    ),
                    "headline": f"{concept['display_name']} headline {index}",
                    "cta": cta,
                }
            )
        concepts[concept["id"]] = variations
    return {"instant_experience_concepts": concepts}


class AdsImageProcessingTests(unittest.TestCase):
    def test_campaign_slot_counts_are_exact(self):
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Carousel")],
            ["Carousel 1", "Carousel 2", "Carousel 3", "Carousel 4", "Carousel 5"],
        )
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Instant Experience")],
            [
                "Premium Scarcity — Right Angle Cover",
                "Premium Scarcity — Straight On Cover",
                "Premium Scarcity — Left Angle Cover",
            ],
        )
        self.assertEqual(
            [slot["label"] for slot in ads_image_workflow.campaign_image_slots("Creative Refresh")],
            ["Ad 1 Image", "Ad 2 Image", "Ad 3 Image"],
        )
        self.assertEqual(
            [slot["strategy"] for slot in ads_image_workflow.campaign_image_slots("Creative Refresh")],
            ["Winner Evolution", "Emotional / Collector Expansion", "Pattern Interrupt"],
        )
        self.assertEqual(ads_image_workflow.campaign_image_slots("Single Image / Video"), ())

    def test_instant_experience_future_package_paths_use_canonical_route_slugs(self):
        self.assertEqual(
            [concept["folder"] for concept in ads_image_workflow.INSTANT_EXPERIENCE_CONCEPTS],
            [
                "01-premium-scarcity-right",
                "02-premium-scarcity-front",
                "03-premium-scarcity-left",
            ],
        )
        self.assertEqual(
            [concept["filename_prefix"] for concept in ads_image_workflow.INSTANT_EXPERIENCE_CONCEPTS],
            [
                "premium_scarcity_right_cover_original",
                "premium_scarcity_front_cover_original",
                "premium_scarcity_left_cover_original",
            ],
        )
        emitted = "\n".join(
            concept["folder"]
            for concept in ads_image_workflow.INSTANT_EXPERIENCE_CONCEPTS
        )
        for obsolete in (
            "01-nostalgia",
            "02-ownership",
            "03-scarcity",
            "01_framed_greatness_scarcity_hybrid",
            "02_pure_limited_release_scarcity",
            "03_collector_proof_scarcity",
        ):
            self.assertNotIn(obsolete, emitted)

    def test_instant_experience_originals_are_inspected_without_reencoding(self):
        source = image_bytes("PNG", size=(1024, 1024), color=(12, 34, 56))

        details = ads_image_workflow.inspect_instant_experience_original(
            source,
            original_name="premium-scarcity-right.png",
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
        source = image_bytes("WEBP")
        first = ads_image_workflow.optimize_meta_image(
            source,
            original_name="instant.webp",
            output_edge=ads_image_workflow.INSTANT_EXPERIENCE_IMAGE_EDGE,
            output_format="PNG",
        )
        second = ads_image_workflow.optimize_meta_image(
            source,
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
            product_url=(
                "https://www.sportscaveshop.com/products/"
                "shohei-ohtani-50-50-wall-art"
            ),
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

        self.assertEqual(len(upload_batch.call_args_list), 7)
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
        notes_call = upload_batch.call_args_list[-2]
        carousel_csv_call = upload_batch.call_args_list[-1]
        self.assertEqual(notes_call.args[2][0]["relative_path"], "Ad Copy.txt")
        self.assertEqual(
            carousel_csv_call.args[2][0]["relative_path"],
            ads_page.CAROUSEL_COPY_FILENAME,
        )
        self.assertEqual(outcomes["_carousel_copy_csv"]["status"], "saved")
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

        self.assertEqual(upload_batch.call_count, 2)
        self.assertEqual(upload_batch.call_args_list[0].args[2][0]["relative_path"], "Ad Copy.txt")
        self.assertEqual(
            upload_batch.call_args_list[1].args[2][0]["relative_path"],
            ads_page.CAROUSEL_COPY_FILENAME,
        )
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

        self.assertEqual(upload_batch.call_count, 4)
        self.assertEqual(
            [call.args[2][0]["relative_path"] for call in upload_batch.call_args_list],
            [
                "Ad Copy.txt",
                ads_page.CAROUSEL_COPY_FILENAME,
                "Ad Copy.txt",
                ads_page.CAROUSEL_COPY_FILENAME,
            ],
        )
        for call in upload_batch.call_args_list:
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
                "01-premium-scarcity-right/premium_scarcity_right_cover_original.png",
                "01-premium-scarcity-right/ad-copy.txt",
                "01-premium-scarcity-right/01-legacy-standard/primary-text.txt",
                "01-premium-scarcity-right/01-legacy-standard/headline.txt",
                "01-premium-scarcity-right/02-framed-greatness/primary-text.txt",
                "01-premium-scarcity-right/02-framed-greatness/headline.txt",
                "01-premium-scarcity-right/03-choose-a-side/primary-text.txt",
                "01-premium-scarcity-right/03-choose-a-side/headline.txt",
                "02-premium-scarcity-front/premium_scarcity_front_cover_original.png",
                "02-premium-scarcity-front/ad-copy.txt",
                "02-premium-scarcity-front/01-legacy-standard/primary-text.txt",
                "02-premium-scarcity-front/01-legacy-standard/headline.txt",
                "02-premium-scarcity-front/02-framed-greatness/primary-text.txt",
                "02-premium-scarcity-front/02-framed-greatness/headline.txt",
                "02-premium-scarcity-front/03-choose-a-side/primary-text.txt",
                "02-premium-scarcity-front/03-choose-a-side/headline.txt",
                "03-premium-scarcity-left/premium_scarcity_left_cover_original.png",
                "03-premium-scarcity-left/ad-copy.txt",
                "03-premium-scarcity-left/01-legacy-standard/primary-text.txt",
                "03-premium-scarcity-left/01-legacy-standard/headline.txt",
                "03-premium-scarcity-left/02-framed-greatness/primary-text.txt",
                "03-premium-scarcity-left/02-framed-greatness/headline.txt",
                "03-premium-scarcity-left/03-choose-a-side/primary-text.txt",
                "03-premium-scarcity-left/03-choose-a-side/headline.txt",
                ads_page._instant_experience_current_copy_csv_filename(result),
            ],
        )
        self.assertEqual(outcomes["_instant_experience_package"]["status"], "saved")

    def test_ad_variation_text_files_are_exact_persistent_zip_bytes(self):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        primary_text = "OWN A PIECE OF THE LEGACY."
        headline = "LIMITED EDITION NFL WALL ART"
        variation = workflow["ad_notes"]["instant_experience_concepts"][
            "premium_scarcity_right"
        ][0]
        variation["primary_text"] = primary_text
        variation["headline"] = headline

        items = ads_page._instant_experience_package_items(result, workflow)
        primary_path = (
            "01-premium-scarcity-right/01-legacy-standard/primary-text.txt"
        )
        headline_path = "01-premium-scarcity-right/01-legacy-standard/headline.txt"
        item_by_path = {item["relative_path"]: item for item in items}

        self.assertEqual(item_by_path[primary_path]["data"], primary_text.encode("utf-8"))
        self.assertEqual(item_by_path[headline_path]["data"], headline.encode("utf-8"))
        self.assertNotEqual(item_by_path[primary_path]["data"], b"")
        self.assertNotEqual(item_by_path[headline_path]["data"], b"")
        self.assertNotIn(primary_text, item_by_path[headline_path]["data"].decode("utf-8"))

        archive_bytes = io.BytesIO()
        with zipfile.ZipFile(archive_bytes, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in items:
                archive.writestr(item["relative_path"], item["data"])

        archive_bytes.seek(0)
        with zipfile.ZipFile(archive_bytes, "r") as archive:
            info_by_path = {info.filename: info for info in archive.infolist()}
            self.assertEqual(archive.read(primary_path), primary_text.encode("utf-8"))
            self.assertEqual(archive.read(headline_path), headline.encode("utf-8"))
            for path in (primary_path, headline_path):
                info = info_by_path[path]
                self.assertFalse(stat.S_ISLNK(info.external_attr >> 16))
                self.assertNotIn(Path(path).suffix.casefold(), {".lnk", ".url"})

            with tempfile.TemporaryDirectory() as extraction_directory:
                archive.extractall(extraction_directory)
                extracted_primary = Path(extraction_directory, *primary_path.split("/"))
                extracted_headline = Path(extraction_directory, *headline_path.split("/"))
                self.assertEqual(extracted_primary.read_text(encoding="utf-8"), primary_text)
                self.assertEqual(extracted_headline.read_text(encoding="utf-8"), headline)
                for exported_text in (extracted_primary, extracted_headline):
                    content = exported_text.read_text(encoding="utf-8")
                    self.assertNotIn("/tmp/", content)
                    self.assertNotRegex(content, r"[A-Za-z]:\\")

    def test_ad_variation_text_export_rejects_missing_required_named_field(self):
        with self.assertRaisesRegex(ValueError, "Primary Text is required"):
            ads_page.build_ad_variation_text_items(
                {"primary_text": "", "headline": "Headline is present"},
                relative_folder="01-ad",
                slot_id="ad-01",
                label="Ad 1",
            )

    def test_creative_refresh_uses_same_ad_variation_text_export(self):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        result["workflow_mode"] = ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
        items = ads_page._instant_experience_package_items(result, workflow)
        text_items = {
            item["relative_path"]: item["data"]
            for item in items
            if item.get("filename")
            in {ads_page.ADS_PRIMARY_TEXT_FILENAME, ads_page.ADS_HEADLINE_FILENAME}
        }

        self.assertEqual(len(text_items), 18)
        self.assertIn(
            "01-premium-scarcity-right/01-legacy-standard/primary-text.txt",
            text_items,
        )
        self.assertIn(
            "01-premium-scarcity-right/01-legacy-standard/headline.txt",
            text_items,
        )

    @patch("ads_page.dropbox_integration.get_metadata_if_exists", return_value=None)
    @patch("ads_page.dropbox_integration.upload_batch")
    def test_instant_experience_ad_copy_exports_three_variations_per_concept(
        self,
        upload_batch,
        _metadata,
    ):
        result, workflow = self.build_result_and_workflow("Instant Experience")
        long_primary = (
            "Opening line\n\nSecond paragraph with O'Neal, J\u00fcrgen and exact spacing. "
            "Claim your edition."
        )
        workflow["ad_notes"] = instant_experience_ad_notes()
        workflow["ad_notes"]["instant_experience_concepts"]["premium_scarcity_right"][0] = {
            "description_key": "legacy_standard",
            "description_label": "Description 1 — Legacy Standard",
            "primary_text": long_primary,
            "headline": "Remember The Kid",
            "cta": "Claim Your Edition",
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
            if item["relative_path"] == "01-premium-scarcity-right/ad-copy.txt"
        )
        notes_text = notes_item["data"].decode("utf-8")
        self.assertEqual(
            notes_item["relative_path"],
            "01-premium-scarcity-right/ad-copy.txt",
        )
        self.assertIn("SPORTS CAVE INSTANT EXPERIENCE", notes_text)
        self.assertIn("ROUTE:\r\nPremium Scarcity", notes_text)
        self.assertIn(
            "Description 1 — Legacy Standard\r\n\r\nDESCRIPTION KEY:\r\n"
            "legacy_standard\r\n\r\nDESCRIPTION COPY:\r\n"
            "Opening line\r\n\r\nSecond paragraph with O'Neal, J\u00fcrgen and exact spacing. "
            "Claim your edition.",
            notes_text,
        )
        self.assertIn("HEADLINE:\r\nRemember The Kid", notes_text)
        self.assertIn("CTA:\r\nClaim Your Edition", notes_text)
        self.assertIn("Description 3 — Choose a Side", notes_text)
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
            workflow["slots"]["instant-experience-premium-scarcity-right"]["data"]
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
        right_item = next(
            item
            for item in upload_batch.call_args.args[2]
            if item["relative_path"]
            == "01-premium-scarcity-right/premium_scarcity_right_cover_original.png"
        )
        self.assertEqual(hashlib.sha256(right_item["data"]).hexdigest(), original_hash)
        self.assertEqual(outcomes["instant-experience-premium-scarcity-right"]["status"], "saved")
        self.assertIn(
            "Right Angle",
            outcomes["instant-experience-premium-scarcity-right"]["concept"],
        )
        self.assertEqual(
            [(event[0], event[1], event[2]) for event in progress_events],
            [
                (1, 25, "Premium Scarcity — Right Angle Cover"),
                (1, 25, "Premium Scarcity — Right Angle Cover"),
            ],
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
                "01-premium-scarcity-right/premium_scarcity_right_cover_original.png",
                "02-premium-scarcity-front/premium_scarcity_front_cover_original.png",
                "03-premium-scarcity-left/premium_scarcity_left_cover_original.png",
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

        def partial_upload(_token, destination, items, **_kwargs):
            successes = []
            failures = []
            for item in items:
                filename = item["relative_path"]
                if filename == "02-premium-scarcity-front/premium_scarcity_front_cover_original.png":
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
        self.assertEqual(outcomes["instant-experience-premium-scarcity-front"]["status"], "failed")
        self.assertIn("rate limited", outcomes["instant-experience-premium-scarcity-front"]["error"])

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

        self.assertEqual(upload_batch.call_count, 3)
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

        self.assertEqual(upload_batch.call_count, 3)
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
