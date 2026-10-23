# Auto Editions attachment repair release — 24 October 2026

This follows [the source investigation](AUTO_EDITIONS_ATTACHMENT_TRACE_20261024.md). The owner explicitly authorised commit, push, Render deployment, Auto Editions Companion update, required acceptance configuration and normal targeted recovery of Tony Gwynn and Jaxon Smith-Njigba. The owner also confirmed the historical picker warning no longer appears after refresh.

## Released fix

- Feature commit `27bd096c848deca36f9ce0a79e756f6bc348e038`, pushed to main and the isolated task branch.
- Existing primary `sports-cave-os`, `srv-d8kl4on7f7vs73dvavv0`: initial release/acceptance deployment `dep-dbdsrh5g1s2s73avn64g`; final accepted-configuration deployment `dep-dbdtatjncjis73ded9f0`, live 2026-10-23 21:48:20.265924 UTC.
- Existing worker: `dep-dbdsre6q1p3s73f27beg`; existing webhook service: `dep-dbdsre6q1p3s73f27b5g`, both live on the feature commit. No new service, Blueprint, schema or resource allocation was created.
- Auto Editions Companion installed from immutable `approved-27bd096c848deca36f9ce0a79e756f6bc348e038`. The existing startup task action was updated; XML comparison confirms its identity, triggers, settings and principal were retained. Pairing, source cache, original failed journals and transfer preferences were preserved. The separate screen task recorder was not updated by this release.
- Installed file hashes were independently checked. Fresh Companion/worker heartbeats both reported `27bd096c`.

The shared detector accepts a positive numeric suffix on the specific known plaque asset basename, while retaining exact layer identity, uniqueness, containment and all existing font, edition-total, colour and readiness checks. Future valid manual attachments already save and queue atomically; the corrected shared detector is used when their available Companion claims them. Products registered before their PSD retain durable waiting discovery; PSD-before-product and duplicate delivery cases are covered by focused tests. No bulk backlog recovery was enabled.

This is automatic processing of supported inputs, not a promise that corrupt/ambiguous PSDs, missing fonts, unavailable Photoshop or provider outages cannot fail. Such conditions must retain recoverable work and actionable evidence; successful completion and production readiness cannot be fabricated.

## Native acceptance and scoped activation

Generation: `d5e8adaf0f0ed3f7008b3b0326b3bdb60b07c66aa0683e1e045de97fbdd20597`.
Isolated run: `24c9eecf52994a5aa2d9681dd4b43d6d`.
Durable session: `dfdc1db8f4a7e086d1d1bb82d53bb3f891d90139abe224576813f95180646b90`.

The installed Companion transferred the bounded 277,954,087-byte synthetic large-v2 package through the actual Render/native PostgreSQL/Dropbox path. Package SHA-256: `49a2c314bff4c991f725993d1c1ad47be606a1a85a68d9d6c8fc50509e2d0006`. The large preamble tests transfer volume; it does not claim full-size artwork compression or pixel memory acceptance.

- Concurrent create requests returned the same session.
- The first 8,388,608 bytes were committed before a deliberate lost acknowledgement. A normal Companion stop/start resumed that same session, without resending the accepted first chunk.
- Lost finalization acknowledgement recovered through the existing durable journal.
- A deliberate retryable interruption after master publication reused the exact master file ID/revision. Final publication uploaded 100 remaining assets and reused the master.
- The backend independently downloaded and verified all 101 assets (2,410,495 bytes), with three proofs, before recording isolated Cloud Ready.
- Retention cleanup expired one separate test session while preserving the active completed main package.
- Highest available 60-second memory sample: 620,929,000 bytes against unchanged 2,147,483,600-byte service limit. These samples are not instantaneous peak measurements.
- Balanced settings remained 3.8 Mbps sustainable, 25% headroom, effective 2.85 Mbps, unpaused. No upload mode/bandwidth preference was changed for the test.

Reviewed acceptance evidence SHA-256: `aa3d92edc3360550837a03644f4e5d171e9b194174d6603f5a7c6b44e0a0df15`. Full evidence and sampled metrics are retained in task runtime `C:/Dev/SportsCaveWorktrees/.studio/runtime/20261023-7a07f6a2` (`reviewed-acceptance.json`, `acceptance-final.json`, `native-concurrent-create.json`, `acceptance-memory-samples.json`).

Only primary-service resumable acceptance keys were merged: uploads enabled, `provider-postgres-retention-large-v2`, the exact generation and reviewed evidence hash, and temporary `COMPANION_ACCEPTANCE_RUN` cleared. Its endpoint then returned HTTP 409, `Isolated acceptance is disabled.` Production readiness settings and existing package/image/disk bounds remain intact.

## Concurrent main update preserved

An unrelated recorder commit `ce0288da2049eac7e60fe614afd29de95322a906` reached main with `[skip render]` while acceptance ran. Render's environment update selected that latest commit. Its build `dep-dbdta78n74is73er4nrg` was cancelled at 21:44:30.962552 UTC before deployment. Activation was explicitly pinned to feature commit `27bd096c`. The specific-commit UI temporarily disabled auto-deploy; the original `On Commit` setting was restored and checked through the Render connector. No subsequent unrelated deployment was triggered by that restoration. Main and the other task's work were not reset, rewritten or discarded.

## Actual product recovery — blocked by Photoshop runtime

Tony's existing checkpoint was retried once through Worker Health with correction confirmation. Request UUID `d142f287-696c-451a-83ec-0d5fe61e2c46`, accepted 2026-10-23 21:49:11.290134 UTC. Exactly one queue-request audit was found. The Companion claimed it and negotiated protocol 1, a 1,073,741,824-byte limit and the accepted generation.

New local attempt: `0a685651407584030665b210cc52b6bd67b1020de5bfab31`. It stopped BEFORE numbered-asset generation at Photoshop inspection, not at the old plaque detector:

> Photoshop inspection failed: Inspector failure: Photoshop could not inspect the linked source.

The retained inspection gives native error 8000. A bounded read-only open diagnostic captured the exact message:

> Cannot open the file because the open options are incorrect

The original and new staged Tony PSD copies have identical SHA-256 `b2f41ae3c3cfbae00acfc14ab476956a1e47e5b8b7fa51ea8060d263a6bac7fa` and the expected Dropbox content hash. Photoshop's File API sees and reads the source. A tiny valid synthetic PNG, the original PSD staging path and a separate task-owned copy all fail scripted open with the same native error; explicit PSD format and forward-slash path also fail. An Action Manager probe did not create a new document and is not treated as a successful workaround. Application modal dialog/tool levels were both zero.

Photoshop 27.11.0 remains responsive but has three existing documents, two unsaved. They were preserved. No document was closed, saved over or restarted to get past this error. The owner has been asked to save their work and restart Photoshop normally before recovery continues. This is a new runtime blocker; these diagnostics do not prove its internal Photoshop cause or guarantee a restart resolves it.

Authoritative Tony status became `Blocked` at 21:50:43.961176 UTC; the live status UI shows Failed with the inspection error. Jaxon's checkpoint remains at its original `Needs PSD Repair`; it has not been blindly retried into a known-unavailable processor.

**Neither product is cloud synced.** Both still have no preparation hash, zero stored preparations and zero matching transfer sessions. The isolated acceptance receipts are not product receipts. No print/visual/supplier approval was created.

After confirming zero active preparations, the normal Worker Health Pause control was used to stop new preparation claims while Photoshop's file-open path is unavailable. Valid attachments continue to save into the durable queue; this avoids sending future products into the same known runtime failure. This is an audited operational preparation pause, not a readiness override or an unrelated service/configuration change. The original state was unpaused. Resume the same control only after the saved/restarted Photoshop passes the file-open check.

## Preservation and checks

Fresh Dropbox metadata confirmed both original revisions and file sizes. Comparison against the captured pre-retry baseline matched both mappings/timestamps, source identities, edition totals, active run IDs, next numbers, last-assigned values and sold counts exactly. Jaxon remains next edition 50 on run `34d693e6-0aa9-43bb-8657-c6cf5010786c`; Tony remains next edition 2 on run `d34c4b26-d4ba-461a-86ab-0a6f18d19244`. PSDs, old journals and completed unrelated work were retained.

Focused local runs: 85 Python checks and the complete picker browser regression from investigation; 56 Shopify registration/onboarding/acceptance checks during release; five additional discovery checks passed. These runs overlap and are not a count of unique tests. One optional native discovery concurrency test was skipped; nine optional legacy standalone PostgreSQL/snapshot cases were previously skipped. Native transfer concurrency/restart/provider/retention checks above actually ran; local mocked tests are not represented as live product success.

Runtime evidence includes `recovery-baseline.json`, `recovery-current-evidence.json`, `release-context.json`, preserved startup XML, the native open diagnostics and `tony-runtime-blocked.png`.

## Safe continuation after Photoshop is usable

1. Confirm Photoshop was saved/restarted safely; test that the synthetic PNG and a disposable staged source can open/close without touching existing documents. Do not kill unsaved work or turn off source/colour/readiness validation. Resume the existing audited preparation pause after this check passes.
2. Re-read each exact source revision/mapping and current queue/lease/hold/review state. Use the existing guarded Worker Health repair-confirmed retry on Tony's existing Blocked checkpoint with a new normal request UUID after correction. Retain the failed attempt; do not replay its expired grant.
3. Require actual Photoshop export, bounded package transfer, verified master plus 100 patches, cloud receipts and authoritative final technical state. Then submit the same normal workflow for Jaxon's existing checkpoint.
4. Recheck mapping/run/allocation preservation, receipt identities and all required proofs. Report the actual outcome. Cloud Ready remains separate from supplier/physical production readiness; no approval or success flag may be forced.
