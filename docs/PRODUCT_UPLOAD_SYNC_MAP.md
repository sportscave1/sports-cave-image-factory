# Product Uploads Sync & Map — local review

Implemented and verified locally on 19 October 2026. At that milestone no commit,
push, deployment, production PSD movement, Shopify write or production Edition Ops
write had been made. The subsequent owner-authorized release is recorded below.

Task: `20261019-47b0769f`; owner: `codex-01a1533c-sync-map-20261019`.

Worktree: `C:\Dev\SportsCaveWorktrees\sports-cave-products-product-uploads-sync-and-map-mapping-only--20261019-47b0769f`

Branch: `codex/task/products-product-uploads-sync-and-map-mapping-only--20261019-47b0769f`

Baseline: `8ee2aa687d04f5bb276a926b0d9e58b7ad1d2e4c`. Studio initially allocated
the older approved base. Only this new, clean task branch was advanced to the
current main baseline, before editing. Other worktrees and the original
`C:\Users\hello\Documents\sports-cave-image-factory` checkout were preserved.

## Behavior and existing services

The existing MAP control is now **Sync & Map**. Its small native dialog shows
Finding Shopify product, Syncing Edition Ops, Checking edition setup, Moving PSD,
Saving mapping and Verifying. It does not notify Streamlit or replace the upload
page. Closing it leaves backend work running; reopening reads durable progress.
Explicitly opening Sync & Map also retains its ID in the existing authenticated
upload-resume URL. A browser refresh can reopen that exact saved operation;
starting another upload clears the recovery URL. This stores no image bytes and
does not discover a latest product or automatically start mapping on page load.

The implementation reuses:

- `product_upload_identity.operation/tag`, exact Shopify tag pagination and
  `fetch_product_by_shopify_id`. Both saved ID and exact tag must agree. There is
  no title selector, newest-product fallback or product creation/publishing call.
- Existing `register_edition` adapter and the canonical catalogue refresh plan,
  display upsert and edition initializer in `supabase_backend`. This refreshes
  one exact product using the same machinery as Pull New Products, without its
  broader catalogue scan or Shopify metafield mirror. Existing counters and runs
  remain intact; missing initial edition limit is collected in the popup.
- `Intakes` ownership/row locks and `product_upload_jobs.JOBS` for background
  execution. Stages, receipts, lease and errors are durable in the existing intake.
  A side effect must recheck its lease, mode and saved WEBP version under the
  intake lock. Interrupted process leases expire after five minutes; Retry resumes.
- `product_upload_dropbox.verify_roots`, its configured Review/live roots,
  `product_upload_lifecycle.filename`, and `Dropbox.api.move_path` (no autorename
  or overwrite). Original ID/revision/hash/size come from the initial selection.
- `PostgresMappings.attach`, its uniqueness/permission/audit rules and fresh
  exact-record read-back. Edition Ops record/run IDs live in the upload operation;
  the canonical mapping remains the single mapping authority.
- Existing Edition Ops catalogue revision invalidation and mapping audit revision,
  so visiting Edition Ops sees committed changes without a manual Shopify pull.

The move intent commits before Dropbox I/O. A lost response is reconciled only
using that intent, the stable file ID, intended destination, size and provider
content hash. The verified moved metadata is separate from the original source;
this preserves the saved WEBP manifest/version and product inputs. A mapping
failure after movement resumes at the verified destination without another move.

Green status means **Success — synced and PSD mapped**, only after exact product
identity, fresh Edition Ops record/run, destination metadata, authoritative mapping
and preparation exclusion have all been verified. Status polling uses database
metadata only. Remote identity and Dropbox are verified by the explicit operation,
not continuously watched by the UI.

There are no new initial-load, PSD-upload, generation or Copy Prompt requests.
The shared upload prompt and image-generation paths were not edited.

## Preparation exclusion and release dependency

`product_upload_mapping_holds` is an immutable, server-only preparation exclusion
keyed uniquely by operation, Shopify product and PSD. Admission is serialized
against mapping/queue writes. It commits before registration or movement; it is
not a queued job and has no release/scheduling action in this change.

The migration installs five database guards: onboarding admission/claims,
discovery registration, source inventory, conflicting/automatic mappings, and
cloud render jobs. This also prevents older callers or direct SQL inserts from
creating runnable work for the held product/file. Current discovery and queue
callers skip held sources explicitly, including before the discovery seed limit,
so held entries cannot starve unrelated jobs.

Existing Companion handoffs, preparation checkpoints/assets or active render work
are conflicts, not silently cancelled, taken over or reset. This workflow creates
no lifecycle handoff, preparation entry or future runnable queue item. Unrelated
preparation continues using its existing rules.

Before production use, review/apply
`supabase/migrations/20261019095933_product_upload_mapping_only_hold.sql` and deploy
the updated web application and existing discovery worker code together. No new
worker service or Companion desktop restart is required by this implementation.
The new action fails closed before moving a PSD if any required database guard is
missing or disabled. This migration is deliberately not added to automatic startup
migrations. None of these release actions was performed in this task.

## Local verification

The providers were simulated and PostgreSQL execution used disposable PGlite.
Registration, edition initialization, mapping/audits, SQL constraints/triggers,
API dispatch and state verification were the actual application services.

- 34 Sync & Map service/API tests passed: all three modes; new and existing
  catalogue records; already-mapped live PSD; required edition choice; no/multiple/
  conflicting correlation; archived product/run; conflicting Edition Ops IDs;
  source/destination/mapping conflicts; partial save; missing guards; existing jobs;
  double click; expired/stale lease; lost move/mapping acknowledgements; move success
  with mapping failure; stale saved source; zero discovery/queue admission; and
  unrelated queue admission still working. The release check also simulates
  production default grants and verifies the hold table denies service-role
  update/delete/truncate and all browser-role access.
- Supporting upload, source, Dropbox and discovery suite: 97 passed, 2 native
  PostgreSQL concurrency tests skipped, 2 baseline assertions excluded (below).
- Jobs, PSD permission and onboarding coverage passed in the combined service run
  (56 passed, including 29 mapping/API cases at that point; 9 legacy native
  PostgreSQL/snapshot cases skipped). Docker's local engine was unavailable;
  independent native PostgreSQL connection/lock tests were not claimed as run.
- Legacy handoff suite: 14 passed with the unchanged baseline Live-prompt assertion
  below excluded.
- Actual Streamlit upload entrypoint: 8 passed, including persistent Sync & Map
  resume links. Unsaved final section stays
  unmounted and upper mockup/lifestyle/Save All controls remain present.
- Deferred handoff and upload-loading regression checks: 17 passed.
- Six Product Uploads Node suites passed, including popup lifecycle, stale
  operation/save responses, explicit start, double click, close/reopen, cleanup,
  existing focus behavior, clipboard feedback and complete prompt mode/save gates.
- `scripts/verify_product_upload_sync_map.py`: normal browser paths in Chrome and
  Edge plus Chrome failure/reload/retry passed. It uses actual HTTP routes and
  mapping services, disposable SQL, synthetic provider metadata and a small
  Product Uploads host fixture. The upload iframe and surrounding inputs were
  retained. Each scenario made exactly one PSD move, with no preparation jobs,
  browser errors or pre-click mapping/provider requests.

Measured browser fixture timings (loopback, Windows, synthetic metadata; no PSD
byte transfer or real provider latency):

| Scenario | Click to visible success | Backend operation |
|---|---:|---:|
| Chrome normal | 1,035 ms | 156 ms |
| Edge normal | 1,568 ms | 141 ms |
| Chrome mapping failure, reload, retry | 1,981 ms overall | 141 ms successful retry |

Provider stage timings and screenshots are retained in ignored
`output/product-upload-sync-map/results.json` and adjacent PNGs. These numbers do
not predict live Shopify/Dropbox performance and are not PSD upload benchmarks.

Three pre-existing test assertions were reproduced with unchanged baseline
modules loaded from `git show HEAD:<file>`; their implementations were not changed:

1. `test_product_upload_intake.test_prompt_only_account_keeps_access_and_expired_session_is_rejected`
   expects an old manual prompt to return 200 without a saved source (baseline 409).
2. `test_auto_editions_discovery.test_host_claim_does_not_refresh_catalogue_with_v15_enabled`
   expects the old response shape without `product_mockup_renders`.
3. `test_product_upload_handoff.test_prompts_keep_saved_commercial_source_without_old_input_dependencies`
   expects the prior Live prompt price-ladder wording.

No live end-to-end result, real PSD movement, full installed-Companion test or
Dropbox-to-ChatGPT-to-Shopify transfer is claimed. All production verification and
release actions remain outstanding and require separate authorization.

## Files changed

Runtime: `product_upload_mapping.py`, `product_upload_mapping_hold.py`,
`product_upload_api.py`, `product_upload_jobs.py`, `product_upload_services.py`,
`product_upload_mockups_ui.py`, `components/product_uploads/app.js`,
`psd_mapping_store.py`, `auto_editions_onboarding_store.py`,
`auto_editions_discovery.py`, `components/product_uploads/mapping.js`,
`components/product_uploads/index.html`, and the migration above.

Verification: `tests/test_product_upload_mapping.py`,
`tests/test_product_upload_mapping.cjs`,
`tests/fixtures/product_upload_mapping_ui.py`,
`tests/test_product_upload_entrypoint.py`, `tests/fixtures/product_upload_entrypoint.py`,
`scripts/verify_product_upload_sync_map.py`, and this report.

## Owner-authorized release, 19 October 2026

The owner subsequently authorized committing/pushing this implementation, applying
the hold migration, and deploying the existing web and discovery services.
Production testing remains read-only: no real PSD moves, live product edits,
mapping executions or Companion preparation runs.

Preflight confirmed main and the existing web/discovery services were at baseline
`8ee2aa687d04f5bb276a926b0d9e58b7ad1d2e4c`. Nathan's existing Render workspace and
canonical primary service are retained; no Blueprint sync or new service is used.

The reviewed migration was applied to the repository-documented authoritative
Supabase project `ceyzbfpuwuuxaiqwiltz`, recorded by Supabase as version
`20261019103352` (`product_upload_mapping_only_hold`). Its local file SHA256 is
`19bc2d4ee2b893152bf98686f170884c9aab4fbf83ad5ef835eeac086b514b45`.
Read-only verification confirmed all five guards enabled, RLS enabled, zero hold
rows before any user operation, no browser grants, and only SELECT/INSERT for
service_role. Production default privileges required explicitly revoking inherited
service-role grants before granting those two operations; a local regression test
now covers this condition. The full mapping/API suite then passed 34 cases, and
the JavaScript popup lifecycle and topology checks passed again.

Exact deployed commit, Render deploy states and post-deploy read-only evidence are
recorded in the task's local release evidence and Studio status after rollout.
