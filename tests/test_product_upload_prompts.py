import hashlib
from pathlib import Path
import unittest

import app


ROOT = Path(__file__).resolve().parents[1]
NEW_PROMPT_SHA256 = "71092f128c8b2de679dbaed697fe393a8578ba1386aae27cd6e46eadd2d3bc6a"
EXISTING_PROMPT_SHA256 = "190193bdbbc70f29ccd981441eeee257d37805f8c602c06d09878cd7fa0dd5ed"


def legacy_generated_prompt(base_prompt):
    return (
        f"{str(base_prompt or '').strip()}\n\n"
        f"{app.product_upload_embedded_sections()}"
    ).strip()


def source_context():
    return {
        "dropbox_root_path": "/Sportscave Team Folder",
        "dropbox_product_folder": (
            "/Sportscave Team Folder/04_OUTPUT/product-images/"
            "O'Connor & São-Paulo - Legends"
        ),
        "product_name": "O'Connor & São-Paulo - Legends",
        "shopify_product_id": "987654321",
        "shopify_product_gid": "gid://shopify/Product/987654321",
        "shopify_handle": "oconnor-sao-paulo-legends-wall-art",
    }


class ProductUploadPromptReliabilityTests(unittest.TestCase):
    def new_prompt(self):
        return app.get_product_upload_prompt(source_context(), update_existing=False)

    def existing_prompt(self):
        return app.get_product_upload_prompt(source_context(), update_existing=True)

    def test_original_prompt_constants_are_byte_for_byte_unchanged(self):
        self.assertEqual(
            hashlib.sha256(app.NEW_SHOPIFY_PRODUCT_PROMPT.encode("utf-8")).hexdigest(),
            NEW_PROMPT_SHA256,
        )
        self.assertEqual(
            hashlib.sha256(app.UPDATE_EXISTING_PRODUCT_PROMPT.encode("utf-8")).hexdigest(),
            EXISTING_PROMPT_SHA256,
        )

    def test_only_change_to_each_generated_prompt_is_the_inserted_patch(self):
        for base_prompt, update_existing in (
            (app.NEW_SHOPIFY_PRODUCT_PROMPT, False),
            (app.UPDATE_EXISTING_PRODUCT_PROMPT, True),
        ):
            with self.subTest(update_existing=update_existing):
                legacy = legacy_generated_prompt(base_prompt)
                upgraded = app.get_product_upload_prompt(
                    source_context(),
                    update_existing=update_existing,
                )
                self.assertEqual(
                    app.remove_product_upload_media_reliability_patch(upgraded),
                    legacy,
                )
                self.assertTrue(upgraded.startswith(base_prompt.strip()))
                self.assertEqual(upgraded.count(app.PRODUCT_UPLOAD_MEDIA_PATCH_START), 1)
                self.assertLess(
                    upgraded.index(app.PRODUCT_UPLOAD_MEDIA_PATCH_START),
                    upgraded.index("ADDITIONAL REQUIRED SUB-PROMPTS"),
                )

    def test_both_prompts_use_dropbox_only_and_never_direct_google_drive_use(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            with self.subTest(prompt_start=prompt[:40]):
                self.assertIn("Dropbox is the only source of truth", prompt)
                self.assertIn("connected Sports Cave Dropbox/Team Space root", prompt)
                self.assertIn("Do not use Google Drive.", prompt)
                self.assertNotIn("drive.google.com", prompt.casefold())
                for line in prompt.splitlines():
                    if "Google Drive" in line:
                        self.assertTrue(
                            "Do not" in line or "Never" in line,
                            line,
                        )

    def test_every_supplied_webp_is_mandatory_validated_and_read_from_latest_dropbox(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            self.assertIn("every supplied Dropbox WebP", prompt)
            self.assertIn("Enumerate every supplied .webp file", prompt)
            self.assertIn("Use the latest Dropbox version", prompt)
            self.assertIn("has a valid WebP signature", prompt)
            self.assertIn("Fully download or hydrate every required file", prompt)
            self.assertIn("Do not silently skip", prompt)
            self.assertIn("Do not use a similarly named product folder", prompt)

    def test_manifest_and_all_four_presentation_variants_are_required(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            for value in ("Black", "Oak", "White", "Unframed"):
                self.assertIn(value, prompt)
            self.assertIn("BUILD A COMPLETE INTERNAL IMAGE MANIFEST", prompt)
            self.assertIn("Exact Dropbox path.", prompt)
            self.assertIn("New Shopify media ID after upload.", prompt)
            self.assertIn("Use stable Shopify product, media, and variant IDs/GIDs", prompt)
            self.assertIn("every applicable Black size variant", prompt)
            self.assertIn("every applicable Oak size variant", prompt)
            self.assertIn("every applicable White size variant", prompt)
            self.assertIn("every applicable Unframed size variant", prompt)

    def test_unframed_can_never_receive_framed_media_or_leak_to_framed_variants(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            self.assertIn("Never attach a framed image to Unframed.", prompt)
            self.assertIn(
                "Never attach the Unframed image to Black, Oak, or White.",
                prompt,
            )
            self.assertIn("No framed variant uses the Unframed image.", prompt)
            self.assertIn("No Unframed variant uses a framed image.", prompt)

    def test_existing_product_uploads_and_verifies_before_deleting_old_media(self):
        prompt = self.existing_prompt()
        ordered_steps = [
            "Read and record the existing product media",
            "Resolve and validate every supplied replacement WebP",
            "Upload all new media.",
            "Wait for every new Shopify image to become ready.",
            "Assign the new media to the correct variants",
            "Verify all four presentation assignments through a fresh Shopify read.",
            "Only after every previous check passes, remove the specific old media",
            "Perform one final Shopify read",
        ]
        positions = [prompt.index(step) for step in ordered_steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("Upload first, verify second, and delete old media last.", prompt)
        self.assertIn("Keep the existing working product media.", prompt)
        self.assertIn(
            "Do not delete the existing Black, Oak, White, or Unframed images.",
            prompt,
        )
        self.assertIn("Do not remove unrelated lifestyle images", prompt)

    def test_new_product_cannot_complete_until_final_media_read_back_passes(self):
        prompt = self.new_prompt()
        ordered_steps = [
            "Create or resolve the product using the unchanged existing workflow.",
            "Confirm all intended Shopify variants exist.",
            "Resolve and validate every supplied Dropbox WebP.",
            "Upload every expected WebP.",
            "Wait for every image to become ready in Shopify.",
            "Assign Black, Oak, White, and Unframed images correctly",
            "Verify the gallery, featured image, and all variant assignments",
            "Report completion only after the final read-back passes.",
        ]
        positions = [prompt.index(step) for step in ordered_steps]
        self.assertEqual(positions, sorted(positions))
        self.assertIn(
            "A product with missing media or incorrect variant images is incomplete.",
            prompt,
        )

    def test_retries_are_bounded_idempotent_and_do_not_duplicate_media(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            self.assertIn("Automatically retry temporary Dropbox, network, or Shopify failures", prompt)
            self.assertIn("bounded retries", prompt)
            self.assertIn("MAKE RETRIES IDEMPOTENT", prompt)
            self.assertIn("Track media IDs returned during this operation.", prompt)
            self.assertIn(
                "Do not upload a duplicate merely because a previous attempt stopped during verification.",
                prompt,
            )
            self.assertIn(
                "remove only confirmed duplicates created by this failed operation",
                prompt,
            )
            self.assertIn("Do not identify replacement media by filename alone", prompt)

    def test_missing_or_ambiguous_mapping_fails_without_media_deletion(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            self.assertIn(
                "If a required Black, Oak, White, or Unframed image is missing or ambiguous",
                prompt,
            )
            self.assertIn("preserve all existing media", prompt)
            self.assertIn("report the exact missing or conflicting filenames", prompt)

    def test_special_characters_and_stable_product_identifiers_are_preserved(self):
        prompt = self.existing_prompt()
        self.assertIn(
            "/Sportscave Team Folder/04_OUTPUT/product-images/"
            "O'Connor & São-Paulo - Legends",
            prompt,
        )
        self.assertIn("gid://shopify/Product/987654321", prompt)
        self.assertIn("oconnor-sao-paulo-legends-wall-art", prompt)
        self.assertIn(
            "Preserve spaces, Unicode characters, apostrophes, ampersands, and hyphens",
            prompt,
        )

    def test_unapproved_metadata_and_credentials_never_enter_the_prompt(self):
        metadata = source_context()
        metadata.update(
            {
                "product_name": 'Quoted "Title"\nwith a second line',
                "dropbox_access_token": "dropbox-secret-value",
                "shopify_access_token": "shopify-secret-value",
                "unapproved_internal_note": "private-note-value",
            }
        )
        prompt = app.get_product_upload_prompt(metadata, update_existing=False)
        self.assertIn(r'Quoted \"Title\" with a second line', prompt)
        self.assertNotIn("dropbox-secret-value", prompt)
        self.assertNotIn("shopify-secret-value", prompt)
        self.assertNotIn("private-note-value", prompt)

    def test_outside_dropbox_folder_is_rejected_before_prompt_generation(self):
        metadata = source_context()
        metadata["dropbox_product_folder"] = "/Another Dropbox/Private"
        with self.assertRaisesRegex(ValueError, "outside"):
            app.get_product_upload_prompt(metadata, update_existing=True)

    def test_final_success_requires_fresh_shopify_read_and_completion_table(self):
        for prompt in (self.new_prompt(), self.existing_prompt()):
            self.assertIn("MANDATORY FINAL SHOPIFY READ-BACK", prompt)
            self.assertIn("Do not report success until a fresh Shopify read confirms", prompt)
            self.assertIn("Every expected Dropbox WebP is present on the correct product.", prompt)
            self.assertIn("No unintended duplicate media remains.", prompt)
            self.assertIn("The correct featured image is selected.", prompt)
            self.assertIn(
                "| Dropbox file | Shopify media ID | Status | Image role | Intended variant | Assigned variant IDs | Verified |",
                prompt,
            )
            self.assertIn("Never return a false success", prompt)

    def test_patch_application_is_idempotent_for_saved_prompt_overrides(self):
        legacy_saved_prompt = (
            "CUSTOM SAVED PRODUCT SOP\nKeep this custom content exactly.\n\n"
            "ADDITIONAL REQUIRED SUB-PROMPTS\nKeep this appendix exactly."
        )
        once = app.apply_product_upload_media_reliability_patch(
            legacy_saved_prompt,
            source_context(),
            update_existing=True,
        )
        twice = app.apply_product_upload_media_reliability_patch(
            once,
            source_context(),
            update_existing=True,
        )
        self.assertEqual(twice.count(app.PRODUCT_UPLOAD_MEDIA_PATCH_START), 1)
        self.assertEqual(
            app.remove_product_upload_media_reliability_patch(twice),
            legacy_saved_prompt,
        )

    def test_product_upload_ui_keeps_two_prompt_cards_and_no_drive_workflow(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        page_source = source[
            source.index("def render_product_uploads_page():") :
            source.index("\n\ndef test_google_drive_connection")
        ]
        self.assertEqual(page_source.count("render_copyable_prompt("), 2)
        self.assertIn("selecting the exact Dropbox product folder", page_source)
        self.assertIn("connected Dropbox and Shopify integrations", page_source)
        self.assertNotIn("shopify-uploads", page_source)
        self.assertNotIn("Google Drive", page_source)
        self.assertNotIn("st.file_uploader", page_source)
        self.assertNotIn("_render_mockup_folder_picker", page_source)


if __name__ == "__main__":
    unittest.main()
