"""Shared closeout instructions for verified Shopify refresh artwork."""

from psd_directory import REVIEW_FOLDER, REVIEW_METADATA_FOLDER


REVIEW_REPLACEMENT_RULE = f"""**REVIEW REPLACEMENT RULE**

Keep one current refresh PSD per verified Shopify product directly in {REVIEW_FOLDER}/,
with one matching upload.json in {REVIEW_METADATA_FOLDER}/. Use the exact verified original
Live PSD stem for the final filenames. This run authorises recoverable deletion and renaming
within Review only for this product. Keep the original Live PSD, unrelated files, Shopify
listing and live PSD mapping untouched.

1. Reopen the replacement saved under its unique staging filename and verify its contents
   and Dropbox file ID, revision and path. Save a matching staging .upload.json under
   {REVIEW_METADATA_FOLDER}/ in create-only mode. Read back both files and verify the JSON
   binds to that exact PSD and Shopify product. If the replacement needs_attention or any
   required check is pending, retain the previous refresh and its JSON. Keep the staged work
   and report replacement and cleanup as pending. Apply this rule before deleting or renaming.
2. List Review and Review/JSON, including all result pages. Identify superseded refreshes by
   matching handoffs with upload_intent existing_product_refresh, the exact Shopify product
   ID, and the PSD's exact Dropbox ID, path and revision. Treat the numeric Shopify ID and
   its Product GID as the same ID. Check matching legacy sidecars in Review if present.
   Filename, title and athlete alone never establish a match. If an unverified file occupies
   either final path, leave it alone and report the conflict before deleting anything.
3. Once the staged pair is verified and ready_for_review, recheck the two staged receipts and
   the identified superseded PSD and JSON receipts for changes. Recoverably delete only
   those superseded refresh PSDs and their verified matching JSON files. Use revision-aware
   deletion where available. Otherwise recheck the recorded ID, path and revision immediately
   before deleting by ID. Leave uncertain, unrelated or concurrent files in place and report
   any unresolved cleanup. Never delete a staged replacement or another run's drafts.
4. Rename the staged PSD to [Original PSD stem] - REFRESH.psd and its JSON to
   [Original PSD stem] - REFRESH.upload.json in their respective folders, without overwriting.
   Re-read the moved PSD by file ID and confirm its final path, actual revision and contents.
   Update the moved JSON against its current revision with the final PSD's actual Dropbox ID,
   revision and path. Reopen the PSD and re-read the JSON to verify the exact match, then list
   Review and Review/JSON again and confirm only one current refresh PSD and one matching
   JSON remain for this product. If cleanup or promotion fails partway, re-read the recorded
   IDs before any retry. Retain the verified replacement and report the exact saved paths and
   remaining operations. Claim completion only after both final files and cleanup are verified.
"""
