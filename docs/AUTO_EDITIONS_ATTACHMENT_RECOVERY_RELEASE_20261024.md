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

## Initial product recovery — Photoshop runtime blocker

Tony's existing checkpoint was retried once through Worker Health with correction confirmation. Request UUID `d142f287-696c-451a-83ec-0d5fe61e2c46`, accepted 2026-10-23 21:49:11.290134 UTC. Exactly one queue-request audit was found. The Companion claimed it and negotiated protocol 1, a 1,073,741,824-byte limit and the accepted generation.

New local attempt: `0a685651407584030665b210cc52b6bd67b1020de5bfab31`. It stopped BEFORE numbered-asset generation at Photoshop inspection, not at the old plaque detector:

> Photoshop inspection failed: Inspector failure: Photoshop could not inspect the linked source.

The retained inspection gives native error 8000. A bounded read-only open diagnostic captured the exact message:

> Cannot open the file because the open options are incorrect

The original and new staged Tony PSD copies have identical SHA-256 `b2f41ae3c3cfbae00acfc14ab476956a1e47e5b8b7fa51ea8060d263a6bac7fa` and the expected Dropbox content hash. Photoshop's File API sees and reads the source. A tiny valid synthetic PNG, the original PSD staging path and a separate task-owned copy all fail scripted open with the same native error; explicit PSD format and forward-slash path also fail. An Action Manager probe did not create a new document and is not treated as a successful workaround. Application modal dialog/tool levels were both zero.

Photoshop 27.11.0 remains responsive but has three existing documents, two unsaved. They were preserved. No document was closed, saved over or restarted to get past this error. The owner has been asked to save their work and restart Photoshop normally before recovery continues. This is a new runtime blocker; these diagnostics do not prove its internal Photoshop cause or guarantee a restart resolves it.

Authoritative Tony status became `Blocked` at 21:50:43.961176 UTC; the live status UI shows Failed with the inspection error. Jaxon's checkpoint remains at its original `Needs PSD Repair`; it has not been blindly retried into a known-unavailable processor.

At this initial checkpoint, **neither product was cloud synced**: both had no preparation hash, zero stored preparations and zero matching transfer sessions. The isolated acceptance receipts were not product receipts. No print/visual/supplier approval was created. The subsequent actual recovery is recorded below.

After confirming zero active preparations, the normal Worker Health Pause control was used to stop new preparation claims while Photoshop's file-open path is unavailable. Valid attachments continue to save into the durable queue; this avoids sending future products into the same known runtime failure. This is an audited operational preparation pause, not a readiness override or an unrelated service/configuration change. The original state was unpaused. Resume the same control only after the saved/restarted Photoshop passes the file-open check.

## Preservation and checks

Fresh Dropbox metadata confirmed both original revisions and file sizes. Comparison against the captured pre-retry baseline matched both mappings/timestamps, source identities, edition totals, active run IDs, next numbers, last-assigned values and sold counts exactly. Jaxon remains next edition 50 on run `34d693e6-0aa9-43bb-8657-c6cf5010786c`; Tony remains next edition 2 on run `d34c4b26-d4ba-461a-86ab-0a6f18d19244`. PSDs, old journals and completed unrelated work were retained.

Focused local runs: 85 Python checks and the complete picker browser regression from investigation; 56 Shopify registration/onboarding/acceptance checks during release; five additional discovery checks passed. These runs overlap and are not a count of unique tests. One optional native discovery concurrency test was skipped; nine optional legacy standalone PostgreSQL/snapshot cases were previously skipped. Native transfer concurrency/restart/provider/retention checks above actually ran; local mocked tests are not represented as live product success.

Runtime evidence includes `recovery-baseline.json`, `recovery-current-evidence.json`, `release-context.json`, preserved startup XML, the native open diagnostics and `tony-runtime-blocked.png`.

## Recovery procedure

1. Confirm Photoshop was saved/restarted safely; test that the synthetic PNG and a disposable staged source can open/close without touching existing documents. Do not kill unsaved work or turn off source/colour/readiness validation. Resume the existing audited preparation pause after this check passes.
2. Re-read each exact source revision/mapping and current queue/lease/hold/review state. Use the existing guarded Worker Health repair-confirmed retry on Tony's existing Blocked checkpoint with a new normal request UUID after correction. Retain the failed attempt; do not replay its expired grant.
3. Require actual Photoshop export, bounded package transfer, verified master plus 100 patches, cloud receipts and authoritative final technical state. Then submit the same normal workflow for Jaxon's existing checkpoint.
4. Recheck mapping/run/allocation preservation, receipt identities and all required proofs. Report the actual outcome. Cloud Ready remains separate from supplier/physical production readiness; no approval or success flag may be forced.

## Actual recovery after the owner cleared Photoshop

After the owner's confirmation, the same domain automation connection observed zero open documents. The disposable 16-pixel PNG and both staged PSDs opened and closed successfully without saving. Both PSDs remained 2835 × 2004. The earlier runtime error was no longer reproducible; its internal Photoshop cause remains undetermined. No runtime workaround or validation relaxation was added.

The normal Worker Health Resume control restored preparation claims. Tony's new guarded retry request `8640f205-d843-433a-b87f-f824fe00e63c` was accepted at 2026-10-23 23:06:14.786555 UTC and claimed at 23:06:54.278213 UTC. Local attempt `6f37b52af6a415dd203fc0a3627f0bba35d83d31b8654ec4` used the verified source cache and accepted generation.

Tony's lossless package was 138,499,770 bytes, with 106 ZIP_STORED entries (already compressed PNGs plus manifest/proofs), transferred in 17 bounded bulk requests. Durable session `abe9676b0d6c94590a58812bbfbc2f669d55c371beb54937a0ad371cc344a1ba` acknowledged every byte. The server recorded **Cloud Ready at 2026-10-23 23:22:30.876342 UTC**, preparation `03bd2c0063b9f7e663fcf623238c6cef14f6bccdc360b0e1166d73827e698b01`.

Actual Tony receipts contain 101 unique names and file IDs, all with revision and positive byte size, totalling 53,305,841 bytes: one master plus number patches 1–100. Three proofs match the final preparation hash (pixel-exact editions 1/100 and exact pixels outside the number). The independent technical job is `Succeeded`, reason `Required technical checks and immutable cloud receipts verified.` Fresh Dropbox metadata for master, number 1 and number 100 independently matched all three stored IDs/revisions/sizes. The live status page also showed Cloud Ready; evidence is retained as `tony-cloud-evidence.json` and `tony-cloud-ready.png` in the task runtime.

Jaxon's guarded request `cf70f554-7650-4756-804d-8ed5d1ddbfa0` was accepted at 2026-10-23 23:23:09.241881 UTC and claimed at 23:23:49.916757 UTC. Local attempt `c6e093caa0921c78ad1b338cdb465ee6bda0cc53c9e99fbd` passed inspection and generated a 72,841,825-byte package. Durable session `38adea3adbf4242f4c75b163e9deb124fd88bf148ee3a1e5011157661f55ee3c` acknowledged every byte. The backend recorded **Cloud Ready at 2026-10-23 23:34:19.677932 UTC**, preparation `fa2dca78ecf2ef2921af2a7d30f5f99553eee3ef57247a654392855d7f8cbd1b`. Its 101 unique asset receipts total 29,288,770 bytes, all have IDs/revisions/positive sizes, all three proofs match that final hash, and its technical job is `Succeeded`. Fresh Dropbox metadata independently matches the master and first/last patches. Evidence is retained as `jaxon-cloud-evidence.json` and the live result screenshot.

Both exports retain the existing scale-4 layered Photoshop preparation, 11340 × 8016 output, exact source ICC and all colour/pixel/role checks. Their manifests retain `print_ready=false`, `supplier_verified=false`, and `quality_approval_required=true`. The automatic technical certificate is TEST-only and does not create a human visual, supplier or production approval.

### Completion acknowledgement follow-up

Jaxon's server verification completed successfully before a Companion upload-status poll finished. That poll hit the old preparation-lease fence and received HTTP 409. The Companion failure handler then reconnected and obtained the completed receipt, but ignored that return value and attempted to report failure using the superseded grant. This left a false local Blocked/checkpoint-pending warning while the authoritative product and cloud receipts were already verified. No second product retry was submitted.

Commit `fb782edaa37824da5b4d7c8cc8e8a988eccda019` makes the failure handler finish from that authenticated same-source completion receipt, clears the stale error, and ensures retained recovery reconciles an existing in-memory job instead of leaving its old pending flag behind. It does not broaden receipt, source, lease or readiness authority. Three focused regressions exercise completed-acknowledgement recovery without reupload/failure reporting, rejection of changed-source completion, and repeat/restart reconciliation of the same retained live row. All 53 selected preparation-host, native-v19 and preflight checks passed, including after integration; topology validation passed.

Another task released footer commit `1cd4132e7a130ebf188b0e479662209ac3369b0d` while product recovery ran. Release `131d0fa6d9bffa2d9ce63c14048c42355071e6f1` preserves that already-live application exactly and adds only the Companion follow-up and its tests/documentation. It excludes the unrelated recorder commit retained on main. The final primary deploy `dep-dbdv1fvavr4c739h16c0` became live at 2026-10-23 23:44:49.788297 UTC; the matching existing worker deploy `dep-dbdv27ss728c738k8i80` became live at 23:44:58.199911 UTC. No new service, readiness setting or resumable-acceptance setting was changed for this acknowledgement-only follow-up. Preparation generation remains the previously accepted `d5e8adaf0f0ed3f7008b3b0326b3bdb60b07c66aa0683e1e045de97fbdd20597`.

The immutable installed Companion now uses `approved-131d0fa6d9bffa2d9ce63c14048c42355071e6f1`, with checked file hashes. Its existing scheduled-task identity/triggers/settings/principal were compared before/after and preserved; only the action's release path changed. The old worker rejected normal Close because of its stale pending flag. After confirming both cloud completions, zero active preparations and no Photoshop processor lock, claims were briefly paused and only the positively identified idle old Companion worker processes were stopped for handover. Photoshop and the separate recorder were not stopped. The new Companion resumed the retained Jaxon journal through normal authenticated reconnect, recording `Prepared`, empty error and `checkpoint_pending=false`, without regeneration, upload or production requeue. The server remains authoritative for Cloud Ready; retained local diagnostics can still say Uploaded, verifying and the source/package remain available rather than being deleted on that intermediate receipt. Claims were resumed after handover.

Final baseline comparison matches both source revisions, mappings/timestamps, edition totals, active runs, next numbers, last-assigned and sold counts. Tony remains next 2; Jaxon remains next 50. Each has exactly one preparation and one durable transfer session. This successful recovery cycle has exactly one guarded queue request, claim and technical-cloud-ready audit per product. Original failed attempts are retained. The final preservation and queue evidence are saved in the task runtime.

### Production readiness still requires evidence

The released `data/auto_editions_production_standards.json` remains empty. `auto_editions_quality.assess` therefore has no exact owner-approved artwork/supplier standard for either immutable preparation. Cloud Ready is the correct technical next state, not Production Ready.

Before production certification, the existing workflow requires exact variant IDs and supplier SKU; verified full canvas dimensions/ratio, bleed, safe margins, ICC and native source PPI; and an identified owner's visual approval of the exact artwork, plaque and complete numbered range, tied to the exact source revision and final preparation hash. The reviewed standard also specifies full-quality RGB JPEG output, 300-DPI metadata and exact ICC. A 300-DPI tag or scale-4 enlargement cannot satisfy the native-resolution check by itself. The only retained A1 supplier evidence is explicitly incomplete (unknown bleed/margins/ICC and no quality approval); it is not applied to these products by assumption. No production flag, supplier record, customer allocation or fulfilment action was changed.
