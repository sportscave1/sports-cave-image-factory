import ast
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import unittest
from unittest import mock

from PIL import Image
from streamlit.testing.v1 import AppTest

import ads_page as ads
import ads_posting_page as posting
import ads_posting_handoff as handoff
from ads_meta_contract import META_DEFAULT_CTA
from meta_posting_service import build_carousel_creative_payload
from posting_import_csv import parse_posting_import_csv, serialize_carousel_posting_import_csv
from tests.test_ads_page import carousel_csv_notes, instant_experience_csv_notes
from tests.test_posting_import_csv import ads_result, product_records


def completed_ad(ad_type="Carousel", source=ads.ADS_WORKFLOW_MODE_NEW, marker="final"):
    result = {**ads_result(workflow_mode=source), "campaign_type": ad_type}
    result["product_id"] = product_records()[0]["row"]["shopify_product_id"]
    result["context_key"] = f"{source}:{ad_type}:{marker}"
    workflow = {"context_key": result["context_key"], "slots": {}, "outcomes": {},
                "export_date": "2026-09-04", "ad_notes": {}}
    if ad_type == "Carousel":
        copy = carousel_csv_notes()
        for card in copy["cards"]:
            card["destination_url"] = result["product_url"]
            card["headline"] = f"{marker} {card['position']}"
        ads._store_carousel_copy_notes(workflow, copy)
    else:
        copy = instant_experience_csv_notes()
        for variations in copy.values():
            for variation in variations:
                variation["headline"] = marker + " " + variation["headline"]
        workflow["ad_notes"]["instant_experience_concepts"] = copy
    for spec in ads.ads_image_workflow.campaign_image_slots(ad_type):
        output = io.BytesIO()
        Image.new("RGB", (96, 96), (spec["position"] * 35, 80, len(marker) * 10)).save(output, "PNG")
        data = output.getvalue()
        details = ads.ads_image_workflow.inspect_instant_experience_original(data, original_name="same-name.png")
        if ad_type == "Carousel":
            details = ads.ads_image_workflow.optimize_meta_image(data, original_name="same-name.png")
        workflow["slots"][spec["id"]] = {
            **details, "data": details.get("data", data), "valid": True,
            "slot_id": spec["id"], "position": spec["position"],
        }
    return result, workflow


def save_locally(result, workflow, *, fail="", collision=False):
    uploaded = {}
    def upload(_token, folder, items, **_kwargs):
        successes, failures = [], []
        for item in items:
            name = item["relative_path"]
            path = folder + "/" + name
            if fail and fail in name:
                failures.append({"relative_path": name, "error": "Simulated failure"})
            else:
                uploaded[path] = bytes(item["data"])
                successes.append({"relative_path": name, "metadata": {
                    "id": "id:" + name, "rev": "test-rev", "path_display": path,
                }})
        return {"successes": successes, "failures": failures}
    with (
        mock.patch.object(ads.st, "session_state", {}),
        mock.patch.object(ads.dropbox_integration, "ensure_folder_path"),
        mock.patch.object(ads.dropbox_integration, "get_metadata_if_exists", return_value={} if not collision else {"id": "existing"}),
        mock.patch.object(ads.dropbox_integration, "windows_numbered_path", side_effect=lambda _token, path: path[:-4] + " (1).jpg"),
        mock.patch.object(ads.dropbox_integration, "upload_batch", side_effect=upload),
        mock.patch.object(posting, "MetaPostingClient", side_effect=AssertionError("No Meta client during save")),
        mock.patch.object(posting.MetaPostingService, "create_paused_campaign", side_effect=AssertionError("No publishing during save")),
    ):
        workflow["outcomes"] = ads.save_ads_images_to_dropbox(
            "test-token", "/approved", "/approved", result, workflow,
        )
    return uploaded


class SavedPackageTests(unittest.TestCase):
    def test_four_flows_keep_exact_uploaded_assets_copy_and_csv_equivalence(self):
        for source in (ads.ADS_WORKFLOW_MODE_NEW, ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH):
            for ad_type in ("Carousel", "Instant Experience"):
                with self.subTest(source=source, ad_type=ad_type):
                    result, workflow = completed_ad(ad_type, source, "refreshed")
                    self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
                    uploaded = save_locally(result, workflow, collision=ad_type == "Carousel")
                    self.assertNotIn("posting_package_error", workflow, workflow.get("posting_package_error"))
                    package = workflow[handoff.SAVED_PACKAGE_KEY]
                    self.assertEqual(package["source"], "Creative Refresh" if source == ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH else "New Ads")
                    self.assertEqual(package["source_signature"], ads._ads_saved_source_signature(result, workflow))
                    for file in package["files"]:
                        self.assertEqual(file["sha256"], hashlib.sha256(uploaded[file["path"]]).hexdigest())
                    state = {posting.AUDIENCE_KEY: "broad", "unrelated": "keep"}
                    handoff.queue_saved_package(package, state=state)
                    self.assertTrue(posting.consume_saved_posting_package(product_records(), state=state))
                    self.assertEqual(state[posting.AD_TYPE_KEY], ad_type)
                    self.assertEqual(state[posting.COUNTRY_KEY], "AUS")
                    self.assertEqual(state[posting.SPORT_KEY], "Motorsport")
                    self.assertEqual(state[posting.PRODUCT_KEY], product_records()[0]["identity"])
                    self.assertEqual(state[posting.SAVED_PRODUCT_URL_KEY]["url"], result["product_url"])
                    self.assertEqual(state["unrelated"], "keep")
                    image_keys = posting.CAROUSEL_IMAGE_STATE_KEYS if ad_type == "Carousel" else posting.IMAGE_STATE_KEYS
                    for spec, key, asset in zip(ads.ads_image_workflow.campaign_image_slots(ad_type), image_keys, package["assets"]):
                        record = state[key]
                        self.assertEqual(record["data"], uploaded[asset["path"]])
                        self.assertEqual(record["source_hash"], asset["processed_hash"])
                        self.assertEqual(record["saved_asset"]["slot_id"], spec["id"])
                        self.assertEqual(record["saved_asset"]["position"], spec["position"])
                        self.assertEqual(record["saved_asset"]["concept_id"], spec.get("concept_id"))
                        self.assertEqual(record["name"], asset["filename"])
                    if ad_type == "Carousel":
                        canonical = ads.parse_carousel_copy_csv(package["copy_csv"], result)
                        self.assertEqual(canonical["cards"], package["source_copy"]["cards"])
                        self.assertEqual(canonical["headlines"], package["source_copy"]["headlines"])
                        self.assertEqual(canonical["descriptions"], package["source_copy"]["descriptions"])
                        csv = serialize_carousel_posting_import_csv(package["batch"]["rows"])
                        fields = (*posting.CAROUSEL_HEADLINE_KEYS, *posting.CAROUSEL_DESCRIPTION_KEYS, *posting.CAROUSEL_PRIMARY_TEXT_KEYS)
                        self.assertIn("refreshed", state[posting.CAROUSEL_HEADLINE_KEYS[0]])
                    else:
                        csv = package["copy_csv"]
                        fields = (*posting.PRIMARY_TEXT_KEYS, *posting.HEADLINE_KEYS)
                        self.assertEqual(len(state[posting.ADS_COPY_ROUTES_STATE_KEY]), 3)
                        self.assertEqual(sum(len(ad["variations"]) for ad in state[posting.ADS_COPY_ROUTES_STATE_KEY]), 9)
                        self.assertIn("refreshed", state[posting.HEADLINE_KEYS[0]])
                        for index, concept in enumerate(ads.INSTANT_EXPERIENCE_CONCEPTS):
                            saved = package["source_copy"][concept["id"]]
                            self.assertEqual(state[posting.PRIMARY_TEXT_KEYS[index]], saved[index]["primary_text"])
                            self.assertEqual(state[posting.HEADLINE_KEYS[index]], saved[0]["headline"])
                    manual = {}
                    posting.apply_posting_import_to_state(parse_posting_import_csv(csv), product_records(), state=manual)
                    for key in fields:
                        self.assertEqual(state[key], manual[key])
                    request = posting._build_posting_request(
                        submission_id="local-only", product_id="", product_title=result["product_name"],
                        product_handle=package["batch"]["product_handle"], product_url=result["product_url"],
                        country="AUS", sport="Motorsport", catalog_id="", product_set_id="", audience={},
                        creatives=[{"image": state[key]} for key in image_keys] if ad_type == "Instant Experience" else [],
                        carousel_cards=[{"image": state[key]} for key in image_keys] if ad_type == "Carousel" else [],
                        ad_type=ad_type,
                    )
                    self.assertEqual([row.image_bytes for row in (request.carousel_cards or request.creatives)], [a["data"] for a in package["assets"]])

    def test_failures_partial_save_and_retry(self):
        for ad_type, failed_file in (("Carousel", "carousel-copy.csv"), ("Instant Experience", "ad-copy.txt")):
            with self.subTest(ad_type=ad_type):
                result, workflow = completed_ad(ad_type)
                save_locally(result, workflow)
                self.assertIn(handoff.SAVED_PACKAGE_KEY, workflow)
                # Match the actual package filename rather than assuming a CSV name.
                if ad_type == "Carousel":
                    failed_file = ads.CAROUSEL_COPY_FILENAME
                save_locally(result, workflow, fail=failed_file)
                self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
                self.assertTrue(workflow["slots"])
                save_locally(result, workflow)
                self.assertIn(handoff.SAVED_PACKAGE_KEY, workflow)
        result, workflow = completed_ad()
        workflow["slots"].pop("carousel-05")
        save_locally(result, workflow)
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)

    def test_unsaved_changes_and_another_ad_change_signature(self):
        for ad_type in ("Carousel", "Instant Experience"):
            result, workflow = completed_ad(ad_type)
            save_locally(result, workflow)
            original = workflow[handoff.SAVED_PACKAGE_KEY]["source_signature"]
            changed = deepcopy(result)
            changed["product_name"] = "Another ad"
            self.assertNotEqual(original, ads._ads_saved_source_signature(changed, workflow))
            for field in ("product_url", "context_key", "country", "workflow_mode"):
                changed = {**result, field: "changed"}
                self.assertNotEqual(original, ads._ads_saved_source_signature(changed, workflow))
            edited = deepcopy(workflow)
            if ad_type == "Carousel":
                edited["ad_notes"]["carousel"]["primary_texts"][0] = "changed"
            else:
                edited["ad_notes"]["instant_experience_concepts"][ads.INSTANT_EXPERIENCE_CONCEPTS[0]["id"]][0]["headline"] = "changed"
            self.assertNotEqual(original, ads._ads_saved_source_signature(result, edited))
            edited = deepcopy(workflow)
            next(iter(edited["slots"].values()))["data"] = b"replacement"
            self.assertNotEqual(original, ads._ads_saved_source_signature(result, edited))

    def test_incompatible_carousel_destination_preserves_saved_outputs_and_explains_failure(self):
        result, workflow = completed_ad()
        workflow["ad_notes"]["carousel"]["cards"][0]["destination_url"] = "https://example.com/different"
        uploaded = save_locally(result, workflow)
        self.assertTrue(uploaded)
        self.assertEqual(workflow["outcomes"]["_carousel_copy_csv"]["status"], "saved")
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
        self.assertIn("different destination URL", workflow["posting_package_error"])

    def test_legacy_empty_and_absent_carousel_ctas_do_not_block_readiness(self):
        for cta in ("Learn More", "Claim Your Edition", "", None):
            with self.subTest(cta=cta):
                result, workflow = completed_ad()
                for card in workflow["ad_notes"]["carousel"]["cards"]:
                    if cta is None:
                        card.pop("cta")
                    else:
                        card["cta"] = cta
                save_locally(result, workflow)
                self.assertNotIn("posting_package_error", workflow)
                package = workflow[handoff.SAVED_PACKAGE_KEY]
                self.assertIs(handoff.validate_saved_package(package), package)
                self.assertEqual(len(package["assets"]), 5)

    def test_legacy_csv_hydrates_exact_copy_and_images_with_fixed_shop_now_payload(self):
        result, workflow = completed_ad()
        original = deepcopy(workflow["ad_notes"]["carousel"])
        for card, cta in zip(original["cards"], ("Learn More", "Claim Your Edition", "", "Sign Up", "SHOP_NOW")):
            card["cta"] = cta
        legacy_csv = ads.build_carousel_copy_csv(result, carousel_notes=original)
        self.assertEqual(ads.parse_carousel_copy_csv(legacy_csv, result), original)
        stale_key = ads._carousel_card_widget_key(result["context_key"], 1, "cta")
        with mock.patch.object(ads.st, "session_state", {stale_key: "A stale editable CTA"}):
            ads.apply_carousel_copy_csv(result, workflow, legacy_csv)
            self.assertEqual(ads._carousel_copy_notes_with_widget_state(result, workflow)["cards"][0]["cta"], "Learn More")
        uploaded = save_locally(result, workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        state = {}
        handoff.queue_saved_package(package, state=state)
        self.assertTrue(posting.consume_saved_posting_package(product_records(), state=state))
        # The original CSV and every variation/card field survive in the loaded
        # source package; CTA metadata cannot override the native Meta button.
        loaded = state[handoff.LOADED_KEY]
        self.assertEqual(loaded, package)
        for field in ("headlines", "descriptions", "primary_texts", "setup_notes"):
            self.assertEqual(loaded["source_copy"][field], original[field])
        cards = []
        for index, asset in enumerate(package["assets"]):
            source = loaded["source_copy"]["cards"][index]
            for field in ads.CAROUSEL_CARD_FIELDS:
                self.assertEqual(source[field], original["cards"][index][field])
            image = state[posting.CAROUSEL_IMAGE_STATE_KEYS[index]]
            self.assertEqual(image["data"], uploaded[asset["path"]])
            self.assertEqual(image["saved_asset"]["position"], index + 1)
            self.assertEqual(image["saved_asset"]["slot_id"], f"carousel-{index + 1:02d}")
            self.assertEqual(state[posting.CAROUSEL_HEADLINE_KEYS[index]], source["headline"])
            self.assertEqual(state[posting.CAROUSEL_DESCRIPTION_KEYS[index]], source["description"])
            cards.append({"image_hash": image["source_hash"],
                          "headline": state[posting.CAROUSEL_HEADLINE_KEYS[index]],
                          "description": state[posting.CAROUSEL_DESCRIPTION_KEYS[index]],
                          "cta": source["cta"]})
        primary = [state[key] for key in posting.CAROUSEL_PRIMARY_TEXT_KEYS]
        self.assertEqual(primary, original["primary_texts"])
        self.assertEqual(state[posting.COUNTRY_KEY], "AUS")
        self.assertEqual(state[posting.SAVED_PRODUCT_URL_KEY]["url"], result["product_url"])
        payload = build_carousel_creative_payload(
            name="Local CTA regression", page_id="test-page", instagram_user_id="test-ig",
            cards=cards, primary_texts=primary, destination_url=state[posting.SAVED_PRODUCT_URL_KEY]["url"],
        )
        link_data = payload["object_story_spec"]["link_data"]
        self.assertEqual(link_data["call_to_action"]["type"], META_DEFAULT_CTA)
        self.assertEqual([card["call_to_action"]["type"] for card in link_data["child_attachments"]], ["SHOP_NOW"] * 5)

    def test_saved_receipt_recovery_rejects_unsaved_copy_missing_images_and_failed_saves(self):
        for mutation in ("copy", "missing-image", "changed-image", "failed-notes", "failed-csv", "wrong-folder"):
            with self.subTest(mutation=mutation):
                result, workflow = completed_ad()
                save_locally(result, workflow)
                workflow.pop(handoff.SAVED_PACKAGE_KEY)
                if mutation == "copy":
                    workflow["ad_notes"]["carousel"]["primary_texts"][0] = "An unsaved edit"
                elif mutation == "missing-image":
                    workflow["slots"].pop("carousel-05")
                elif mutation == "changed-image":
                    workflow["slots"]["carousel-05"]["data"] = b"unsaved replacement"
                elif mutation in {"failed-notes", "failed-csv"}:
                    key = "_ad_setup_notes" if mutation == "failed-notes" else "_carousel_copy_csv"
                    workflow["outcomes"][key]["status"] = "failed"
                else:
                    workflow["outcomes"]["carousel-05"]["path"] = "/different-folder/image.jpg"
                ads._restore_saved_carousel_posting_package(result, workflow)
                self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)

    def test_instant_experience_creative_ctas_remain_exact(self):
        result, workflow = completed_ad("Instant Experience")
        original = deepcopy(workflow["ad_notes"]["instant_experience_concepts"])
        save_locally(result, workflow)
        state = {}
        handoff.queue_saved_package(workflow[handoff.SAVED_PACKAGE_KEY], state=state)
        posting.consume_saved_posting_package(product_records(), state=state)
        self.assertEqual(state[handoff.LOADED_KEY]["source_copy"], original)
        for route in state[posting.ADS_COPY_ROUTES_STATE_KEY]:
            expected = original[route["route_key"]]
            self.assertEqual([v["cta"] for v in route["variations"]], [v["cta"] for v in expected])

    def test_new_handoff_replaces_a_previous_complete_run_without_reusing_meta_ids(self):
        result, workflow = completed_ad()
        save_locally(result, workflow)
        state = {
            posting.SUBMISSION_ID_KEY: "previous-run", posting.RUN_STATE_KEY: "COMPLETE",
            posting.RESULT_KEY: {"status": "COMPLETE", "campaign_id": "previous-campaign"},
            posting.EXISTING_CAMPAIGN_KEY: "previous-campaign", posting.EXISTING_ADSET_KEY: "previous-adset",
            posting.CSV_IMPORT_KEY: "previous-upload", posting.CSV_IMPORT_STATE_KEY: {"ok": True},
        }
        handoff.queue_saved_package(workflow[handoff.SAVED_PACKAGE_KEY], state=state)
        posting.consume_saved_posting_package(product_records(), state=state)
        self.assertEqual(state[posting.RUN_STATE_KEY], "DRAFT")
        self.assertNotEqual(state[posting.SUBMISSION_ID_KEY], "previous-run")
        for key in (posting.RESULT_KEY, posting.EXISTING_CAMPAIGN_KEY, posting.EXISTING_ADSET_KEY, posting.CSV_IMPORT_KEY, posting.CSV_IMPORT_STATE_KEY):
            self.assertNotIn(key, state)

    def test_failed_save_exception_revokes_the_previous_handoff_without_losing_source(self):
        result, workflow = completed_ad("Instant Experience")
        save_locally(result, workflow)
        source_before = deepcopy(workflow["ad_notes"])
        with mock.patch.object(ads.st, "session_state", {}), mock.patch.object(
            ads.dropbox_integration, "ensure_folder_path", side_effect=RuntimeError("Dropbox unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "Dropbox unavailable"):
                ads.save_ads_images_to_dropbox("test-token", "/approved", "/approved", result, workflow)
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
        self.assertEqual(workflow["ad_notes"], source_before)
        self.assertEqual(len(workflow["slots"]), 3)

    def test_atomic_failure_and_meta_history_guard(self):
        result, workflow = completed_ad()
        save_locally(result, workflow)
        package = workflow[handoff.SAVED_PACKAGE_KEY]
        for mutation in ("corrupt", "missing-image", "bad-image", "bad-slot", "bad-type", "unmatched-product", "meta-history"):
            with self.subTest(mutation=mutation):
                state = {posting.PRIMARY_TEXT_KEYS[0]: "previous draft", posting.IMAGE_STATE_KEYS[0]: {"data": b"old"}}
                handoff.queue_saved_package(package, state=state)
                incoming = state[handoff.PENDING_KEY]["package"]
                if mutation == "corrupt":
                    incoming["copy_csv"] = b"bad"
                elif mutation == "missing-image":
                    incoming["assets"].pop()
                elif mutation == "bad-image":
                    incoming["assets"][-1]["data"] = b"not an image"
                    incoming["assets"][-1]["processed_hash"] = hashlib.sha256(b"not an image").hexdigest()
                elif mutation == "bad-slot":
                    incoming["assets"][0]["slot_id"] = "carousel-02"
                elif mutation == "bad-type":
                    incoming["ad_type"] = "unknown"
                elif mutation == "meta-history":
                    state[posting.RUN_STATE_KEY] = "FAILED"
                if mutation != "corrupt":
                    incoming["package_hash"] = handoff.content_hash({k: v for k, v in incoming.items() if k != "package_hash"})
                before = deepcopy(state)
                with self.assertRaises((handoff.SavedPackageError, posting.PostingImportCSVError)):
                    posting.consume_saved_posting_package([] if mutation == "unmatched-product" else product_records(), state=state)
                self.assertEqual(state, before)
                self.assertEqual(workflow[handoff.SAVED_PACKAGE_KEY], package)

    def test_switch_types_clear_stale_state_and_rerun_keeps_edits(self):
        state = {posting.AUDIENCE_KEY: "broad", posting.PRODUCT_SET_KEY: "old-product-set"}
        for ad_type in ("Carousel", "Instant Experience", "Carousel"):
            result, workflow = completed_ad(ad_type)
            save_locally(result, workflow)
            handoff.queue_saved_package(workflow[handoff.SAVED_PACKAGE_KEY], state=state)
            pending = deepcopy(state[handoff.PENDING_KEY])
            posting.consume_saved_posting_package(product_records(), state=state)
            absent = posting.IMAGE_STATE_KEYS if ad_type == "Carousel" else posting.CAROUSEL_IMAGE_STATE_KEYS
            self.assertTrue(all(key not in state for key in absent))
            self.assertNotIn(posting.PRODUCT_SET_KEY, state)
            self.assertEqual(state[posting.AUDIENCE_KEY], "broad")
            key = posting.CAROUSEL_PRIMARY_TEXT_KEYS[0] if ad_type == "Carousel" else posting.PRIMARY_TEXT_KEYS[0]
            state[key] = "Manual edit survives"
            state[handoff.PENDING_KEY] = pending
            with mock.patch.object(posting, "build_meta_posting_image_record", side_effect=AssertionError("No repeat decode")):
                self.assertFalse(posting.consume_saved_posting_package(product_records(), state=state))
            self.assertEqual(state[key], "Manual edit survives")


class HandoffUITests(unittest.TestCase):
    def test_carousel_copy_controls_are_visible_once_outside_expanders(self):
        result, workflow = completed_ad()
        app = AppTest.from_string('''
import streamlit as st
import ads_page
ads_page._render_carousel_setup_notes(st.session_state["result"], st.session_state["workflow"])
''')
        app.session_state["result"] = result
        app.session_state["workflow"] = workflow
        app.run(timeout=20)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.expander), 0)
        labels = [item.label for item in app.text_area] + [item.label for item in app.text_input]
        for index in range(1, 6):
            for label in (f"Headline variation {index}", f"Description variation {index}", f"Primary text variation {index}", f"Card {index} headline"):
                self.assertEqual(labels.count(label), 1)
            self.assertNotIn(f"Card {index} CTA", labels)
        self.assertTrue(any("Carousel always uses Shop Now" in item.value for item in app.caption))
        tree = ast.parse(Path(ads.__file__).read_text(encoding="utf-8"))
        renderer = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "render_supported_result")
        calls = [n.value.func.id for n in renderer.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)]
        self.assertLess(calls.index("_render_ads_image_slots"), calls.index("_render_ads_setup_notes"))
        self.assertLess(calls.index("_render_ads_setup_notes"), calls.index("_render_ads_image_save"))

    def test_post_now_navigation_hydration_edit_rerun_and_zero_meta_writes_all_four_flows(self):
        for source in (ads.ADS_WORKFLOW_MODE_NEW, ads.ADS_WORKFLOW_MODE_CREATIVE_REFRESH):
            for ad_type in ("Carousel", "Instant Experience"):
                with self.subTest(source=source, ad_type=ad_type):
                    result, workflow = completed_ad(ad_type, source)
                    if ad_type == "Carousel":
                        for card in workflow["ad_notes"]["carousel"]["cards"]:
                            card["cta"] = "Learn More"
                    save_locally(result, workflow)
                    with (
                        mock.patch.object(posting, "_meta_state", return_value=({}, {}, "", "")),
                        mock.patch.object(posting, "_product_rows_state", return_value=[r["row"] for r in product_records()]),
                        mock.patch.object(posting, "MetaPostingClient", side_effect=AssertionError("No Meta client during hydration")),
                        mock.patch.object(posting.MetaPostingService, "create_paused_campaign") as publish,
                        mock.patch.object(posting, "run_collection_validation_from_posting_state") as diagnostic,
                        mock.patch.object(posting, "run_collection_template_copy_from_posting_state") as template,
                    ):
                        app = AppTest.from_string('''
import streamlit as st
import ads_page, ads_posting_page
if st.session_state.get("current_page") == "Posting":
    ads_posting_page.render_page()
else:
    ads_page._render_saved_ad_post_now(st.session_state["result"], st.session_state["workflow"], source_matches=st.session_state.get("source_matches", True))
''')
                        app.session_state["result"] = result
                        app.session_state["workflow"] = {**workflow, handoff.SAVED_PACKAGE_KEY: None, "outcomes": {}}
                        app.run(timeout=20)
                        self.assertNotIn("POST NOW", [button.label for button in app.button])
                        app.session_state["workflow"] = workflow
                        app.session_state["source_matches"] = False
                        app.run(timeout=20)
                        self.assertNotIn("POST NOW", [button.label for button in app.button])
                        app.session_state["source_matches"] = True
                        app.run(timeout=20)
                        self.assertIn("POST NOW", [button.label for button in app.button])
                        self.assertFalse(any("CTA is incompatible" in item.value for item in app.info))
                        app.button[0].click().run(timeout=20)
                        self.assertEqual(len(app.exception), 0)
                        self.assertEqual(app.session_state[posting.AD_TYPE_KEY], ad_type)
                        self.assertEqual(app.query_params["page"], ["ads_posting"])
                        primary = next(item for item in app.text_area if item.label == "Primary Text 1")
                        primary.set_value("Reviewed manual edit").run(timeout=20)
                        app.run(timeout=20)
                        self.assertEqual(len(app.exception), 0)
                        self.assertEqual(next(item for item in app.text_area if item.label == "Primary Text 1").value, "Reviewed manual edit")
                        publish.assert_not_called()
                        diagnostic.assert_not_called()
                        template.assert_not_called()

    def test_previously_cta_blocked_save_recovers_post_now_without_upload_or_copy_edits(self):
        result, workflow = completed_ad()
        workflow["ad_notes"]["carousel"]["cards"][0]["cta"] = "Claim Your Edition"
        old_error = "Card 1 CTA is incompatible with Posting's fixed Shop Now CTA."
        with mock.patch.object(handoff, "build_saved_package", side_effect=handoff.SavedPackageError(old_error)):
            uploaded = save_locally(result, workflow, collision=True)
        self.assertNotIn(handoff.SAVED_PACKAGE_KEY, workflow)
        self.assertEqual(workflow["posting_package_error"], old_error)
        original_notes = deepcopy(workflow["ad_notes"])
        with mock.patch.object(ads.dropbox_integration, "upload_batch", side_effect=AssertionError("No re-save")):
            app = AppTest.from_string('''
import streamlit as st
import ads_page
ads_page._render_saved_ad_post_now(st.session_state["result"], st.session_state["workflow"])
''')
            app.session_state["result"], app.session_state["workflow"] = result, workflow
            app.run(timeout=20)
            self.assertEqual(len(app.exception), 0)
            self.assertIn("POST NOW", [button.label for button in app.button])
            restored = app.session_state["workflow"]
            self.assertNotIn("posting_package_error", restored)
            self.assertEqual(restored["ad_notes"], original_notes)
            package = restored[handoff.SAVED_PACKAGE_KEY]
            for file in package["files"]:
                self.assertEqual(file["sha256"], hashlib.sha256(uploaded[file["path"]]).hexdigest())


if __name__ == "__main__":
    unittest.main()
