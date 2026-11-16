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
   binds to that exact PSD and Shopify product. Track artwork review_status separately from
   cleanup_status. Use cleanup_status pending until final promotion and cleanup are verified,
   then set it to complete. Pending cleanup alone does not change an otherwise verified artwork
   from ready_for_review to needs_attention. If a staged handoff was marked needs_attention
   solely for pending cleanup, confirm the artwork and PSD checks and update the exact JSON
   revision to ready_for_review before resuming. If any required artwork, PSD or new handoff
   check is unresolved, retain the previous refresh and its JSON and report the pending checks.
2. List Review and Review/JSON, including all result pages. Identify superseded refreshes by
   matching handoffs with upload_intent existing_product_refresh, the exact Shopify product
   ID, and the PSD's exact Dropbox ID, path and revision. Treat the numeric Shopify ID and
   its Product GID as the same ID. Check matching legacy sidecars in Review if present.
   For legacy refresh files with missing or stale JSON, verify the match using the exact
   original Live PSD stem, the verified Shopify product identity and visual inspection of the
   PSD. When these confirm the same product, recoverably delete its superseded Review PSDs and
   obsolete matching JSON files after the replacement PSD and JSON are saved and verified.
   Missing or stale JSON alone must not block replacement. Confirm an obsolete JSON belongs to
   an identified superseded refresh before removing it. A JSON that points to another active
   PSD must be assessed against that PSD separately. Leave genuinely ambiguous files untouched.
   If an ambiguous file occupies a final path, keep the ready staged pair and report the conflict
   before removing any superseded files.
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
   JSON remain for this product. Update cleanup_status to complete and verify that JSON revision.
   If cleanup or promotion fails partway, re-read the recorded
   IDs before any retry. Retain the verified replacement and report the exact saved paths and
   remaining operations. Claim completion only after both final files and cleanup are verified.
"""
