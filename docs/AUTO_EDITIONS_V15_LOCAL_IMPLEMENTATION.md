# Auto Editions V15 — local Phase 1 implementation

Local only, 15 October 2026 (Australia/Sydney). No commit, push, deployment,
production database write, Shopify mutation or Dropbox asset write was performed
for this task. Original repository and other task changes were retained.

Task: `20261014-1aae0e49` (INTEGRATIONS).
Owner: `codex/v15-20261015-01a13cc7`.
Path: `C:\Dev\SportsCaveWorktrees\sports-cave-integrations-auto-editions-v15-automatic-product-mappin-20261014-1aae0e49`.
Branch: `codex/task/integrations-auto-editions-v15-automatic-product-mappin-20261014-1aae0e49`.
Prerequisite: user explicitly approved the committed V14 snapshot
`ca9ff5c27e3db6a9c6cf9699b5746df220835449` as this task's local baseline.
The older Studio global approved base remains unchanged. The dependency and
approved stale-lock recovery are recorded in this task's Studio history.

## Implemented behavior

- Canonical eligible product registration, used by the existing authenticated
  create/update webhooks, records discovery in the same database transaction.
  A handoff failure rolls back registration and retains the existing webhook
  failure/retry behavior. No new webhook service or Shopify API call was added.
- A durable singleton Dropbox cursor fetches one nonrecursive original-folder
  page at a time (initial page size 200). Cursor and metadata commit together.
  Mapping is disabled until every page in the current inventory has completed.
  Subsequent polls use cursor deltas; no repeated full Dropbox folder scan.
- The original `psd_directory.reconcile`, `title_filename_keys`, `filename_key`
  and `approved_file` functions remain the matching authority. No fuzzy matching.
  Competing product titles, handles, source filenames and ownership are rejected.
- An unmapped product must have one candidate, followed by a current metadata
  read and a transaction recheck of ID, revision, content hash and exact approved
  filename/location. Mapping insertion, existing mapping audit and preparation
  checkpoint insertion commit together. Only `INSERT` is used for a new mapping.
- Verified mappings bypass discovery entirely, including when a source disappears
  from inventory. They are never replaced, rematched or cleared.
- Waiting/review requests survive restarts, failed metadata reads and cursor
  pagination. New source metadata wakes waiting requests. A Dropbox cursor reset
  discards only cached inventory metadata and rebuilds it incrementally.
- One finite bootstrap inserts missing historical preparation checkpoints in
  batches of at most 20, without rematching or changing existing checkpoints.
  Historical artwork stays deferred at priority zero unless existing commerce
  signals or administrator Prepare Now promote it.
- Existing manual Add/Save mapping transactions are unchanged. The queue's
  existing enqueue decision is available inside the new mapping transaction.
  Repeated events preserve active leases, attempts, preparations and approvals.
  A stale prepared revision discovered for a new mapping stays Blocked for review.
- New mappings use priority 2; order urgency, sales/advertisement priorities and
  Prepare Now priority 10 retain their existing rules. The existing worker rotates
  batches of up to 100 pending products, retaining a durable last-check timestamp.
  With V15 enabled, companion claims no longer refresh the whole catalogue.
- Existing Windows companion transfer, Photoshop preparation, number overlays,
  immutable Dropbox uploads and checkpoint recovery remain in use. Existing visual
  approval remains mandatory; Cloud Ready continues to mean TEST downloads only.
- Status reads append durable waiting/review rows without Dropbox or Shopify I/O.
  The explicit administrator diagnostic
  `/api/auto-editions/onboarding/discrepancies?preparation_hash=<hash>&offset=0`
  checks at most 20 recorded prepared asset IDs per call and returns `next_offset`.
  It flags orphan preparations and missing/changed ID, revision, size, name or
  location. It never deletes, overwrites, repairs or approves artwork.

## Changed files

| File | Change |
| --- | --- |
| `auto_editions_discovery.py` | Durable discovery, exact verification, historical bootstrap, worker loop and read-only diagnostics |
| `supabase_backend.py` | Transactional handoff from canonical eligible registration |
| `auto_editions_onboarding_store.py` | Reuse existing enqueue decisions within a caller transaction; optional current-source fence |
| `auto_editions_priority.py` | Bounded, durably rotating priority refresh |
| `auto_editions_onboarding_api.py` | Waiting statuses, explicit diagnostic, V15 claim path without catalogue refresh |
| `sports_cave_worker.py` | Opt-in background thread in the existing worker; shutdown integration |
| `dropbox_integration.py` | Optional deleted metadata, deleted-entry tag and cursor-reset classification |
| `supabase/migrations/20261014234210_auto_editions_v15_discovery.sql` | Additive discovery/inventory/cursor tables and priority timestamp; RLS and server-only grants |
| `tests/test_auto_editions_discovery.py` | Synthetic SQL, API, worker, restart and independent-connection concurrency contracts |
| `tests/test_psd_directory.py` | Repair inherited AST projection fixture's missing pure `print_jpg` dependency; stub cloud link lookup |
| `docs/AUTO_EDITIONS_V15_LOCAL_IMPLEMENTATION.md` | Implementation, validation and integration handoff |

`psd_directory.py`, `psd_mapping_store.py`, source assets, filenames, allocation
logic, certificates, customer ownership, Shopify metafields, Prodigi and
`render.yaml` are unchanged by V15.

## Validation

The existing Python virtual environment and existing PGlite/PostgreSQL runtimes
were reused. No application dependency was added. Native tests refuse any cluster
whose data directory is not this task's `output/v15-native/data` or whose listen
address is not `127.0.0.1`. Each native test creates and removes its own synthetic
database. No production database configuration or data is used.

Focused suite:

```powershell
$env:AUTO_EDITIONS_TEST_PGLITE = 'C:/Users/hello/Documents/sports-cave-image-factory/output/email-idle-pg/node_modules/@electric-sql/pglite/dist/index.js'
$env:AUTO_EDITIONS_NATIVE_TEST_PORT = '56415' # Only when this task's isolated cluster is running.
& C:/Users/hello/Documents/sports-cave-image-factory/.venv/Scripts/python.exe -m pytest tests/test_auto_editions_discovery.py tests/test_auto_editions_onboarding.py tests/test_auto_editions_onboarding_api.py tests/test_auto_editions_priority.py tests/test_auto_editions_cloud.py tests/test_auto_editions_preparation_host.py tests/test_sports_cave_worker.py tests/test_psd_directory.py tests/test_product_activation_sync.py tests/test_product_webhook_restoration.py tests/test_auto_editions_jobs.py tests/test_auto_editions_speed.py tests/test_auto_editions_eligibility.py -q
```

Coverage includes PSD-before-product, product-before-PSD, manual Add, duplicates,
unclear matching, stale revision/location/ownership, incomplete inventory,
restarts, interruption/rollback, lease recovery, historical bootstrap, source
deletion/cursor reset, mandatory approval, role denial, priority rules and unchanged
allocation/certificate/ownership fixtures. Native PostgreSQL additionally checks
concurrent registration/mapping lock order, duplicate mapping and single-winner
preparation claims. Existing upload-resume tests cover interrupted prepared asset
uploads without overwriting immutable assets.

Final combined result: **156 passed, 14 subtests passed**, with five inherited
deprecation warnings. The native PostgreSQL V15 suite independently passed all
**30 tests**, including concurrent transactions. Final combined log:
`output/v15-native/final-tests.log`.

Static checks: `git diff --check`, Studio Verify and
`python scripts/validate_render_topology.py`. Test results are recorded in Studio
for the current uncommitted file snapshot. Existing FastAPI/Starlette deprecation
warnings are unrelated to V15.

Studio Verify's registry comparison to the older `bdc46c29` base fails on
inherited whitespace in `docs/DEVELOPER_STUDIO_V9_LOCAL.md`,
`scripts/photoshop/inspect_psd_editions.jsx`, two inherited tests and two tracked
`tmp` logs. These files are unchanged by V15 and are intentionally left intact.
Syntax, secret-pattern checks and Studio infrastructure tests otherwise passed.
The same static verifier against the explicitly approved V14 prerequisite is
recorded separately in `output/v15-native/task-static-verify.json`; the V15 diff
and topology checks pass. The registry failure is retained, not suppressed.

## Exact remaining integration work

No local backend implementation is intentionally deferred. Production integration
requires fresh, explicit authorization and has not been attempted:

1. Review this uncommitted task diff against the approved V14 prerequisite, rather
   than treating the older global Studio base as the V15 feature diff.
   Resolve the inherited Studio baseline comparison during release review.
2. In an authorized isolated release candidate, apply the additive migration after
   existing PSD mapping and V6/V11 preparation schemas; verify server role grants.
3. Enable `AUTO_EDITIONS_V15_ENABLED=true` consistently on the existing primary app,
   authenticated webhook service and existing worker. Default is disabled. The
   Windows companion protocol needs no change and must already be connected to
   the authorized preparation host with Photoshop available.
4. Perform an authorized staging/host acceptance using test-only artwork: an
   eligible product event, both source-arrival orders, preparation, upload receipt,
   mandatory visual review and TEST download. No real Shopify/Dropbox/Photoshop
   integration or hosted acceptance was exercised in this local task.
5. Before any future authorized Blueprint sync, inspect its preview and rerun
   topology validation. This task adds no Render service, cron or dependency.

Discovery polls at most every five minutes while idle; new registration requests
wake the cursor for the next worker cycle (60 seconds). Waiting requests also have
a 15-minute retry interval, interrupted by new source metadata. Initial inventory
and historical bootstrap are bounded and can take multiple cycles. Priority signal
latency grows by one cycle per 100 pending products. Product identity snapshots
are read from the local database for due mapping checks to preserve the original
cross-product ambiguity rules; they are never fetched from Shopify or refreshed
on host claims/page loading. Prepared diagnostics verify recorded metadata; they
do not download artwork or replace pixel/visual approval.

The task remains uncommitted. Studio may mark it Tested, but clean committed
review readiness is intentionally unavailable without commit authorization.
