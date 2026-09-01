import csv
import io
import unittest
from unittest import mock

from PIL import Image

import ads_page
import ads_posting_page
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from posting_import_csv import (
    POSTING_IMPORT_FILENAME,
    POSTING_IMPORT_HEADERS,
    POSTING_IMPORT_LEGACY_HEADERS,
    POSTING_IMPORT_LEGACY_SCHEMA_VERSION,
    POSTING_IMPORT_SCHEMA_VERSION,
    PostingImportCSVError,
    build_posting_import_rows,
    parse_posting_import_csv,
    serialize_posting_import_csv,
)


class FakeUpload:
    def __init__(self, data, *, name, file_id, content_type="text/csv"):
        self._data = bytes(data)
        self.name = name
        self.file_id = file_id
        self.type = content_type
        self.size = len(self._data)
        self.getvalue_calls = 0

    def getvalue(self):
        self.getvalue_calls += 1
        return self._data


def posting_ads():
    return (
        {
            "ad_number": 1,
            "primary_text": "Peter Brock.\nSix Laps Ahead.\nRace-day intensity on the wall.",
            "headline": 'Brock, "Six Laps"',
            "description": "Limited, exact description",
        },
        {
            "ad_number": 2,
            "primary_text": "Second ad — collector evolution.",
            "headline": "Bathurst Memory",
            "description": "",
        },
        {
            "ad_number": 3,
            "primary_text": "Third ad with O'Neal-style punctuation.",
            "headline": "The Mountain Calls",
            "description": "Final description",
        },
    )


def posting_rows(**overrides):
    values = {
        "product_name": "Six Laps Ahead Peter Brock Wall Art",
        "product_handle": "peter-brock-bathurst-wall-art",
        "product_url": (
            "https://www.sportscaveshop.com/products/"
            "peter-brock-bathurst-wall-art"
        ),
        "country": "AUS",
        "sport_category": "Motorsport",
        "campaign_type": "Instant Experience",
        "ads": posting_ads_with_variations(),
    }
    values.update(overrides)
    return build_posting_import_rows(**values)


def posting_ads_with_variations():
    workflow = ads_workflow()
    rows = []
    for index, concept in enumerate(INSTANT_EXPERIENCE_CONCEPTS, start=1):
        variations = [
            {**variation, "variation": variation_number}
            for variation_number, variation in enumerate(
                workflow["ad_notes"]["instant_experience_concepts"][concept["id"]],
                start=1,
            )
        ]
        variations[0]["description"] = posting_ads()[index - 1]["description"]
        rows.append(
            {
                "ad_number": index,
                "route_key": concept["id"],
                "route_label": ads_page._instant_experience_copy_csv_route_label(concept),
                "variations": variations,
            }
        )
    return tuple(rows)


def primary_ads(batch):
    return tuple(
        {
            "ad_number": ad["ad_number"],
            "primary_text": ad["primary_text"],
            "headline": ad["headline"],
            "description": ad["description"],
        }
        for ad in batch["ads"]
    )


def ads_result(*, workflow_mode=ads_page.ADS_WORKFLOW_MODE_NEW):
    return {
        "context_key": f"posting-csv-{workflow_mode}",
        "workflow_mode": workflow_mode,
        "campaign_type": "Instant Experience",
        "product_name": "Six Laps Ahead Peter Brock Wall Art",
        "product_url": (
            "https://www.sportscaveshop.com/products/"
            "peter-brock-bathurst-wall-art"
        ),
        "country": "Australia",
        "category": "Motorsport",
    }


def ads_workflow():
    notes = {}
    for index, concept in enumerate(INSTANT_EXPERIENCE_CONCEPTS, start=1):
        notes[concept["id"]] = [
            {
                "description_key": "legacy_standard",
                "description_label": "Description 1 — Legacy Standard",
                "primary_text": posting_ads()[index - 1]["primary_text"],
                "headline": posting_ads()[index - 1]["headline"],
                "description": posting_ads()[index - 1]["description"],
                "cta": "Claim Your Edition",
            },
            {
                "description_key": "framed_greatness",
                "description_label": "Description 2 — Framed Greatness",
                "primary_text": f"Alternative {index}A",
                "headline": f"Alternative headline {index}A",
                "cta": "Secure Your Edition",
            },
            {
                "description_key": "choose_a_side",
                "description_label": "Description 3 — Choose a Side",
                "primary_text": f"Alternative {index}B",
                "headline": f"Alternative headline {index}B",
                "cta": "Own This Edition",
            },
        ]
    return {"ad_notes": {"instant_experience_concepts": notes}, "slots": {}}


def product_records():
    return ads_page.build_ads_product_selector_records(
        [
            {
                "shopify_product_id": "shopify-1",
                "product_title": "Six Laps Ahead Peter Brock Wall Art",
                "product_handle": "peter-brock-bathurst-wall-art",
                "online_store_url": (
                    "https://www.sportscaveshop.com/products/"
                    "peter-brock-bathurst-wall-art"
                ),
            }
        ]
    )


class PostingImportContractTests(unittest.TestCase):
    def test_schema_is_versioned_three_route_nine_copy_row_contract(self):
        rows = posting_rows()
        self.assertEqual(len(rows), 9)
        self.assertTrue(
            all(row["schema_version"] == POSTING_IMPORT_SCHEMA_VERSION for row in rows)
        )
        self.assertEqual(
            [(row["ad_number"], row["variation"]) for row in rows],
            [(ad_number, variation) for ad_number in (1, 2, 3) for variation in (1, 2, 3)],
        )
        self.assertTrue(all(row["product_handle"] for row in rows))
        self.assertEqual(len({row["route_key"] for row in rows}), 3)

    def test_multiline_quotes_commas_and_unicode_round_trip_exactly(self):
        data = serialize_posting_import_csv(posting_rows())
        parsed = parse_posting_import_csv(
            data,
            allowed_countries=("AUS", "USA", "UK", "CAN", "NZ"),
            allowed_sports=("Motorsport", "NFL"),
            allowed_campaign_types=("Instant Experience",),
        )
        self.assertEqual(primary_ads(parsed), posting_ads())
        self.assertIn(b'""Six Laps""', data)
        headers = next(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        self.assertEqual(tuple(headers), POSTING_IMPORT_HEADERS)

    def test_new_ads_and_creative_refresh_export_identical_schema_and_values(self):
        workflow = ads_workflow()
        new_data = ads_page.build_ads_posting_import_csv(ads_result(), workflow)
        refresh_data = ads_page.build_ads_posting_import_csv(
            ads_result(workflow_mode=ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH),
            workflow,
        )
        new_batch = parse_posting_import_csv(new_data)
        refresh_batch = parse_posting_import_csv(refresh_data)
        self.assertEqual(new_batch["rows"], refresh_batch["rows"])
        self.assertEqual(new_batch["country"], "AUS")
        self.assertEqual(new_batch["sport_category"], "Motorsport")
        self.assertEqual(new_batch["campaign_type"], "Instant Experience")
        self.assertEqual(new_batch["ads"][0]["primary_text"], posting_ads()[0]["primary_text"])
        self.assertEqual(new_batch["ads"][2]["headline"], posting_ads()[2]["headline"])
        self.assertEqual(len(new_batch["ads"][0]["variations"]), 3)
        self.assertEqual(
            new_batch["ads"][1]["variations"][2]["primary_text"],
            "Alternative 2B",
        )
        self.assertEqual(
            new_data,
            ads_page.build_instant_experience_copy_csv(ads_result(), workflow),
        )

    def test_named_standard_ads_fields_map_without_display_text_reconstruction(self):
        result = ads_result()
        result["standard_ads"] = tuple(
            {
                **ad,
                "strategy": f"Strategy {ad['ad_number']}",
                "image_prompt": f"Standalone prompt {ad['ad_number']}",
            }
            for ad in posting_ads()
        )
        parsed = parse_posting_import_csv(
            ads_page.build_ads_posting_import_csv(result, ads_workflow())
        )
        self.assertEqual(primary_ads(parsed), posting_ads())

    def test_package_adds_posting_csv_without_changing_text_exports(self):
        result = ads_result()
        workflow = ads_workflow()
        for concept in INSTANT_EXPERIENCE_CONCEPTS:
            workflow["slots"][concept["slot_id"]] = {
                "valid": True,
                "data": b"original-image-bytes",
                "original_name": f"{concept['id']}.png",
                "source_format": "PNG",
                "source_width": 1024,
                "source_height": 1024,
            }
        items = ads_page._instant_experience_package_items(result, workflow)
        item_by_path = {item["relative_path"]: item for item in items}
        self.assertIn(POSTING_IMPORT_FILENAME, item_by_path)
        stored_batch = parse_posting_import_csv(
            item_by_path[POSTING_IMPORT_FILENAME]["data"]
        )
        self.assertEqual(len(stored_batch["rows"]), 9)
        self.assertEqual(
            stored_batch["ads"][2]["variations"][1]["headline"],
            "Alternative headline 3A",
        )
        self.assertEqual(
            item_by_path[
                "01-premium-scarcity-right/01-legacy-standard/primary-text.txt"
            ]["data"],
            posting_ads()[0]["primary_text"].encode("utf-8"),
        )
        self.assertEqual(
            item_by_path[
                "01-premium-scarcity-right/01-legacy-standard/headline.txt"
            ]["data"],
            posting_ads()[0]["headline"].encode("utf-8"),
        )

    def test_description_can_be_blank(self):
        parsed = parse_posting_import_csv(serialize_posting_import_csv(posting_rows()))
        self.assertEqual(parsed["ads"][1]["description"], "")

    def test_invalid_schema_missing_row_duplicate_number_and_conflicts_are_rejected(self):
        cases = []
        rows = [dict(row) for row in posting_rows()]
        invalid_schema = [dict(row) for row in rows]
        invalid_schema[0]["schema_version"] = "OLD"
        cases.append((invalid_schema, "schema_version"))
        cases.append((rows[:-1], "exactly 9"))
        duplicate = [dict(row) for row in rows]
        duplicate[1] = dict(duplicate[0])
        cases.append((duplicate, "duplicated"))
        conflicting_handle = [dict(row) for row in rows]
        conflicting_handle[-1]["product_handle"] = "another-product"
        cases.append((conflicting_handle, "does not match product_url"))
        conflicting_country = [dict(row) for row in rows]
        conflicting_country[-1]["country"] = "USA"
        cases.append((conflicting_country, "Conflicting"))
        for candidate, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(PostingImportCSVError, message):
                    serialize_posting_import_csv(candidate)

    def test_excel_and_sheets_safe_headers_bom_newlines_and_filename(self):
        canonical = serialize_posting_import_csv(posting_rows()).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(canonical, newline="")))
        reordered_headers = tuple(reversed(POSTING_IMPORT_HEADERS))
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output,
            fieldnames=[f"  {header.replace('_', ' ').title()}  " for header in reordered_headers],
            lineterminator="\n",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    f"  {header.replace('_', ' ').title()}  ": row[header]
                    for header in reordered_headers
                }
            )
        edited = output.getvalue().encode("utf-8-sig")

        parsed = parse_posting_import_csv(edited, filename="ChatGPT completed output")

        self.assertEqual(primary_ads(parsed), posting_ads())
        self.assertEqual(
            parsed["ads"][0]["variations"][0]["primary_text"],
            posting_ads()[0]["primary_text"],
        )

    def test_immediately_previous_three_row_posting_csv_remains_supported(self):
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=POSTING_IMPORT_LEGACY_HEADERS)
        writer.writeheader()
        for ad in posting_ads():
            writer.writerow(
                {
                    "schema_version": POSTING_IMPORT_LEGACY_SCHEMA_VERSION,
                    "product_name": "Six Laps Ahead Peter Brock Wall Art",
                    "product_handle": "peter-brock-bathurst-wall-art",
                    "product_url": "https://www.sportscaveshop.com/products/peter-brock-bathurst-wall-art",
                    "country": "AUS",
                    "sport_category": "Motorsport",
                    "campaign_type": "Instant Experience",
                    **ad,
                }
            )
        parsed = parse_posting_import_csv(output.getvalue().encode("utf-8-sig"))
        self.assertEqual(primary_ads(parsed), posting_ads())
        self.assertEqual(parsed["source_schema_version"], POSTING_IMPORT_LEGACY_SCHEMA_VERSION)

    def test_new_ads_and_refresh_round_trip_import_save_and_posting_hydration(self):
        for workflow_mode in (
            ads_page.ADS_WORKFLOW_MODE_NEW,
            ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH,
        ):
            with self.subTest(workflow_mode=workflow_mode):
                result = ads_result(workflow_mode=workflow_mode)
                completed_csv = ads_page.build_instant_experience_copy_csv(
                    result,
                    ads_workflow(),
                )
                imported_workflow = {"ad_notes": {}, "slots": {}}
                ads_state = {}
                with mock.patch.object(ads_page.st, "session_state", ads_state):
                    status = ads_page._process_instant_experience_copy_csv_upload(
                        result,
                        imported_workflow,
                        FakeUpload(
                            completed_csv,
                            name="ChatGPT completed.csv",
                            file_id=f"ads-{workflow_mode}",
                        ),
                    )
                self.assertTrue(status["ok"])
                self.assertEqual(status["message"], "CSV imported — ad copy applied")
                self.assertTrue(ads_page.instant_experience_copy_complete(imported_workflow))
                for concept in INSTANT_EXPERIENCE_CONCEPTS:
                    imported_workflow["slots"][concept["slot_id"]] = {
                        "valid": True,
                        "data": f"image-{concept['id']}".encode("utf-8"),
                        "original_name": f"{concept['id']}.png",
                        "source_format": "PNG",
                        "source_width": 1024,
                        "source_height": 1024,
                    }

                stored_items = {
                    item["relative_path"]: item
                    for item in ads_page._instant_experience_package_items(
                        result,
                        imported_workflow,
                    )
                }
                self.assertIn(POSTING_IMPORT_FILENAME, stored_items)
                stored_csv = stored_items[POSTING_IMPORT_FILENAME]["data"]
                self.assertEqual(stored_csv, completed_csv)
                stored_batch = parse_posting_import_csv(stored_csv)
                self.assertEqual(len(stored_batch["rows"]), 9)

                posting_state = {ads_posting_page.AUDIENCE_KEY: "broad"}
                posting_status = ads_posting_page.process_posting_csv_upload(
                    FakeUpload(
                        stored_csv,
                        name="saved-ad-copy-any-name.csv",
                        file_id=f"posting-{workflow_mode}",
                    ),
                    product_records(),
                    state=posting_state,
                )
                self.assertTrue(posting_status["ok"])
                for index, expected in enumerate(posting_ads()):
                    self.assertEqual(
                        posting_state[ads_posting_page.PRIMARY_TEXT_KEYS[index]],
                        expected["primary_text"],
                    )
                    self.assertEqual(
                        posting_state[ads_posting_page.HEADLINE_KEYS[index]],
                        expected["headline"],
                    )
                    self.assertEqual(
                        posting_state[ads_posting_page.DESCRIPTION_KEYS[index]],
                        expected["description"],
                    )


class PostingCSVImportTests(unittest.TestCase):
    def test_product_matches_by_handle_and_canonical_url_wins(self):
        data = serialize_posting_import_csv(
            posting_rows(
                product_url=(
                    "https://legacy.example/products/"
                    "peter-brock-bathurst-wall-art"
                )
            )
        )
        upload = FakeUpload(data, name=POSTING_IMPORT_FILENAME, file_id="csv-1")
        state = {ads_posting_page.AUDIENCE_KEY: "broad"}
        status = ads_posting_page.process_posting_csv_upload(
            upload,
            product_records(),
            state=state,
        )
        self.assertTrue(status["ok"])
        self.assertEqual(
            status["summary"]["product_url"],
            "https://www.sportscaveshop.com/products/peter-brock-bathurst-wall-art",
        )
        self.assertEqual(state[ads_posting_page.COUNTRY_KEY], "AUS")
        self.assertEqual(state[ads_posting_page.SPORT_KEY], "Motorsport")
        self.assertEqual(state[ads_posting_page.AUDIENCE_KEY], "broad")
        self.assertEqual(
            state[ads_posting_page.PRIMARY_TEXT_KEYS[0]],
            posting_ads()[0]["primary_text"],
        )
        self.assertEqual(
            state[ads_posting_page.HEADLINE_KEYS[1]],
            posting_ads()[1]["headline"],
        )
        self.assertEqual(
            state[ads_posting_page.DESCRIPTION_KEYS[2]],
            posting_ads()[2]["description"],
        )

    def test_import_is_local_only_and_cached_by_uploaded_file_identity(self):
        upload = FakeUpload(
            serialize_posting_import_csv(posting_rows()),
            name=POSTING_IMPORT_FILENAME,
            file_id="csv-cached",
        )
        state = {}
        with mock.patch.object(
            ads_posting_page,
            "_load_meta_references",
            side_effect=AssertionError("Meta discovery must not run"),
        ), mock.patch.object(
            ads_posting_page.MetaPostingClient,
            "upload_image",
            side_effect=AssertionError("Meta writes must not run"),
        ):
            first = ads_posting_page.process_posting_csv_upload(
                upload, product_records(), state=state
            )
            second = ads_posting_page.process_posting_csv_upload(
                upload, product_records(), state=state
            )
        self.assertTrue(first["ok"])
        self.assertEqual(second, first)
        self.assertEqual(upload.getvalue_calls, 1)

    def test_failed_import_does_not_destroy_existing_form_state(self):
        upload = FakeUpload(
            b"wrong,headers\n1,2\n",
            name=POSTING_IMPORT_FILENAME,
            file_id="csv-invalid",
        )
        state = {
            ads_posting_page.PRIMARY_TEXT_KEYS[0]: "Keep this text",
            ads_posting_page.HEADLINE_KEYS[0]: "Keep this headline",
            ads_posting_page.PRODUCT_KEY: "existing-product",
        }
        before = dict(state)
        status = ads_posting_page.process_posting_csv_upload(
            upload, product_records(), state=state
        )
        self.assertFalse(status["ok"])
        for key, value in before.items():
            self.assertEqual(state[key], value)

    def test_invalid_country_is_rejected(self):
        rows = [dict(row) for row in posting_rows()]
        for row in rows:
            row["country"] = "US"
        with self.assertRaisesRegex(PostingImportCSVError, "Country must be"):
            serialize_posting_import_csv(rows)


class PostingImageCaptureTests(unittest.TestCase):
    @staticmethod
    def large_png():
        output = io.BytesIO()
        Image.new("RGB", (1080, 1350), (25, 35, 45)).save(output, format="PNG")
        data = output.getvalue()
        return data + (b"\x00" * max(0, (5 * 1024 * 1024 // 2) - len(data)))

    def test_two_to_five_mb_image_is_captured_once_and_survives_rerun(self):
        upload = FakeUpload(
            self.large_png(),
            name="creative-1.png",
            file_id="image-1",
            content_type="image/png",
        )
        with mock.patch.object(
            ads_posting_page,
            "inspect_meta_posting_image_upload",
            wraps=ads_posting_page.inspect_meta_posting_image_upload,
        ) as inspect, mock.patch.object(
            ads_posting_page,
            "build_instant_experience_preview_thumbnail",
            wraps=ads_posting_page.build_instant_experience_preview_thumbnail,
        ) as preview:
            first = ads_posting_page.capture_posting_image_upload(upload)
            second = ads_posting_page.capture_posting_image_upload(upload, first)
        self.assertTrue(first["valid"])
        self.assertGreaterEqual(first["source_size"], 2 * 1024 * 1024)
        self.assertEqual(second["data"], first["data"])
        self.assertEqual(upload.getvalue_calls, 1)
        inspect.assert_called_once()
        preview.assert_called_once()

    def test_all_three_image_slots_are_local_only(self):
        state = {}
        uploads = [
            FakeUpload(
                self.large_png(),
                name=f"creative-{index}.png",
                file_id=f"image-{index}",
                content_type="image/png",
            )
            for index in range(1, 4)
        ]
        with mock.patch.object(
            ads_posting_page,
            "_load_meta_references",
            side_effect=AssertionError("Meta discovery must not run"),
        ), mock.patch.object(
            ads_posting_page.MetaPostingClient,
            "upload_image",
            side_effect=AssertionError("Meta upload must wait for Create"),
        ):
            captured = [
                ads_posting_page._sync_posting_image_upload(
                    index, upload, state=state
                )
                for index, upload in enumerate(uploads, start=1)
            ]
        self.assertTrue(all(item["valid"] for item in captured))
        self.assertTrue(
            all(key in state for key in ads_posting_page.IMAGE_STATE_KEYS)
        )
        self.assertEqual([upload.getvalue_calls for upload in uploads], [1, 1, 1])


if __name__ == "__main__":
    unittest.main()
