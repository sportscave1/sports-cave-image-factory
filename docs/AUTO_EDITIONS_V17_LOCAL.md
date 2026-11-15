# Auto Editions V17 — implemented and tested locally, NOT activated

## Isolation and authority

Task `20261015-ea887e40`, owner `codex/v17-continuous-20261015`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-auto-editions-v17-continuous-paid-order-fi-20261015-ea887e40`.
Branch: `codex/task/integrations-auto-editions-v17-continuous-paid-order-fi-20261015-ea887e40`.
Approved base: `f36516699b5c7e724605ba526080f7af4cbed2a4`, independently matching GitHub main and the application, webhook and worker at the read-only inventory checkpoint. Includes SC3303 correction.

This task includes the 19 reviewed, uncommitted reliability dependency files from task `20261015-87d20b92`, at the same approved base. That worktree remains untouched. See `AUTO_EDITIONS_PERMANENT_RELIABILITY_LOCAL.md` for its diagnostics and installation details. Its historical statement that Deferred remains ineligible describes the dependency before V17; the opt-in policy below supersedes it.

No commits, pushes, deployments, production configuration/database writes, live preparation or companion installation were performed. No Shopify, certificate, allocation, approval or Dropbox asset was changed.

## Confirmed causes and catalogue audit

- Legacy priority-zero rows were intentionally excluded from claims. Historical bootstrap also stopped checking for missing handoffs after its completion marker. This prevented continuous catalogue completion without commerce/manual promotion.
- Read-only authoritative project `ceyzbfpuwuuxaiqwiltz`: 285 mappings, zero missing onboarding checkpoints, 63 preparation records. Raw queue: 166 Awaiting (165 priority zero, one priority five), 76 Blocked, 26 Needs PSD Repair, 16 Cloud Ready, one Preparing. These are queue states, not a fresh certification of assets or owner approvals.
- All 167 historical records remain present. Two had already been promoted for real orders; 165 remained Deferred. V17 deliberately makes eligible Deferred records claimable when enabled; local implementation has not changed those production rows.
- SC3304 allocated edition 009 already existed. Recorded queue wait was about 92 minutes; actual Preparing lasted about 3m22, then Blocked with `Photoshop reference has a different colour profile`. Original/reference PNG had ICC evidence; master and number exports lacked ICC. No completed package/approval existed, so no JPG was correctly available. The allocation remains untouched.
- Reused dependency repairs missing export ICC only with conclusive Photoshop profile evidence, preserving compressed pixel bytes and all original validation gates. Supervisor, owned-lease heartbeats, durable package recovery and pending checkpoint acknowledgement are included.
- Additional V17 defect: checking only the newest 20 journals could hide older interrupted work behind completed history. A rotating 20-journal window now prevents permanent starvation.

## Implemented behavior

`AUTO_EDITIONS_V17_CONTINUOUS_ENABLED=false` by default. No migration, new dependency, service or scheduled task is required.

When enabled:

1. The existing worker seeds at most 20 missing mapping checkpoints per existing cycle, including mappings arriving after bootstrap. Existing V15 webhook registration and bounded Dropbox cursor discovery handle product-before-PSD and PSD-before-product. Verified mappings are never rediscovered/rematched by this change.
2. Existing queue claims include all uniquely mapped catalogue products with a unique ledger identity and edition limit 1–1000, even without sales/activity. Original PSD location/metadata is verified again before a grant. Invalid, ambiguous or retained-preparation rows cannot start a fresh catalogue preparation.
3. Paid outstanding work (stored priority 8) wins the next claim, including over manual catalogue Prepare Now. Administrator priority 10 is next, advertised products 7, existing commerce priorities 6/5, newly linked 2, continuous catalogue 1 (legacy zero also eligible). No active Photoshop save/upload is preempted. Default-off mode retains legacy priority ordering.
4. Claim serialization and owned 45-minute leases remain. Three interrupted claims become a retained actionable failure. Three transport recovery cycles also report a terminal failure rather than monopolising the catalogue; verified local packages remain for safe recovery. Backoff is bounded at 300 seconds. A stuck Photoshop call/uncertain lock still requires operator inspection; no lock is stolen.
5. Existing immutable preparations are retained. A current exact existing product-wide approval can be reused, with no conflicting layout and complete verified receipts. No approval is created/copied by V17. Changed/uncertain artwork retains review. Missing receipts prevent Cloud Ready and the corresponding Orders JPG link, even if an old approval exists.
6. Receipt checks require the preparation hash, expected master/number names, unique file IDs and revisions for all expected files. Existing source, pixel, geometry, edition-total and immutable-hash validation remains authoritative. Stored receipts are not a new remote Dropbox scan or supplier certificate.
7. The existing preparation expander shows eight compact counts, current design, last successful upload checkpoint and host heartbeat. Uploaded and Production Ready remain distinct evidence-based counts in the tooltip. Remaining includes failures/review, so a zero runnable queue does not falsely imply completion. No new table column, page or toolbar is introduced.
8. Summary refresh uses one additional batched SQL status read only while the existing expander is mounted/visible, every 25 seconds; no per-row Dropbox calls. Review controls, confirmation, selection and scroll are preserved. Passive updates pause during review/input. Existing Edition Ops table refresh behavior is unchanged.

The summary uses up to five SQL statements per refresh (queue, waiting discovery when enabled, mapping/last-success aggregate, host aggregate, status batch); it makes no provider requests. Worker discovery/priority cadence and single Photoshop concurrency remain unchanged. Local recovery reads at most 20 journals per pass, while its existing directory metadata enumeration still scales with retained local folders. Existing verified cleanup remains in use; no historical files are deleted by V17.

## Focused validation

All SQL fixtures used disposable loopback PostgreSQL under this worktree at port 56421, with synthetic identities. Browser routes were intercepted; no Photoshop or production provider calls ran.

- Initial V17/discovery combined run: **42 passed** (12 V17 + 30 discovery), including registration retry/rollback and late source arrival.
- Final paid-first and V17/reliability run: **33 passed** (13 V17 + 20 reliability). Tests drain 167 synthetic historical mappings without changing mapping/edition/allocation/certificate snapshots; test paid-before-manual, no active preemption, rollback, duplicate events, retained approval/JPG eligibility, incomplete receipts, permissions and terminal upload failure.
- Final rotating journal recovery and reliability: **21 passed** (new rotation case + same 20 reliability). These runs overlap; do not add them as unique totals. V17 now has 14 dedicated cases.
- Focused existing onboarding/API/host/priority/status/runtime/Reset/quality/lifecycle regressions: **144 passed, 7 optional PGlite-fixture skips**. Native discovery/V17/reliability tests exercised real isolated SQL separately.
- Existing companion/startup/release tests: **99 passed**.
- **Six desktop/mobile browser scenarios passed**: V17 counts/polling/selection/scroll/review/unavailable behavior at 1280 and 390px, existing responsive onboarding review at both widths, recovery/Uploading/Review/JPG status gate at both widths. No whole table redesign or hosted performance claim.
- Diff whitespace and canonical Render topology validation passed.

334-row synthetic status comparison (285 mapped, retained preparation evidence, 49 unmapped; seven samples): final median **79.69 ms off / 81.46 ms on**, one SQL query and zero Dropbox calls. Peak traced Python allocation **1,268,064 / 1,402,190 bytes**, response **90,751 / 97,102 bytes**. Earlier run varied 81.64 / 92.49 ms; timings are local noise, not proof of a hosted speedup/regression. Enabled receipt validation adds bounded work. Measurements: `output/v17/performance.json`; browser captures: `output/v17/onboarding-1280.png`, `onboarding-390.png`.

## Companion and release requirements

Existing installed runtime remains `v9-auto-editions-oneclick-sc3284-handshake-20261014`; its companion hash was `4402cd3338c4ffffa39a3b7c458476094d923040de4cf87de404a635d9af0470` at inventory. It does not contain these new local reliability/V17 changes. The existing sign-in task `SportsCave-Studio-20261011-7192d493` already uses interactive sign-in, recurring recovery and IgnoreNew. Do not add another startup processor.

Separately approved release order:

1. Integrate only this reviewed task and its stated reliability dependency; deploy compatible server revisions with V17 still false. Preserve V6 TEST cloud gate, V15 discovery, V16 policy/standards and canonical topology. No new migration is needed.
2. At an authorised idle checkpoint, update the existing companion runtime using its existing controls, with rollback copy. Include companion.py, draft_ui.py, auto_editions_local.py, scripts/prepare_auto_editions.py, Photoshop JSX and auto_editions_colour.py. Preserve owner, home, port, DPAPI pairing, journals, source/package folders and scheduled task. Never stop active work or delete an uncertain lock.
3. Authorise an isolated test artwork using an existing authorised allocation. Verify real Photoshop/profile preservation, sleep/wake/restart, interrupted upload, verified Dropbox receipts and owner review. No manufactured approval or new real allocation.
4. Separately activate V17 consistently on the existing application, webhook and worker only after readiness checks. Coordinate configuration rollouts around active work. No new services or cron jobs.
5. Observe paid-first claims and gradual historical draining, then verify an approved unchanged design's existing JPG and a new design's mandatory review. SC3304 still needs an authorised retry and its first owner review; its edition 009 must be reused.

Rollback: disable only V17 on the same processes. Newly assigned catalogue priority 1 and legacy priority 0 are immediately excluded from fresh claims; active owned preparation finishes normally. No checkpoint, approval, asset, allocation or history is removed. Existing commerce/manual eligibility continues. Retain compatible server reliability endpoints if the updated companion is installed.

The machine must be interactively signed in, awake, online, with Photoshop.Application.200, required fonts/profiles and at least the existing 8 GiB free-space threshold. Credential revocation/expiry requires authorised re-pairing; Photoshop dialogs, corrupted sources and uncertain locks require operator repair. Actual new Photoshop execution, real Dropbox transfer interruption and Windows sleep/wake remain untested by this local-only task. Production readiness still requires the existing approved supplier standards; Cloud Ready does not authorise fulfilment.

## Exact file inventory

- `.env.example`
- `auto_editions_v17.py` (new)
- `auto_editions_colour.py` (new dependency)
- `auto_editions_discovery.py`
- `auto_editions_onboarding_api.py`
- `auto_editions_onboarding_store.py`
- `auto_editions_priority.py`
- `auto_editions_runtime.py`
- `auto_editions_setup_api.py`
- `auto_editions_status.py`
- `auto_editions_store.py`
- `orders_page.py`
- `components/auto_editions/onboarding.html`
- `components/auto_editions/status.html`
- `scripts/photoshop/prepare_auto_editions.jsx`
- `scripts/prepare_auto_editions.py`
- `scripts/studio/auto_editions_local.py`
- `scripts/studio/companion.py`
- `scripts/studio/draft_ui.py`
- `tests/test_auto_editions_preparation_host.py`
- `tests/test_auto_editions_reliability.py` (new dependency)
- `tests/test_auto_editions_reliability_ui.cjs` (new dependency)
- `tests/test_auto_editions_v17.py` (new)
- `tests/test_auto_editions_v17_ui.cjs` (new)
- `docs/AUTO_EDITIONS_PERMANENT_RELIABILITY_LOCAL.md` (new dependency report)
- `docs/AUTO_EDITIONS_V17_LOCAL.md` (this report)

**Result: local implementation/fixture acceptance PASS. Live unattended V17 acceptance NOT RUN; release/installation/activation remains unauthorised.**
