# Product Uploads: exact saved Dropbox WEBP prompt

Implemented and tested locally on 19 October 2026. The user subsequently
authorized Git publication and deployment to the existing Render service.
Live Shopify product operations remain outside this release.

## Verified task identity

- Task: 20261019-d841bc56, PRODUCTS.
- Owner: codex-01a1533c-dropbox-manifest-20261019.
- Worktree: C:/Dev/SportsCaveWorktrees/sports-cave-products-product-uploads-exact-dropbox-webp-manifes-20261019-d841bc56.
- Branch: codex/task/products-product-uploads-exact-dropbox-webp-manifes-20261019-d841bc56.
- Starting code: a5b3afc0dc3b91307bc674134c7138c42e79fc4c, identified by the local
  released-task record. Studio initially allocated its older approved base; only
  this newly allocated clean branch was fast-forwarded to the released code.
  Other task worktrees, category branches and unfinished changes were not edited.
- Release preparation preserves the newer Files-page commits already on main.
  The exact published commit and Render deployment are recorded in Studio and
  local release evidence after publication.

## Behavior

Save All retains the authoritative complete receipt and a lightweight ordered WEBP
manifest. The WEBP directory is taken from the confirmed files' Dropbox metadata,
including numbered destinations. One exact folder metadata lookup during saving
captures the WEBP folder ID when available; the product folder ID is not substituted.
The manifest includes the actual count, filenames, roles/order, available file IDs,
revision/hash/size and existing role/variant metadata.

Save-operation tokens and fingerprints guard checkpoints and final binding.
Image edits, product-detail changes, generation and a new save invalidate the
previous handoff. Late completions cannot overwrite the current destination.
The copy endpoint requires the displayed source version and rechecks it after
loading the editable template. No destination is inferred from a product title or
searched by recency.

The complete prompt is generated when copying, from the saved metadata and the
existing Developer Studio template. Draft, Live and Update rules, commercial copy,
pricing, collections, variant mapping and operation correlation remain in place.
The Dropbox source section instructs ChatGPT to retrieve original WEBP files,
verify the manifest and report retrieval/transfer blockers before Shopify writes.
The shared template is not written or given product-specific paths.

The bottom saved-WEBP gallery and per-file controls were removed. The replacement
button copies directly to the clipboard and shows Copied for two seconds after a
successful write. Before a current complete save, it is disabled with Save All
first guidance. Timer cleanup and errors are handled without a modal or text box.
Save All's inline status, upper previews, generation and lifestyle tools remain.
Copying performs no image download, ZIP creation, sharing-link creation, helper
invocation or Shopify operation.

## Files changed

Runtime:

- components/product_uploads/app.js — direct clipboard action, source-version gate,
  errors, feedback and lifecycle cleanup.
- components/product_uploads/index.html — one complete-prompt button and guidance;
  removed bottom gallery and its styles/messages.
- components/product_uploads/package.js — removed obsolete gallery/download client.
- product_upload_source.py — new receipt-derived source validation and prompt section.
- product_upload_export.py — captures exact WEBP folder metadata at save completion.
- product_upload_mockups.py — save-operation fencing and authoritative receipt binding.
- product_upload_intake.py — exposes validated source version and checks copy acknowledgement.
- product_upload_api.py — builds the complete prompt from current metadata and rechecks
  it after template loading; removes unused gallery-script route.
- product_upload_prompts.py — runtime Dropbox-source adapter; keeps editable templates.
- product_upload_outputs_ui.py — invalidation, save-operation capture and stale-result guard.
- product_upload_mockups_ui.py — mounts disabled/enabled handoff and invalidates edits.
- product_upload_jobs.py — invalidates saved source when regenerating images.

Verification and documentation:

- tests/test_product_upload_source.py — new manifest, mode, stale-source and save-race tests.
- tests/test_product_upload_complete_prompt.cjs — new clipboard/feedback/gating/lifecycle tests.
- tests/test_product_upload_package.py — complete receipt fixtures and prompt API assertions;
  isolates the real Streamlit status check from legacy app import side effects.
- tests/fixtures/product_upload_outputs_provider.py — realistic synthetic folder/file metadata.
- tests/test_product_upload_state.cjs — asserts unsaved/manual copy is gated.
- tests/test_product_upload_package.cjs — removed obsolete per-file gallery tests.
- scripts/verify_product_upload_complete_prompt.py — synthetic loopback Chrome/Edge checks.
- components/product_uploads/README.md — current prompt handoff documentation.
- docs/PRODUCT_UPLOAD_DROPBOX_PROMPT.md — this report.

## Checks completed

- 84 tests passed across test_product_upload_package.py, test_product_upload_source.py,
  test_product_upload_outputs.py, test_product_upload_mockups.py,
  test_product_upload_modes.py, test_product_upload_gallery.py and
  test_product_upload_jobs.py. PostgreSQL cases used disposable local PGlite;
  providers were synthetic and environment credentials were excluded.
- Four additional prompt-adapter checks passed after preserving legacy input-text
  formatting, including the existing saved-commercial-copy regression.
- Five Node suites passed: complete_prompt, state, copy_feedback, mapping and focus.
  They cover both clipboard APIs, all modes, errors, exactly 2000 ms feedback,
  repeated clicks, stale responses, new products, unmount cleanup, upper lifestyle
  copy tools and preview focus behavior.
- Installed Chrome and Edge passed synthetic real-clipboard checks for all three
  modes, feedback reset, blocked clipboard, save gating, and desktop/mobile layout.
  No image/helper requests, downloads or browser errors were observed.
- Syntax checks and git diff --check passed.

Evidence is in output/product-upload-dropbox-prompt/: focused-tests.txt,
browser-checks.json and browser screenshots. The generated evidence is local and
ignored by Git.

The initial combined Python run exposed an existing Streamlit global-state test
interaction; the same status test passed alone. It now runs in an isolated
subprocess, and the combined suite passes.

## Verification boundary

Prompt generation, receipt handling and clipboard behavior were verified locally.
The live Dropbox-to-ChatGPT-to-Shopify retrieval/transfer chain was not exercised.
No claim is made that an external connector can complete that transfer or that a
Shopify product was uploaded. No production credentials or live customer data were
used in the verification fixtures.
