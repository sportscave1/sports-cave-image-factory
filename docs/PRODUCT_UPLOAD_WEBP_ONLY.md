# Product Uploads WEBP-only saves

Owner-authorized implementation and release, 19 October 2026.
Task `20261019-a785b044`, owner `codex-01a1533c-webp-only-20261019`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-products-product-uploads-webp-only-final-saves-20261019-a785b044`.
Branch: `codex/task/products-product-uploads-webp-only-final-saves-20261019-a785b044`.
Baseline: `8e4d406caa65753ced9d0afc8ca9f008da0345fe`.
The new clean task worktree was advanced from Studio's older approved base before
editing. The original repository and other worktrees were preserved.

## Pipeline trace and scope

`product_upload_jobs.generate` calls `image_factory.generate_product_images`.
The framed/unframed/size-guide generators share `save_review_and_assets`, which
previously encoded PNG reviews, WEBP masters and JPEG masters. Product Uploads now
passes `export_jpg=False`; no JPG cache directory or final JPEG is created. Its
generation completion check requires the existing reviews, previews and WEBPs.

Lifestyle imports pass through `app.save_uploaded_lifestyle_result` into the
atomic staged `image_factory.save_lifestyle_mockup` encoder. Only results carrying
the Product Uploads intake identity disable final JPEG encoding. The original
lossless WEBP validation, resizing, previews, colour handling and atomic rollback
remain in place. JPEG source/template decoding and retained uploaded input files
remain available to their existing processing/copy tools; they are not new final
product exports.

`app._mockup_dropbox_manifest` now excludes JPG paths for Product Uploads, including
cached older runs with both formats. `product_upload_export.transfer` independently
accepts only the final WEBP entries under `WEBP/`, so old cached manifests cannot
upload new JPG copies. The source PSD flow is separate and unchanged. No historical
Dropbox files or folders are deleted.

Save All fingerprinting, retries, progress totals and exact receipts already use
the actual export manifest. They now count only its WEBPs; no fixed count is added.
`current_source` and the complete upload prompt use this authoritative receipt and
the existing role/order manifest. Missing JPGs cannot block completion. The
existing required WEBP validation still applies. Prompt templates and UI layout
are unchanged.

Shared generation and manifest functions retain their original JPEG-enabled
defaults for standalone Mockups, social exports and other callers. The change
does not alter Sync & Map, its preparation holds, Shopify publication or workers.
No database migration or infrastructure configuration change is required.

## Local checks

- Real generated core images and lifestyle imports were compared with the previous
  encoder path: WEBP/review/preview bytes, filenames, dimensions and order match.
  A save interceptor rejects any JPEG encoding in the WEBP-only path.
- Standalone defaults still create valid JPGs; Product Uploads creates no JPG cache
  directory. The application lifestyle wrapper selects the correct mode.
- Background generation completes without JPG files and fails without a WEBP.
- Actual isolated save services and SQL verify WEBP-only progress/receipts, partial
  failures, lost upload acknowledgements, retry and duplicate-save recovery,
  numbered folders, current manifests and stale-save fencing. A mixed older
  manifest also transfers only WEBPs.
- The Streamlit entrypoint suite passes in its isolated process. Running it after
  other Streamlit suites in one process reproduces the existing form-context leak;
  that combined run is not represented as green.
- Existing standalone artwork-memory and second-upload tests, the complete-prompt
  clipboard contract, topology validation and Studio static/secret checks pass.

No production PSD upload, Dropbox asset save, Shopify write or Companion operation
is performed for verification. Release deploy IDs and read-only health/heartbeat
results are retained in the task's ignored `output/product-upload-webp-only` evidence
and Studio release status.
