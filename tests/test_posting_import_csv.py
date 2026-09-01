import csv
import io
import unittest
from unittest import mock

from PIL import Image

import ads_page
import ads_image_workflow
import ads_posting_page
from ads_image_contracts import INSTANT_EXPERIENCE_CONCEPTS
from posting_import_csv import (
    ADS_COPY_HEADERS,
    POSTING_IMPORT_FILENAME,
    POSTING_IMPORT_HEADERS,
    POSTING_IMPORT_LEGACY_HEADERS,
    POSTING_IMPORT_LEGACY_SCHEMA_VERSION,
    POSTING_IMPORT_SCHEMA_VERSION,
    PostingImportCSVError,
    build_posting_import_rows,
    parse_ads_import_csv,
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

    def test_new_ads_and_creative_refresh_use_the_ads_copy_contract_not_posting(self):
        workflow = ads_workflow()
        new_result = ads_result()
        refresh_result = ads_result(
            workflow_mode=ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
        )
        new_data = ads_page.build_instant_experience_copy_csv(new_result, workflow)
        refresh_data = ads_page.build_instant_experience_copy_csv(
            refresh_result,
            workflow,
        )
        self.assertEqual(new_data, refresh_data)
        headers = tuple(
            next(csv.reader(io.StringIO(new_data.decode("utf-8-sig"))))
        )
        self.assertEqual(headers, ads_page.INSTANT_EXPERIENCE_COPY_CSV_HEADERS)
        self.assertNotEqual(headers, POSTING_IMPORT_HEADERS)
        with self.assertRaisesRegex(PostingImportCSVError, "no product details"):
            parse_posting_import_csv(new_data)

    def test_package_adds_current_ads_csv_without_changing_text_exports(self):
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
        csv_filename = ads_page._instant_experience_current_copy_csv_filename(result)
        self.assertIn(csv_filename, item_by_path)
        self.assertNotIn(POSTING_IMPORT_FILENAME, item_by_path)
        stored_copy = ads_page.parse_instant_experience_copy_csv(
            item_by_path[csv_filename]["data"],
            result,
        )
        self.assertEqual(
            stored_copy[INSTANT_EXPERIENCE_CONCEPTS[2]["id"]][1]["headline"],
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

    def test_previous_working_ads_copy_template_normalises_and_hydrates(self):
        result = ads_result()
        canonical = ads_page.build_instant_experience_copy_csv(
            result, ads_workflow()
        ).decode("utf-8-sig")
        source_rows = list(csv.DictReader(io.StringIO(canonical, newline="")))
        decorated_headers = [
            f"  {header.replace('_', ' ').title()}  " for header in ADS_COPY_HEADERS
        ] + ["Editor Notes"]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=decorated_headers, lineterminator="\n")
        writer.writeheader()
        for source_row in source_rows:
            writer.writerow(
                {
                    **{
                        f"  {header.replace('_', ' ').title()}  ": source_row[header]
                        for header in ADS_COPY_HEADERS
                    },
                    "Editor Notes": "",
                }
            )
        edited = output.getvalue().encode("utf-8-sig")

        batch = parse_ads_import_csv(edited)
        self.assertEqual(batch["source_schema_kind"], "ads_copy")
        self.assertEqual(len(batch["rows"]), 9)

        workflow = {"ad_notes": {}, "slots": {}}
        state = {}
        with mock.patch.object(ads_page.st, "session_state", state):
            status = ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                FakeUpload(edited, name="ChatGPT result", file_id="ads-editor-file"),
            )
        self.assertTrue(status["ok"])
        self.assertEqual(status["message"], "CSV imported — ad copy applied.")
        self.assertTrue(ads_page.instant_experience_copy_complete(workflow))
        first_key = ads_page._instant_experience_copy_widget_key(
            result["context_key"],
            INSTANT_EXPERIENCE_CONCEPTS[0]["id"],
            "primary_text",
            1,
        )
        self.assertEqual(state[first_key], posting_ads()[0]["primary_text"])

    def test_blank_ads_template_can_be_filled_then_immediately_imported(self):
        result = ads_result()
        blank = ads_page.build_instant_experience_copy_csv(
            result, {}, blank=True
        ).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(blank, newline="")))
        expected = ads_workflow()["ad_notes"]["instant_experience_concepts"]
        for row in rows:
            variation = expected[row["route_key"]][int(row["variation"]) - 1]
            row["primary_text"] = variation["primary_text"]
            row["headline"] = variation["headline"]
            row["cta"] = variation["cta"]
        output = io.StringIO(newline="")
        writer = csv.DictWriter(
            output, fieldnames=ADS_COPY_HEADERS, lineterminator="\r\n"
        )
        writer.writeheader()
        writer.writerows(rows)

        imported = ads_page.parse_instant_experience_copy_csv(
            output.getvalue().encode("utf-8-sig"), result
        )

        for concept in INSTANT_EXPERIENCE_CONCEPTS:
            for index in range(3):
                self.assertEqual(
                    imported[concept["id"]][index]["primary_text"],
                    expected[concept["id"]][index]["primary_text"],
                )
                self.assertEqual(
                    imported[concept["id"]][index]["headline"],
                    expected[concept["id"]][index]["headline"],
                )
                self.assertEqual(
                    imported[concept["id"]][index]["cta"],
                    expected[concept["id"]][index]["cta"],
                )

    def test_ads_import_applies_once_per_file_but_new_upload_can_reapply(self):
        result = ads_result()
        data = ads_page.build_instant_experience_copy_csv(result, ads_workflow())
        workflow = {"ad_notes": {}, "slots": {}}
        state = {}
        first_key = ads_page._instant_experience_copy_widget_key(
            result["context_key"],
            INSTANT_EXPERIENCE_CONCEPTS[0]["id"],
            "primary_text",
            1,
        )
        first_upload = FakeUpload(
            data, name="completed.csv", file_id="same-browser-upload"
        )
        with mock.patch.object(ads_page.st, "session_state", state):
            ads_page._process_instant_experience_copy_csv_upload(
                result, workflow, first_upload
            )
            state[first_key] = "Manual edit after import"
            ads_page._process_instant_experience_copy_csv_upload(
                result, workflow, first_upload
            )
            self.assertEqual(state[first_key], "Manual edit after import")
            ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                FakeUpload(data, name="completed-again.csv", file_id="new-upload"),
            )
        self.assertEqual(state[first_key], posting_ads()[0]["primary_text"])
        self.assertEqual(first_upload.getvalue_calls, 1)

    def test_old_red_status_is_reparsed_and_replaced_by_green_success(self):
        result = ads_result()
        copy_data = ads_page.build_instant_experience_copy_csv(
            result, ads_workflow()
        )
        workflow = {
            "ad_notes": {},
            "slots": {},
            "copy_csv_import_file_id": "persisted-file",
            "copy_csv_import_runtime_version": "older-parser",
            "copy_csv_import_status": {"ok": False, "message": "Old red error"},
        }
        state = {}
        with mock.patch.object(ads_page.st, "session_state", state):
            ads_status = ads_page._process_instant_experience_copy_csv_upload(
                result,
                workflow,
                FakeUpload(
                    copy_data,
                    name="completed.csv",
                    file_id="persisted-file",
                ),
            )
        self.assertTrue(ads_status["ok"])
        self.assertEqual(ads_status["message"], "CSV imported — ad copy applied.")

        posting_data = serialize_posting_import_csv(posting_rows())
        posting_state = {
            ads_posting_page.CSV_IMPORT_STATE_KEY: {
                "ok": False,
                "message": "Old red error",
                "source_file_id": "persisted-posting-file",
                "runtime_version": "older-parser",
            }
        }
        posting_status = ads_posting_page.process_posting_csv_upload(
            FakeUpload(
                posting_data,
                name="posting-import.csv",
                file_id="persisted-posting-file",
            ),
            product_records(),
            state=posting_state,
        )
        self.assertTrue(posting_status["ok"])
        self.assertEqual(
            posting_status["message"], "CSV imported — ad copy applied."
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

    def test_new_ads_and_refresh_round_trip_import_export_and_save_independently(self):
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
                ads_state = {
                    ads_page.ADS_ACTIVE_WORKFLOW_MODE_KEY: workflow_mode,
                }
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
                    exported_again = ads_page.build_instant_experience_copy_csv(
                        result,
                        imported_workflow,
                    )
                self.assertTrue(status["ok"])
                self.assertEqual(status["message"], "CSV imported — ad copy applied.")
                self.assertTrue(ads_page.instant_experience_copy_complete(imported_workflow))
                self.assertEqual(exported_again, completed_csv)
                expected_state_key = (
                    ads_page.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY
                    if workflow_mode == ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
                    else ads_page.ADS_IMAGE_STATE_KEY
                )
                other_state_key = (
                    ads_page.ADS_IMAGE_STATE_KEY
                    if workflow_mode == ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
                    else ads_page.ADS_CREATIVE_REFRESH_IMAGE_STATE_KEY
                )
                self.assertIs(ads_state[expected_state_key], imported_workflow)
                self.assertNotIn(other_state_key, ads_state)
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
                csv_filename = ads_page._instant_experience_current_copy_csv_filename(
                    result
                )
                self.assertIn(csv_filename, stored_items)
                self.assertNotIn(POSTING_IMPORT_FILENAME, stored_items)
                stored_csv = stored_items[csv_filename]["data"]
                stored_copy = ads_page.parse_instant_experience_copy_csv(
                    stored_csv,
                    result,
                )
                self.assertEqual(
                    stored_copy,
                    ads_page.parse_instant_experience_copy_csv(completed_csv, result),
                )
                expected_slot = (
                    "_creative_refresh_copy_csv"
                    if workflow_mode == ads_page.ADS_WORKFLOW_MODE_CREATIVE_REFRESH
                    else "_new_ads_copy_csv"
                )
                self.assertEqual(stored_items[csv_filename]["slot_id"], expected_slot)
                with self.assertRaisesRegex(PostingImportCSVError, "no product details"):
                    parse_posting_import_csv(stored_csv)


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

        first_key = ads_posting_page.PRIMARY_TEXT_KEYS[0]
        state[first_key] = "Manual Posting edit"
        ads_posting_page.process_posting_csv_upload(
            upload, product_records(), state=state
        )
        self.assertEqual(state[first_key], "Manual Posting edit")
        ads_posting_page.process_posting_csv_upload(
            FakeUpload(
                upload._data,
                name="same-content-new-upload.csv",
                file_id="csv-new-selection",
            ),
            product_records(),
            state=state,
        )
        self.assertEqual(state[first_key], posting_ads()[0]["primary_text"])

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
    def image_data(image_format, *, colour=(25, 35, 45), size=(720, 900)):
        output = io.BytesIO()
        mode = "RGB"
        Image.new(mode, size, colour).save(output, format=image_format)
        return output.getvalue()

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
            ads_image_workflow,
            "inspect_meta_posting_image_upload",
            wraps=ads_image_workflow.inspect_meta_posting_image_upload,
        ) as inspect, mock.patch.object(
            ads_image_workflow,
            "build_instant_experience_preview_thumbnail",
            wraps=ads_image_workflow.build_instant_experience_preview_thumbnail,
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

    def test_jpeg_png_and_webp_slots_persist_when_widgets_reconstruct_empty(self):
        state = {}
        formats = (
            ("JPEG", "creative-1.jpg", "image/jpeg"),
            ("PNG", "creative-2.png", "image/png"),
            ("WEBP", "creative-3.webp", "image/webp"),
        )
        source_bytes = []
        for index, (image_format, name, content_type) in enumerate(formats, start=1):
            data = self.image_data(image_format, colour=(20 * index, 35, 45))
            source_bytes.append(data)
            captured = ads_posting_page._sync_posting_image_upload(
                index,
                FakeUpload(
                    data,
                    name=name,
                    file_id=f"format-{index}",
                    content_type=content_type,
                ),
                state=state,
            )
            self.assertTrue(captured["valid"])
            self.assertEqual(captured["source_format"], image_format)
            self.assertEqual(captured["source_bytes"], data)
            self.assertEqual(captured["data"], data)

        retained = [
            ads_posting_page._sync_posting_image_upload(index, None, state=state)
            for index in range(1, 4)
        ]
        self.assertEqual([row["data"] for row in retained], source_bytes)
        self.assertTrue(all(row["valid"] for row in retained))

    def test_replacing_second_slot_does_not_change_first_or_third(self):
        state = {}
        originals = []
        for index in range(1, 4):
            data = self.image_data("PNG", colour=(index * 30, 20, 10))
            originals.append(data)
            ads_posting_page._sync_posting_image_upload(
                index,
                FakeUpload(
                    data,
                    name=f"original-{index}.png",
                    file_id=f"original-{index}",
                    content_type="image/png",
                ),
                state=state,
            )
        replacement = self.image_data("PNG", colour=(200, 100, 50))
        ads_posting_page._sync_posting_image_upload(
            2,
            FakeUpload(
                replacement,
                name="replacement-2.png",
                file_id="replacement-2",
                content_type="image/png",
            ),
            state=state,
        )
        self.assertEqual(state[ads_posting_page.IMAGE_STATE_KEYS[0]]["data"], originals[0])
        self.assertEqual(state[ads_posting_page.IMAGE_STATE_KEYS[1]]["data"], replacement)
        self.assertEqual(state[ads_posting_page.IMAGE_STATE_KEYS[2]]["data"], originals[2])

    def test_csv_import_and_text_changes_do_not_clear_images(self):
        state = {ads_posting_page.AUDIENCE_KEY: "broad"}
        images = []
        for index in range(1, 4):
            data = self.image_data("PNG", colour=(10, index * 40, 20))
            images.append(data)
            ads_posting_page._sync_posting_image_upload(
                index,
                FakeUpload(
                    data,
                    name=f"creative-{index}.png",
                    file_id=f"creative-{index}",
                    content_type="image/png",
                ),
                state=state,
            )
        status = ads_posting_page.process_posting_csv_upload(
            FakeUpload(
                serialize_posting_import_csv(posting_rows()),
                name="posting-import.csv",
                file_id="copy-with-images",
            ),
            product_records(),
            state=state,
        )
        self.assertTrue(status["ok"])
        state[ads_posting_page.HEADLINE_KEYS[0]] = "Manual headline edit"
        self.assertEqual(
            [state[key]["data"] for key in ads_posting_page.IMAGE_STATE_KEYS],
            images,
        )

    def test_preview_failure_keeps_full_resolution_source_ready(self):
        source = self.image_data("PNG", size=(1400, 1800))
        upload = FakeUpload(
            source,
            name="full-resolution.png",
            file_id="preview-failure",
            content_type="image/png",
        )
        with mock.patch.object(
            ads_image_workflow,
            "build_instant_experience_preview_thumbnail",
            side_effect=OSError("preview unavailable"),
        ):
            captured = ads_posting_page.capture_posting_image_upload(upload)
        self.assertTrue(captured["valid"])
        self.assertEqual(captured["data"], source)
        self.assertEqual(captured["source_bytes"], source)
        self.assertEqual((captured["source_width"], captured["source_height"]), (1400, 1800))
        self.assertTrue(captured["preview_error"])

    def test_invalid_image_has_specific_error_and_is_not_ready(self):
        captured = ads_posting_page.capture_posting_image_upload(
            FakeUpload(
                b"not-an-image",
                name="broken.png",
                file_id="broken-image",
                content_type="image/png",
            )
        )
        self.assertFalse(captured["valid"])
        self.assertIn("corrupt", captured["error"].casefold())

    def test_same_metadata_without_file_id_uses_content_hash_for_replacement(self):
        first_data = self.image_data("PNG", colour=(10, 20, 30), size=(10, 10))
        second_data = self.image_data("PNG", colour=(30, 20, 10), size=(10, 10))
        self.assertEqual(len(first_data), len(second_data))
        first = FakeUpload(
            first_data,
            name="same.png",
            file_id="",
            content_type="image/png",
        )
        second = FakeUpload(
            second_data,
            name="same.png",
            file_id="",
            content_type="image/png",
        )
        original = ads_posting_page.capture_posting_image_upload(first)
        replacement = ads_posting_page.capture_posting_image_upload(second, original)
        self.assertNotEqual(original["source_hash"], replacement["source_hash"])
        self.assertEqual(replacement["data"], second_data)

    def test_review_request_receives_each_original_image_and_matching_copy(self):
        image_records = []
        for index, image_format in enumerate(("JPEG", "PNG", "WEBP"), start=1):
            data = self.image_data(image_format, colour=(index * 40, 25, 35))
            image_records.append(
                ads_posting_page.capture_posting_image_upload(
                    FakeUpload(
                        data,
                        name=f"creative-{index}.{image_format.casefold()}",
                        file_id=f"review-{index}",
                        content_type=f"image/{image_format.casefold()}",
                    )
                )
            )
        creatives = tuple(
            {
                "image": image_records[index - 1],
                "primary_text": f"Primary {index}",
                "headline": f"Headline {index}",
                "description": f"Description {index}",
            }
            for index in range(1, 4)
        )
        request = ads_posting_page._build_posting_request(
            submission_id="11111111-1111-4111-8111-111111111111",
            product_id="shopify-1",
            product_title="Product",
            product_handle="product",
            product_url="https://www.sportscaveshop.com/products/product",
            country="AUS",
            sport="Motorsport",
            catalog_id="catalog-1",
            product_set_id="set-1",
            audience={"type": "broad", "id": ""},
            creatives=creatives,
        )
        self.assertEqual(
            [creative.image_bytes for creative in request.creatives],
            [record["source_bytes"] for record in image_records],
        )
        self.assertEqual(
            [creative.primary_text for creative in request.creatives],
            ["Primary 1", "Primary 2", "Primary 3"],
        )
        self.assertEqual(
            [creative.headline for creative in request.creatives],
            ["Headline 1", "Headline 2", "Headline 3"],
        )


if __name__ == "__main__":
    unittest.main()
