# Product Uploads: retrieve Dropbox originals first

19 October 2026. Task 20261019-901146ce; owner
codex-dropbox-first-20261019-01. Based on the released main revision
f5d925e84affe788d965f3b8c256e369acf8b098, fast-forwarded only in the newly
allocated task worktree. Existing main updates are preserved.

The exported complete prompt begins with the requested START HERE block,
immediately followed by the current successful save's full exact WEBP manifest.
The manifest has moved from the media section and appears once. Correlation,
design context and all remaining Shopify instructions follow in their existing
order. The adapter checks its opening before inserting correlation/context.
Save validation, stale-source/mode checks and text-only copy behavior remain.

Verification uses synthetic receipts and loopback services. Chrome and Edge
actual clipboard text passed for Draft, Live and Update. The entire exported
text equals the generated prompt plus correlation/context (normalising Windows
CRLF), with the exact opening and one manifest. Edge uses a different current
folder and file IDs and contains no earlier product folder. No image/helper
requests, downloads or browser errors occurred; the Dropbox provider rejects
any call. Incomplete/invalidated saves leave Copy disabled.

A comparison against the previous adapter also verified that removing the moved
manifest from the old prompt yields exactly the new prompt after its opening,
for all three modes, including saved custom commercial content. This preserves
the complete Shopify body, pricing, variants, publication, retries and MAP copy.

Commands: pytest tests/test_product_upload_source.py
tests/test_product_upload_package.py tests/test_product_upload_modes.py;
node tests/test_product_upload_complete_prompt.cjs;
python scripts/verify_product_upload_complete_prompt.py;
python scripts/validate_render_topology.py. Clipboard exports and browser results
are retained locally under output/product-upload-dropbox-prompt/ (ignored).

Prompt/clipboard verification does not verify the end-to-end Dropbox original
retrieval or Shopify transfer. No live Dropbox files were retrieved and no
Shopify or Edition Ops writes were performed for these checks.

The user authorised Git publication and Render deployment for this release.
Deploy only through the existing canonical sports-cave-os service; render.yaml
is unchanged and no Blueprint sync or infrastructure creation is required.
