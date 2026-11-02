# Tony Gwynn / Jaxon Smith-Njigba: local investigation and recovery proposal

Status: implemented and tested locally; NOT committed, pushed, deployed or installed.
No production mappings, jobs, allocations, settings or assets were changed.
Read-only diagnosis performed 24 October 2026 Sydney time.

## Isolation

Verified the EDITIONS category checkout at `C:/Dev/SportsCaveWorktrees/sports-cave-editions`, branch `codex/category/editions`, was clean. Created Studio task `20261023-7a07f6a2`, owner `codex-editions-20261024-attachment-trace`, in its own worktree:
`C:/Dev/SportsCaveWorktrees/sports-cave-editions-trace-tony-gwynn-and-jaxon-smith-njigba-ma-20261023-7a07f6a2`.
Branch: `codex/task/editions-trace-tony-gwynn-and-jaxon-smith-njigba-ma-20261023-7a07f6a2`.
Base: `24fd24f7e63952e1a251e9d8e61b41e84a7998c2` (current main/live application).
Other tasks and their unfinished changes were preserved.

## Persisted trace

Times below are on 23 October 2026. Sydney was UTC+11.

| Evidence | Jaxon Smith-Njigba — Seattle Reign | Tony Gwynn — Mr. Padre |
|---|---|---|
| Edition Ops product ID | 735 | 736 |
| Shopify product ID | 15440506487091 | 15440511926579 |
| Dropbox file ID | `id:u1tYiAa2O-AAAAAAAACJXA` | `id:u1tYiAa2O-AAAAAAAACJXQ` |
| PSD filename | `Jaxon Smith - Seattle Reign.psd` | `Tony Gwynn - Mr. Padre.psd` |
| Dropbox revision inspected | `0165e783eedd560000000036d367e13` | `0165e7868e60c9f000000036d367e13` |
| Dropbox content hash | `2c69d92809cd7f4168c72022c01bf794aa68102fac8aa137e312580e0e5ddfea` | `51589e009aa4b2be75a1d075dba1a2417b3d30266c187620eb4f67912f5bc89f` |
| Manual attachment audit ID | 296 | 297 |
| Attachment persisted / checkpoint created (UTC) | 01:56:46.752831 | 02:06:00.011360 |
| Attachment persisted (Sydney) | 12:56:46.752831 | 13:06:00.011360 |
| Claimed (UTC) | 01:57:08.142481 | 02:06:07.184148 |
| Preparing (UTC) | 01:57:11.968471 | 02:06:11.737322 |
| Photoshop diagnostic (UTC) | 01:57:49.371088 | 02:06:51.725351 |
| Needs PSD Repair persisted (UTC) | 01:58:04.019549 | 02:07:06.078369 |
| Terminal time (Sydney) | 12:58:04.019549 | 13:07:06.078369 |
| Local Companion attempt | `fff01f1f756130c6f786a940988e9fc1d1531d8c54b44fff` | `5cfa24e56ee9885b33910238049d503c56a4e10a60d1269d` |
| Retained input bytes | 183705244 | 197902154 |
| Edition total / next allocation | 100 / 50 | 100 / 2 |
| Existing active edition run | `34d693e6-0aa9-43bb-8657-c6cf5010786c` | `d34c4b26-d4ba-461a-86ab-0a6f18d19244` |

Mappings are persisted manual records, `verified=true`, state `Linked`. This verifies attachment metadata, not print readiness. Their `mapping_confirmed` events and onboarding creation commit with attachment save. Each was priority 2 and claimed once. Both onboarding rows remain `Needs PSD Repair`, with no preparation hash, replacement or reset cancellation. Their old leases have expired. No matching preparation, transfer session or customer render job was found. Therefore numbered assets and cloud receipts have not been produced for these attempts. Shopify Active status is not the evidence used for this conclusion.

The first failed transition for BOTH is automatic role detection after Photoshop inspection. Diagnostic code: `PLAQUE_AMBIGUOUS`, stage `Photoshop`. Exact error emitted by `auto_editions_onboarding.detect_roles`:

> A unique recognised collector plaque is required; manual role review needed.

The automatic caller is `scripts/studio/auto_editions_local.py` after inspection, before `prepare_worker`. Both durable local journals agree with the server diagnostic and terminal status. Neither job failed at attachment save, queue admission, Companion connectivity, asset upload or cloud confirmation.

## Confirmed shared cause

Both retained inspections contain exactly one visible, independent top-level smart-object layer named `limited-edition-plaque (1)`, layer ID 39. The old detector recognises only exact names `limited-edition-plaque` and `SC_EDITION_PLAQUE` (or exact pinned source evidence). It rejected this numeric suffix despite an independent editable `001 / 100` text layer contained inside that plaque.

Jaxon: number layer 42, bounds `[2306,1822,2513,1863]`; plaque bounds `[2028,1709,2638,1908]`.
Tony: number layer 40, bounds `[588,1775,861,1823]`; plaque bounds `[207,1619,1033,1889]`.
Both: 2835×2004 RGB, 8-bit, tagged `sRGB IEC61966-2.1`, installed `Cinzel-Medium`, Photoshop 27.11.0. Their inspections also record bounded smart-object traversal warnings; this change does not suppress them or certify embedded content.

Comparison: Tempted, Shopify product `15432135377203`, reached persisted `Cloud Ready` at 2026-10-22 03:18:21.218942 UTC. Preparation `36f0d1f9569ec87b74c15c84b38ba6b61d5da9113128943907992409f339616c` has 101 asset receipts, three proofs and a matching receipt preparation hash. Its same-sized, same-profile/font Photoshop inspection has canonical `SC_EDITION_PLAQUE` / `SC_EDITION_NUMBER` roles. Both old and new detectors return identical Tempted role/geometry results. It passed this transition because its plaque name was already recognised. Its earlier package-transfer recovery is a separate, previously released issue.

## Local repair

`auto_editions_onboarding.py` now recognises only the known plaque asset basename with a positive numeric suffix, such as `limited-edition-plaque (1)`. A suffixed candidate must be a top-level visible smart object or raster layer without a smart-object chain. The exact original layer name is passed onward; no PSD is renamed or modified by detection.

All recognised candidates are counted before containment checks. Two candidates, including a canonical plaque plus a suffixed copy, still require review. Arbitrary names, trailing text, text layers, nested copies and out-of-plaque numbers remain rejected. Existing number uniqueness, editability, total/format, font, colour and preparation checks are unchanged. The same shared detector serves future automatic manual attachments.

Existing save/queue logic already worked; it was not rewritten. Queue retries still require the recorded correction to be confirmed. No allocation, source-profile, pixel-budget, geometry, approval or receipt policy was changed. Existing scale policy still selects 4× (11340×8016) for these sources; this is TEST preparation and is not supplier certification.

## Picker investigation and limit of the evidence

`psd_directory.render_missing_link_guard` declares `psd_directory.psd_picker_events` against tracked `components/psd_picker` assets. Both `index.html` and `inline.js` are present in Git. Live responses during this diagnosis were HTTP 200, 7451 and 19611 bytes respectively, with correct content types and content matching the checkout. Historical Render logs show successful component and helper requests around the attachments, including 01:55:45 UTC. No matching 404/500/503 entry was found in the searched 22 October 13:00–23 October 20:45 UTC interval.

A fresh authenticated Edition Ops page loaded the component without the reported warning or component JavaScript errors. Both actual saves persisted and both jobs were claimed, proving that this warning did not prevent THEIR save/queue transition.

The historical warning's own timestamp/request/console error was not supplied and its cause was not reproduced. Do not describe it as fixed or assign it to these failures. No speculative picker production code change was made. The browser regression now serves the actual helper asset (the old test returned 404 for it) and verifies save, replacement/cancel and persisted mapping context after reload. Its HTTP/API persistence is mocked; the separate SQL test exercises real disposable PostgreSQL semantics. Actual live save/reload mutation was deliberately not attempted.

## Versions and release dependency

Fresh heartbeat at 2026-10-23 20:47:12.571412 UTC: Auto Editions Companion instance `9f4b457962762c5e9d05b43f`, revision `b78b78356cbc891dfd8b94aaec21d3082cad5642`, protocol 1, Idle, processor lock false. Worker heartbeat at 20:47:02.287098 UTC: Render `24fd24f7e63952e1a251e9d8e61b41e84a7998c2`, Live, protocol 1. Both failing diagnostics identify Companion b78. Relevant detector, role-evidence, local processor and picker code were identical between b78 and current main before this patch. There is no evidence of a compatibility mismatch causing these failures.

The Companion WILL need the new detector installed when this repair is released: detection executes locally. This is the Photoshop/Edition Ops Auto Editions Companion installed from the approved b78 release, not the screen task recorder helper. No recorder files or installation were touched.

The changed detector is part of the preparation generation fingerprint. Local candidate generation is `d5e8adaf0f0ed3f7008b3b0326b3bdb60b07c66aa0683e1e045de97fbdd20597`; installed generation is `4b7c8bb87398acb1e38e53b14c4728bf8754b904e18c17fa64cc47f789c95c96`. The existing resumable acceptance gate checks this exact generation. Do not copy the old acceptance hash or disable that gate to deploy this change.

## Validation

- Focused Python suite: **81 passed** across onboarding, API, preparation host, picker API/permissions, package validation and large-package transfer.
- Worker Health normal recovery API/queue checks: **4 passed**, covering repair confirmation, duplicate request identity, owned leases and protected state.
- Real headless Chrome picker regression: passed with both real component frontend files, search/select/save, replace/cancel and reload; no live provider network or JavaScript errors.
- Read-only retained-inspection comparison: the old detector reproduces the exact error for both products; the local detector accepts their exact recorded geometry, names and font. Tempted is unchanged. Evidence: task runtime `retained-inspection-comparison.json`.
- New disposable PGlite test exercises actual `PostgresMappings.attach`, reload through another store instance, automatic queue creation, duplicate save, absent Companion, expired lease/reconnect, stale-worker rejection, retry and duplicate retry. One mapping/audit/onboarding row remains, next edition stays 50, and no customer render job is created.
- Existing large-package tests use bounded disk/HTTP processing and synthetic assets, including interrupted transfer and single import/receipt recovery. These are local checks, not new live Render/provider acceptance.
- The optional legacy standalone PostgreSQL/snapshot suite was attempted separately: nine cases skipped because `PSD_LOCAL_TEST_PORT` is not configured. The new PGlite save/queue test above ran successfully; no skipped tests are included in the 85-passed total.
- No Photoshop preparation, real product upload, cloud-sync recovery or new production approval was run.

## Concrete release / targeted recovery proposal — requires owner approval

1. Review and authorise a focused commit/push/release of this task only. Retain unrelated unfinished work. Deploy to existing primary `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`) and its existing worker where shared preparation code runs; create no service or database migration. Install the matching immutable Auto Editions Companion through its existing supervisor, only after it is idle and ownership is safe. Do not update the screen recorder.
2. Run the existing isolated, administrator/host/run-scoped native provider/PostgreSQL/retention/resource acceptance for the NEW final generation, including the large-v2 transfer case. Verify rollback/reconnect, integrity, retained assets, cleanup and memory evidence before changing only the required resumable acceptance generation/evidence settings. Retain existing bounds, production readiness rules and gate protections. A local synthetic pass does not replace this acceptance.
3. Immediately before recovery, re-read each exact mapping and Dropbox file revision/hash above, edition total/run/next number, queue status, holds, review/reset states and fresh idle Companion heartbeat. If any identity has changed, stop and validate the new source normally.
4. Use Worker Health's existing mapped-design queue action, with correction confirmation and a stable request UUID per product (`POST /api/worker-health/enqueue`: `product_gid`, `request_id`, `repair_confirmed:true`). Target ONLY `gid://shopify/Product/15440506487091` and `gid://shopify/Product/15440511926579`. This retries their EXISTING onboarding checkpoints, rather than reattaching PSDs, making duplicate jobs, resetting runs or editing allocations. Process one at a time.
5. Preserve the two failed local journals and PSD copies. They contain inspections, not completed numbered packages: there is no package upload to resume. Do not directly replay their expired grant/lease. A normal retry issues a new lease/local attempt; incompatible old-generation caches cannot be trusted. Let the normal path inspect/prepare and retain recoverable queued work if the Companion becomes unavailable.
6. For each product, verify claim → Photoshop completion → validated master and 100 numbered patches → finalized transfer → authoritative cloud receipts with matching preparation/source hashes, required proofs and final server checkpoint. Recheck the original edition run and next allocation values. Report the actual resulting technical/review state; never force `Cloud Ready`, approve visual quality or mark print ready to get past a failure. Any subsequent colour, visual, supplier, size, bleed or production approval requirement remains a blocker until actually satisfied.
7. If the picker warning recurs, capture its Sydney time and failing component request/console error on that session. Repair the evidenced loading cause and verify it independently; do not hide the warning or claim the current successful loads explain the historical event.

Remaining blockers: owner release/installation/acceptance and targeted retry authorisation; actual post-repair Photoshop exports and cloud receipts; all normal technical/production readiness results. The historical picker warning remains unproven, rather than falsely marked resolved.
