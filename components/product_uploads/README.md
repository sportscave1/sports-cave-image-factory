# Product Uploads implementation and local evidence

The owner authorised publication on 17 October 2026. This report preserves the
original local implementation evidence below. The integration with the newer
technical worker and release verification are described in
`docs/releases/ALL_LATEST_UPDATES_20261017.md`.

The automatic route is implemented behind `PRODUCT_UPLOAD_AUTOMATIC_ENABLED=false`.
It uses real application services and a new private intake table. Manual prompts,
mapping, reset and retry remain available. This is a local implementation, not a
verified production end-to-end release: Photoshop admission is blocked by the
running Companion, and remote writes were deliberately not exercised.

## User flow

1. Choose Upload to Draft, Upload to Live or Update Existing.
2. Upload the PSD. The backend verifies its structure, final size, Dropbox content
   hash, stable file ID and revision before enabling Copy Prompt.
3. Find Mockups opens the existing Files route at the verified product-images folder.
4. Copy Prompt and give ChatGPT the website images. The prompt remains sourced from
   the existing Dev Mode prompt IDs and commercial rules.
5. After ChatGPT finishes, paste the resulting exact title or Shopify URL and Upload.
6. Exact lookup includes drafts. Duplicate titles require a choice. The existing
   Shopify registration, mapping and Companion queue services handle the product.
7. Status updates until Cloud Ready or Failed. The preview becomes available after
   linking and successful native preparation. Manual workflow requires no PSD.

## Integration and recovery

- The same-origin routes reuse signed account cookies, session revocation and page
  permissions. Automatic uploads also require the existing first-PSD attachment
  capability and Files access. Prompt-only accounts retain manual prompt access.
- A durable account-owned UUID record connects mode, file size, Dropbox content
  hash, chunk digests, transfer session/offset, source ID/revision, copy state,
  lookup choices, product GID and exact preparation hash. RLS denies browser roles.
- Transfers use sequential 4 MiB binary chunks, up to 1 GiB. Incremental framing
  checks PSD signature/version, sections, RGB8, dimensions and compression. Native
  editable-layer/font/numbering checks remain separate. PSB, RGB16, CMYK and canvases
  above the current 95 MP worker budget fail with an explanation.
- No base64 or full-PSD request-body allocation. Chunk digests and deterministic
  storage destinations recover interrupted transfers and lost acknowledgements.
  Refresh retrieves the server record; reselecting the same file resumes its offset.
  Interrupted sessions expire after six days; the UI directs the user to start anew.
- Originals remain unchanged in the approved PSD storage directory. Preparation uses
  the existing Companion's versioned staging copy and native workflow. No new
  Photoshop runner, competing process or installed Companion update was introduced.
- Lookup uses NFC/whitespace/case normalisation and exact post-search matching.
  It paginates existing Shopify queries, includes drafts, accepts trusted store URLs,
  escapes search syntax, and never uses the first fuzzy result. The field does not
  inherit the title generator's 60-character limit and does not rename products.
- Linking never creates a Shopify product. Registration uses the existing locked
  upsert, including a narrowly scoped draft option. Repeated requests use the same
  product, mapping and queue checkpoint. A previously committed mapping is reused
  after a failed handoff. A different mapped PSD requires existing Reset / Replace.
- The Edition Ops snapshot uses a small durable intake registration marker to invoke
  its existing invalidation on navigation/rerun. The status bridge also gets a refresh
  event. No page reload is required to see a newly registered product.
- A `product-upload-technical-v1` marker is restricted to the exact linked intake,
  source, edition total and verified preparation. It does not fabricate a visual
  approval. Existing package verification recomputes source/pixel proofs and checks
  every asset's hash and profile before durable receipts are accepted.
- The marker allows technical Cloud Ready / TEST READY only. Automatic supplier
  certification and visual-review workers exclude it; existing jobs retain their
  behaviour. Orders, allocations, certificates and supplier fulfilment are untouched.
- Previews reuse the existing colour-managed thumbnail worker/cache. Cache identity
  includes the exact preparation. A changed mapping, source revision or edition total
  invalidates readiness and preview access. Status calls read small database evidence,
  never full PSDs. Polling is every five seconds while visible and active, and stops
  on Uploaded, Failed or Cloud Ready. Preview retries are bounded.

## Template and colour findings

Read-only Dropbox metadata verified both the path and stable identity:

`/Sportscave Team Folder/04_OUTPUT/product-images`

`id:u1tYiAa2O-AAAAAAAAACKg`

Local asset inspection found:

| Asset | Dimensions | Profile and purpose |
| --- | --- | --- |
| sportscave-new-designs-template.psd | 7016 × 4961 | Tagged sRGB IEC61966-2.1; design template |
| mockup-product-page-template.psd | 1500 × 1000 | Untagged; website mockup template, not the numbered production PSD |
| mockup-socials-template.psd | 1024 × 1024 | Untagged; social mockup template |
| SC_Auto_Editions_Base_Template_V1.psd | 11812 × 8350 | Untagged RGB8; archived native layer-role reference |

The Auto Editions base file's SHA-256 matches the archived Photoshop inspection in
`data/auto_editions_template.json`: 300 dpi landscape, editable top-level `001 / 100`,
Cinzel-Medium, 14.412 pt, tracking 400, centred. Archived number bounds are
[1988, 7446, 2781, 7597]; plaque bounds are [883, 7004, 3287, 7787]. The plaque is an
embedded smart object. Matting includes embedded objects and archived inspection
warnings for nested objects. The current worker takes geometry from each source,
not from these template coordinates. Current glyph widths across the full range,
linked-object availability and font availability still need native verification.

A separate local `output/product-uploads/templates/SC_Auto_Editions_Base_Template_V2_sRGB_LOCAL.psd`
has sRGB IEC61966-2.1 assigned using the existing binary profile staging implementation.
The complete layer/pixel tail is byte-identical to the original. This is profile
assignment, not colour conversion or an assertion of historical provenance. The
original/shared template and active template manifest were not changed.

The V2 copy is **not adopted as a working production template**: its 98,630,200 pixels
exceed the existing 95,000,000-pixel worker limit, and Photoshop reopen/export was
not admitted. No unapproved resize, flattening, invented number or badge replacement
was used to make it pass. Its hash and exact blocker are in `template-audit.json`.

The existing approved colour policy remains authoritative: correctly tagged files
are preserved; untagged RGB8 assignment needs exact approved policy membership.
Filename, dimensions and folder location do not establish that membership. Existing
policy does not authorise PSD colour conversion (`pixels_converted` must remain
false); an unapproved conversion is rejected. The preview pipeline can convert
tagged image pixels to sRGB for display. Native profile conversion remains unverified
and is not represented as implemented policy support.

## Local verification

Evidence is under `output/product-uploads/` (ignored local artifacts).

- `regression-results.txt`: 375 passed, 35 skipped, 36 subtests. Covers retained
  prompts/modes/collections, Shopify sync, onboarding, colour policy, quality,
  package validation, status and cancellation. Skips are not counted as validation.
- `final-integration-tests.txt`: 195 passed, one skipped, two subtests after the final
  backend changes. Includes intake recovery, permissions with actual signed cookies,
  private-table access, exact/duplicate/draft/URL/long-title lookup, concurrent clicks,
  canonical registration, mapping conflicts, committed-mapping recovery, queue leases,
  source invalidation, real binary package import and existing Files/status/visual
  regressions. The skipped test requires the native PostgreSQL performance fixture.
- SQL was executed by disposable PGlite, not mocked SQL. It is not evidence of native
  PostgreSQL MVCC performance or real remote provider behaviour. Shopify/Dropbox
  boundaries and native Photoshop output were simulated with synthetic identities.
- The binary package endpoint test actually unpacks the archive, verifies every asset
  hash/profile, recomputes pixel/source proofs, records disk-backed upload receipts,
  saves the preparation and completes the existing queue. Photoshop produced none of
  those test images; they are explicitly synthetic fixtures.
- `browser-qa.log` and `browser-metrics.json`: real Chromium exercised the actual page
  and HTTP services, successful/denied clipboard access and a working fallback,
  interrupted chunk transfer/resume, navigation/back/refresh, manual actions, mode
  invalidation, not-found recovery, duplicate submission, offline waiting, cached
  preview reuse and terminal polling. The real app iframe bridge and its late-load
  measurement handshake were exercised.
- Desktop 1280 × 850 and narrow 390 × 844 were checked. DPR 1.5 and CSS zoom 125%
  simulate scaling; the user's physical Windows settings were not changed. No
  horizontal overflow, field/button overlap or JavaScript errors were observed.
  The complete Streamlit login/navigation shell was not run against production.
- Python compilation, JavaScript syntax, migration safety check and Render topology
  validation passed. The migration was applied only to the disposable SQL fixture.

Native admission was checked through the existing maintenance preflight. Running
Companion and Photoshop processes prevented admission. They were not interrupted.
The pending independent PSD repair was excluded. No current native preparation,
template reopen, actual Shopify linking or remote Dropbox upload was performed.

## Measured performance

These are the last recorded loopback measurements from `browser-metrics.json`,
including browser hashing and backend final verification. The server was warmed.
They are not Dropbox WAN timings or a claimed improvement over an older version.

| Measurement | Result |
| --- | --- |
| Synthetic large-transfer fixture | 179,695,966 bytes; 1.837 s |
| Server RSS baseline / sampled peak | 72.55 / 77.51 MiB |
| Server RSS increase | 4.96 MiB |
| Sampled browser-process RSS baseline / peak | 288.09 / 327.66 MiB |
| Real local sRGB design-template transfer | 16,206,695 bytes; 0.207 s |
| Binary request maximum | 4 MiB |
| Waiting status | 2 responses in 11.51 s, 529 bytes each |
| Cached synthetic preview | 200 × 100 JPEG, 1,104 bytes |
| Preview inputs fetched | master and first numbered patch once; no refetch on refresh |
| Terminal status polling | zero requests over the observed subsequent 11 s |
| Completed iframe content height | 687 px |

The stress fixture tests transfer behaviour, not native PSD validity. The real
16 MB template underwent header/structure/storage identity checks, not Photoshop
preparation. The preview is synthetic and is not representative of full-size native
preview generation cost. RSS was sampled every 150 ms; short peaks can be missed.

## Reproduce safely

Run from this isolated worktree. No production credentials are needed. The harness
clears inherited secrets, disables dotenv loading, blocks external HTTP, substitutes
provider boundaries and binds only to loopback. Its database is disposable and
does not survive a harness process restart; production intake durability belongs
to PostgreSQL and Dropbox. Test restart recovery reuses durable records within the
disposable database, plus browser navigation and service reconstruction.

```powershell
$env:AUTO_EDITIONS_TEST_PGLITE='C:\Dev\SportsCaveWorktrees\.studio\release-evidence\ov20\pgtest\node_modules\@electric-sql\pglite\dist\index.js'
& 'C:\Users\hello\Documents\sports-cave-image-factory\.venv\Scripts\python.exe' scripts/product_upload_local_preview.py --port 8676
```

Open `http://127.0.0.1:8676/product-uploads`. For a fresh manual test, first restart
the disposable harness or run `Invoke-RestMethod http://127.0.0.1:8676/__test/reset -Method Post`
and refresh the page. Choose a mode, upload `output/product-uploads/sportscave-new-designs-template-local.psd`,
Copy Prompt, and enter **New Art**. It links to a synthetic Shopify product and shows
Waiting for Companion. The harness's Files boundary page tests navigation without
connecting the production Files account. Native completion is simulated only by
the harness's test endpoint; it is not an installed Companion operation.

In another terminal, run the repeatable browser exercise (it resets only the
disposable harness fixtures):

```powershell
& 'C:\Users\hello\Documents\sports-cave-image-factory\.venv\Scripts\python.exe' scripts/verify_product_upload_browser.py
```

The real server integration requires the reviewed intake migration and the feature
flag. Do not enable it against production as part of local testing. Optional
`SHOPIFY_PUBLIC_DOMAIN` permits that exact storefront hostname for handle URLs;
connected Shopify admin URLs work without it.

## Workspace and files changed

Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-integrations-product-upload-psd-intake-20261017-product-upload-psd-intake-20261017`

Branch: `codex/task/integrations-product-upload-psd-intake-20261017-product-upload-psd-intake-20261017`

Base: `c8e6688f6b9e25e8aea12d674143b336cd9ddd6f`. Developer Studio initially chose an older clean base; the fresh
isolated branch was advanced to this existing integration base before edits. No
new commit was created. The original repository and other active worktrees were
not edited by this task. Colour-policy and automatic-processing work were inspected;
the independent pending PSD repair remains excluded.

Files changed in this worktree:

- `.env.example`
- `app.py`
- `auto_editions.py`
- `auto_editions_quality_store.py`
- `auto_editions_setup_api.py`
- `auto_editions_status.py`
- `auto_editions_visual_store.py`
- `components/product_uploads/README.md`
- `components/product_uploads/app.js`
- `components/product_uploads/index.html`
- `edition_ops.py`
- `files_upload_api.py`
- `migrations/20261017010350_product_upload_intakes.sql`
- `product_upload_api.py`
- `product_upload_intake.py`
- `product_upload_prompt_core.py`
- `product_upload_prompts.py`
- `product_upload_readiness.py`
- `product_upload_services.py`
- `run_migrations.py`
- `scripts/inspect_product_upload_templates.py`
- `scripts/product_upload_local_preview.py`
- `scripts/verify_product_upload_browser.py`
- `sports_cave_server.py`
- `supabase/migrations/20261017010350_product_upload_intakes.sql`
- `supabase_backend.py`
- `tests/auto_editions_postgres_server.mjs`
- `tests/test_product_upload_handoff.py`
- `tests/test_product_upload_intake.py`
- `tests/test_product_upload_modes.py`
- `tests/test_product_upload_prompts.py`

The prompt core was moved out of Streamlit startup so both the iframe API and Dev
Mode use the same source. Existing content tests passed. Local PSD copies, audit
logs, measurements and screenshots remain in the ignored output directory.

## Remaining verification

Exclusive native Photoshop validation of representative uploaded PSDs and the local
V2 template remains blocked. The oversized Auto Editions template also needs a
separately verified worker-budget or source-template decision. No native full-range
number/font/export verification or authorised PSD profile conversion was claimed.
Remote storage upload/resume, a real Shopify return/link and full installed-Companion
execution remain unverified under the local-only restriction. There is no claim of
end-to-end production readiness.

Status: Implemented locally. Not committed, pushed or deployed.
