# Local Dropbox PSD linking — validated snapshot

Studio task: 20261012-5849050d; owner: codex-psd-01a12ffa.
Branch: codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
Status: Tested locally, uncommitted; production untouched.

## Actual matching results

Validated the user-supplied Sports_Cave_Codex_PSD_Snapshot_2026-10-12.zip offline.
Only the three requested CSVs and manifest integrity metadata were read; attached
prose was not treated as instructions. All three CSV hashes match the manifest.

- Edition Ops products: 333
- Approved PSDs mapped: 282, with 282 unique stable Dropbox file IDs
- Products without an approved PSD: 51, displayed as Not linked
- Review-folder PSDs excluded: 40
- Ambiguous matches: 0

The export uses spaced hyphens for forbidden filename punctuation. Matching supports
that deterministic sanitisation and the existing integration's underscore convention,
with collision checks across both. Exported product titles, handles, GIDs, filenames,
file IDs and namespace paths were independently cross-checked across the two CSVs.
No fuzzy matching or guessed product identity is used.

Raw exports, actual unmatched-product list and generated mapping are ignored:

- output/psd_snapshot/edition_ops_products_333.csv
- output/psd_snapshot/approved_dropbox_psds_282.csv
- output/psd_snapshot/excluded_review_psds_40.csv
- output/psd_snapshot/unmatched_products_51.json
- output/psd_snapshot/validation_results.json
- output/psd_directory.json

## Implementation

Edition Ops and Orders use the same persistent cached product mapping. Orders
resolves each line's product ID; multi-artwork orders have separate PSD links.
Edition Ops removes the two Shopify link columns, displays Status and adds File.
Save & Sync Shopify and internal sync states are preserved. Live requires published
online-store evidence and healthy sync; explicit unpublished states display Offline;
failures display Sync Issue. Unknown and pending remain distinct.

The CSV export has no Dropbox preview URLs. Open PSD therefore goes to the
same-origin /api/files-psd-open endpoint. This explicitly checks existing login and
Files permission before reading any Dropbox context. On click, the integration
resolves the immutable file ID, checks the current approved-folder location and
redirects only to Dropbox's API-returned preview URL. No share link is created, and
no temporary content/download URL is exposed. Dropbox then applies its own account
permissions. ID lookup handles filename changes. Removed/review-folder files fail
closed; missing preview URLs return a controlled unavailable response.

There is no network request or polling during table projection. Existing integration
and authentication are reused. Local JSON persistence is atomic and cached. Verified
assignments are preserved; conflicting imports fail without overwriting them.

## Changed files

- psd_directory.py — shared matching, mapping cache, display states and local import
- edition_ops.py — compact requested columns; sync/edit workflow preserved
- orders_page.py — per-line product PSD links in the existing column position
- dropbox_integration.py — preview metadata and read-only stable-ID resolver
- files_upload_api.py — authenticated PSD redirect route
- scripts/validate_psd_snapshot.py — offline integrity/identity validation and import
- tests/test_psd_directory.py — matching, snapshot, exclusions, cache, performance
- tests/test_psd_open.py — authentication, redirects, renames, missing/review files
- tests/test_psd_links_ui.cjs — missing-link click guard and unrelated navigation
- tests/test_edition_ops_table_editing.py — requested column regression expectations
- docs/LOCAL_PSD_LINKING.md — this report

## Verification and performance

126 focused Python tests passed using the existing virtual environment:

```
python -B -m unittest tests.test_psd_directory tests.test_psd_open tests.test_edition_ops_stability tests.test_edition_ops_table_editing tests.test_orders_compact tests.test_dropbox_integration tests.test_files_upload_api
```

`node tests/test_psd_links_ui.cjs` passed. Studio static checks, secret-pattern checks,
and git diff whitespace checks passed. Security tests explicitly verify denial before
cloud access, rejection of wrong file IDs, review-folder moves and unsafe URLs.
Tests use fake credentials and mocked cloud operations only.

Actual snapshot benchmark, 20 runs:

- Full matching/cross-validation plus 333 link projections: median 14.138 ms
- Cached Edition Ops projection, 333 rows: median 4.911 ms; max 5.908 ms
- Cached Orders projection, 333 lines: median 1.367 ms; max 1.444 ms
- Network requests during these operations: 0

Both actual table projections independently show 282 Open PSD cells and 51 Not linked
cells. These are local processing measurements, not complete production page timings.

## Remaining limitations

Live Dropbox click-through is intentionally untested: the snapshot lacks preview
URLs and no production credentials or live APIs were accessed. Resolver behavior is
covered by mocked contract/security tests. A future authorized environment must have
Dropbox metadata/sharing-read scope and provide a permission-protected preview URL.

Browser viewport testing remains unavailable because Playwright is not installed.
Streamlit AppTest covers save/reload/navigation; Studio Phase 1 application previews
remain disabled. Mapping persistence is local to this retained task worktree; no
production storage or database migration is included.

No commits, pushes, merges, deployments, live Shopify/Dropbox modifications or
production database changes were performed. Exported files are not tracked.
