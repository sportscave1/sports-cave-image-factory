# Product Uploads hold: manual PSD recovery (local only)

Task: `20261020-bfc2ace1`, owner `codex-01a1571e-mapping-recovery`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-products-edition-ops-manual-psd-takeover-failed-pro-20261020-bfc2ace1`.
Branch: `codex/task/products-edition-ops-manual-psd-takeover-failed-pro-20261020-bfc2ace1`.
The supplied main checkout is dirty with unrelated work. PRODUCTS category is an
idle entry point. Studio allocated this isolated task; its initially clean base
predated current mapping code, so this task uses existing remote main commit
`8b9a1a31e7b03b78cab099bc3e3ed9230555d235`. No existing worktree was edited,
committed, reset, stashed, merged, pushed or deployed by this repair.

## Root cause and history

`90fd2351` (19 October 2026, 21:34 Sydney) added the mapping-only hold, the
Postgres preparation guards, and the unconditional manual-attach rejection in
`PostgresMappings.attach`. This prevents discovery/preparation from claiming a
PSD while Sync & Map is moving and linking it. Failed attempts intentionally
retain their hold and move progress for safe retries; the manual Attach PSD path
had no way to retire such an attempt.

`dfe44257` (20 October, 09:39 Sydney) added the durable verified completion
receipt, admitting ordinary work after automatic finalisation. Failed operations
still do not meet that receipt. `8b9a1a31` (20 October, 22:53 Sydney) fixed native
UUID run receipts and offered reopening the earlier hold-owning attempt. It did
not add manual takeover. This is a scoped interaction with an incomplete upload,
not evidence that ordinary manual mapping is generally broken.

## Production read-only evidence (20 October 2026)

Authoritative project is `ceyzbfpuwuuxaiqwiltz`, established from repository
deployment reports. The similarly named project has no intake table. All remote
queries were SELECTs; Dropbox access was metadata-only, by stable file ID.

- Product: `gid://shopify/Product/15430466666803`.
- Edition Ops record: **733**, Ruth vs Mantle — Pinstripe Immortals Wall Art.
- Active edition run: `8ff9bb78-49c5-48ce-a4be-01c170fa1d00` (the supplied ID
  identifies the edition run, not the hold-owning upload operation).
- Edition total **100**, next number **1**. No mapping is currently persisted.
- Hold-owning operation: `48fe3e9a-ceb0-4589-8585-95f05eaed54d`, created
  20 October at 10:52:58 UTC / 21:52:58 Sydney. State **Mapping failed** at
  Checking edition setup, lease expiry null; no move intent/moved receipt.
- Sibling attempts `46f83a53-da95-4438-9e55-5c26ee4a6f54` and
  `9cf42f1b-560e-4c50-a9da-6b87de34863a` are also failed without a live lease.
  The latter explicitly points back to the hold-owning attempt.
- No onboarding record, rendering jobs or retained preparations matched this
  product or PSD at inspection. This is a snapshot, not authority to bypass the
  transactional worker checks at a later Save.
- Stable PSD: `id:u1tYiAa2O-AAAAAAAACGzQ`, **193,732,129 bytes**.
- Dropbox currently resolves it to:
  `/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/Pinstripe Immortals - Ruth & Mantle.psd`.
- Current revision: `0165e447ef41163000000036d367e13`; server modified
  20 October at 12:09 UTC / 23:09 Sydney. The attempts still capture its earlier
  Review-subfolder path/revision. Do not move it back or replay a rename.
- The metadata connector did not expose a current content hash. Recovery obtains
  fresh full metadata through the existing PSD-open adapter and requires its
  stable ID, content hash and byte size to match the retained source. No claim of
  production content-hash verification or completed recovery is made.

## Targeted repair

Ordinary attachment retains its permissions, filename confirmation, replacement
checks, folder policy, audit and preparation behaviour. Only an administrator
saving an incomplete held PSD is offered an additional explicit checkbox.

The first Save is non-mutating and returns the exact hold-owning operation ID.
The confirmed Save locks matching intake rows NOWAIT **before** mapping locks,
matching Map's lock order. This rejects an in-flight worker even if its saved
lease has expired. Future leases, conflicting identities, existing preparation,
queued/generating renders and retained preparation assets also block takeover.

The transaction validates fresh metadata, retains all progress/error/move fields,
adds a terminal manual-takeover receipt to the holder and matching sibling
attempts, and writes and rereads the one authoritative manual link. Any failed
validation or persistence rolls the whole operation back. The mapping audit
records the takeover operation. The original hold row is retained unchanged and
becomes inactive through its terminal receipt; no holds or history are deleted.
Ordinary manual Save preparation admission remains unchanged.

The additive migration recognises that receipt and installs an immutable intake
trigger. Older code cannot replace a retired operation's lease/source/progress or
delete its recovery history. Current Map rejects retired attempts before provider
mutations. No table permissions are expanded, no browser privileges are granted,
and completed automatic receipts retain their existing semantics.

## Exact recovery action for this PSD, after separately authorised release

1. Apply the reviewed additive migration and deploy the matching application
   repair. Neither has been done by this task.
2. As an administrator, open Edition Ops record **733** / product
   **15430466666803**, choose **Attach PSD**, and select
   **Pinstripe Immortals - Ruth & Mantle.psd** in the main approved folder.
3. Check **Filename differs — I confirm this is the correct artwork**, then
   **Save PSD**. The response offers takeover of retained operation
   `48fe3e9a-ceb0-4589-8585-95f05eaed54d` without modifying it yet.
4. Check **Take over this inactive Product Uploads mapping. Preserve its history
   and permanently stop its retries**, then **Save PSD** again.
5. Save rechecks all worker/identity conditions. If clear, it commits the terminal
   receipts and the manual link together. Verify record 733 opens the same stable
   PSD ID at its current main-folder location and that a fresh mapping read is
   Linked/verified. The receipts identify Edition Ops record 733; run UUID,
   edition total and next number remain unchanged.

Do not clear the hold directly, restart an old automatic attempt, relocate the
PSD, overwrite a destination or create a second link as a workaround. If Save
reports active/conflicting work or changed content, stop and review that state.

## Verification and limits

Tests use synthetic representative records and simulated Dropbox metadata only;
no production records, credentials or artwork were used in the local fixtures.

- Disposable PostgreSQL/PGlite tests cover ordinary matching attachment, confirmed
  mismatch, explicit takeover, changed content, stale picker state, conflicting
  ownership, live leases, preparation/rendering conflicts, retained moves and a
  lost move acknowledgement, sibling retirement, immutable old-code retry/deletion
  rejection, idempotent reopened links, unchanged edition counters, fresh link
  reads and migration/privilege failure modes.
- Existing manual-picker API, VA permission and automatic mapping/UUID suites
  passed (82 tests before final audit annotation/guard-specificity hardening).
- Real PostgreSQL 17 in a separate disposable localhost-only Docker container
  verified two-connection NOWAIT contention and successful attachment after the
  in-flight row lock was released. Container is removed after testing.
- Headless Chromium ran the actual picker HTML: mismatch check, separate takeover
  consent, active-worker error, successful Save message and consent reset on
  selection change. Browser requests used synthetic routes only.
- After final audit annotation and trigger-target checks, 30 directly affected
  tests passed again (manual recovery, picker API, VA permissions and Chromium),
  and the real two-connection PostgreSQL test passed again. No skips/failures.
  Changed Python syntax and `git diff --check` passed.

Reproduce the PGlite suite with `AUTO_EDITIONS_TEST_PGLITE` set to the installed
PGlite `dist/index.js` and run:

```powershell
python -m pytest tests/test_product_upload_manual_takeover.py tests/test_psd_picker_api.py tests/test_psd_va_permissions.py tests/test_product_upload_mapping.py tests/test_product_upload_mapping_uuid.py -q
python -m pytest tests/test_psd_manual_takeover_ui.py -q
```

For the concurrency test, use a **fresh disposable** PostgreSQL 17 container,
localhost binding only, database `manual_takeover_test`, local test user postgres
and an ephemeral random password supplied as `MANUAL_TAKEOVER_LOCAL_PASSWORD`.
Set `MANUAL_TAKEOVER_LOCAL_PORT` to its allocated localhost port and run
`python -m pytest tests/test_product_upload_takeover_concurrency.py -q`.
The isolated container is removed after the test; do not target an existing DB.

Production remains unrecovered until the migration/application release and the
explicit manual Save are separately authorised and executed. No commit, push,
merge, deployment, production mapping, file move or remote schema change occurred.

Changed implementation: `product_upload_manual_takeover.py`,
`psd_mapping_store.py`, `product_upload_mapping.py`, `files_upload_api.py`,
`components/psd_picker/picker.html`,
`supabase/migrations/20261020121849_product_upload_manual_mapping_takeover.sql`.
Tests: `tests/test_product_upload_manual_takeover.py`,
`tests/test_product_upload_takeover_concurrency.py`,
`tests/test_psd_manual_takeover_ui.py`, `tests/test_psd_va_permissions.py`.
This report: `docs/PRODUCT_UPLOAD_MANUAL_PSD_RECOVERY.md`.


## Subsequent release authorisation

The user subsequently requested pushing this repair to GitHub/Render. This
approves releasing the reviewed application patch and its required additive
migration. The release does not execute manual takeover, attach this PSD, change
edition counters, move files or retire an operation. Those remain the explicit
administrator Save PSD recovery action described above. Production verification
uses read-only checks after the schema deployment.
