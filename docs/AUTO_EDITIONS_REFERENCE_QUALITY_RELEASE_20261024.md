# Auto Editions reference quality release — 24 October 2026

The owner authorised commit, push, Render deployment, Auto Editions Companion update, acceptance and a targeted For Brock replacement. No other product was regenerated.

## Released revision
Feature commit: 0bfd4c826ee9aab8d4f3b98114254cede90c1dd4.
Initial sizing release: 6358fcf1fa9d34ba55c4d2752706c92c508c7aa6 (documentation whitespace follow-up only).
Final deployed application/worker/Companion revision: 51fca93820256018147a5cd9c99883bfcd7606e9, adding only the verified replacement handoff and its tests to that release. It excludes the unrelated recorder commits preserved on main.
Main integration: 3ded241b (preserves the previous remote main's recorder commits; those unrelated commits are excluded from this pinned deployment).
Primary: existing sports-cave-os, srv-d8kl4on7f7vs73dvavv0.
Worker: existing sports-cave-seo-worker, srv-d9ujm9navr4c73amurgg.
Worker deployment dep-dbe3j1bncjis73e1ram0 became live 04:53:41.588672 UTC.
Final accepted-config primary deployment dep-dbe485om7kps73c9dl20 became live 05:40:19.664304 UTC.
Final handoff primary deployment dep-dbe538t9fdbs739bmdug became live 06:38:11.434709 UTC; worker dep-dbe53959fdbs739bmga0 became live 06:36:45.926701 UTC. Main also contains the follow-up as 1fd7ccb9b546128375362f6f749283175cd90a1b.
No service, Blueprint, schema, compute plan, image/transfer limit, print-readiness policy or recorder release was changed. The original On Commit deploy preferences were restored after specific-commit deployment.

The final immutable installed Companion is approved-51fca93820256018147a5cd9c99883bfcd7606e9. Source came from that exact Git archive; eight critical file hashes were independently checked. Existing scheduled task identity, principal, triggers and settings match its before/after XML; only its executable action's release path changed. Pairing, journals, source caches and Balanced transfer settings were retained. Fresh Render/Companion heartbeats reported the release revision.

## Shared sizing fix
See AUTO_EDITIONS_REFERENCE_QUALITY_20261024.md for the original diagnosis and local changes.
For Brock's 2362 × 1670 PSD historically used a fixed 4× resize, producing 9448 × 6680. Kostecki & Hazelwood's larger 2835 × 2004 PSD reached 11340 × 8016 under the same multiplier.
The versioned policy now uses that owner-selected raster floor for supported mapped framed sizes, preserves aspect ratio and the unchanged 95 MP bound, and discloses its provenance without claiming supplier Excellent certification or native-detail approval. Cached product variants supply the target even before the first order. Legacy archives remain valid and unchanged; incompatible smaller preparation caches are not reused for fresh work.

## Release checks
Exact isolated release: 123 focused Python checks passed in 75.30 seconds, with two dependency deprecation warnings. Tests include PostgreSQL/PGlite context and queue checks, products without orders, cache/history compatibility, fractional rounding, ICC/pixel/encoder protections, transfer boundaries and interrupted localhost HTTP recovery. Render topology validation and Studio static checks passed.
These local checks are distinct from the live acceptance and native preparation below.
The confirmed handoff repair passed 50 technical checks and 61 reset/clear checks. Two old reset fixtures lacked the commerce metadata tables used by preparation; those fixtures were brought into line with production, without changing production schema or weakening assertions. Added cases protect allocation allowlists, visual/production approvals, variant scope, corrupt assets, changed historical source/evidence, mismatched owner requests and retained generations; successful repeats remain idempotent.

## Actual installed-Companion acceptance
Generation: c56c264a345e173dd256106c7d73ae216036a8446aa864cc0acd8cd5176afb56.
Run: 9719785731e44bde8b05ad57c350581d.
Session: c9ef320d668fad842c43ed099f955f8d57dfdbb2809dd9a43207b59bf70a2e9a.
Package: 277,954,087 bytes, beyond the 256 MiB legacy boundary. This synthetic transfer fixture is not a full-size artwork memory benchmark.
- Two concurrent create requests returned the same session.
- The server committed 8,388,608 bytes before a deliberate lost acknowledgement. Normal Companion stop/start resumed the same session from that committed position.
- Lost finalization acknowledgement recovered from the durable upload journal.
- Deliberate retry after master publication reused that exact cloud file ID/revision; final publication reused one asset and uploaded 100.
- The backend independently downloaded and verified all 101 assets (2,410,495 bytes), with three proofs, before isolated Cloud Ready.
- Cleanup expired one separate test session while preserving the completed main package.
- Highest available 60-second Render memory sample during acceptance was 387,481,600 bytes versus the unchanged 2,147,483,600-byte limit. This is not an instantaneous peak measurement.
Reviewed evidence SHA256: dc8358ec007741724d6472c48814be5af852b2da42f8f965bed19f309f2c0335.
Only the required primary acceptance-generation/evidence bindings were updated. Existing provider-postgres-retention-large-v2 and uploads-enabled settings were retained. COMPANION_ACCEPTANCE_RUN was cleared after acceptance; its endpoint returned HTTP 409, Isolated acceptance is disabled. The live guarded recovery request asserted protocol 1, a 1 GiB negotiated limit and the exact matching generation before queuing.
Evidence is retained outside Git in .studio/runtime/20261024-a085057b, including acceptance-final.json, native-concurrent-create.json, reviewed-acceptance.json and Companion task XML.
The server-only handoff follow-up leaves all generation inputs and client transfer code unchanged; its installed and deployed generation is still c56c264a..., so the completed large-v2 acceptance binding remains valid. No acceptance result was fabricated or replaced with mock evidence.

## For Brock targeted native replacement
Product 394; gid://shopify/Product/10254227865907; file id:u1tYiAa2O-AAAAAAAAAA9Q.
Unchanged PSD revision 016572fe73a7c92000000036d367e13; 51,998,216 bytes; Dropbox content hash 5f1e6b90bd33a6a3cebaa3ad0a20299349ef212b0d89236997d205ca79d8694c.
Baseline: next 9, last assigned 8, sold 8, total 100, active run 11dfaa12-261f-40b3-af86-8c43804608fc; mapping timestamp 2026-10-12 21:27:40.519910 UTC.
The old preparation 3615e0dd7038aed390c245e6c718a0b20a2c2006364563845e96a21ecfcdac44 and its 101 receipts remain retained.
Request 2104e969-3bc7-4b48-a537-9850b97d4960 used the existing Reset.request replacement service, without clearing its mapping or edition run. Repeating that same request returned the same Discovering operation.
First local attempt 72b1467c4d20f053ac6835f5d6f35586b6b149686a99eb6f stopped before export with Photoshop error 8000. A tiny valid PNG failed with the same open-options error; this was not evidence of a damaged For Brock PSD.
Photoshop's only open document was saved. It was exited normally and restarted; the saved Barry document was restored. Tiny PNG opens passed both before and after that restoration. No document was saved over or discarded. The Companion was stopped normally for this restart and resumed on the same release.
The normal guarded Worker Health retry resumed the same replacement; it did not create another replacement request.
Second local attempt: d9b8708116f17c5a205a640a21ef003f4debf80e8e0637db.
Native inspection, colour and preflight passed. Actual generated master and original: 11340 × 8018, preserving the source aspect ratio; all 100 number patches generated. Manifest records target_met, source_modified=false and the reference policy provenance. Package size 167,341,055 bytes.
A local Photoshop RSS sample during export was about 8.90 GB, with about 5.92 GB available on the 34.24 GB machine. This is separate from Render's memory limit and is not an instantaneous peak benchmark.

## Confirmed replacement handoff defect and repair
The package uploaded completely and imported with 101 real cloud receipts, but technical completion correctly refused the old wildcard layout still pointing to preparation 3615e0dd...: "Conflicting retained layout. Use explicit reset/repair; no layout was replaced."
The shared technical commit now permits a handoff only for a completed, audited owner request bound to the new package's reset request ID, the exact previous preparation, unchanged PSD source and edition total. The prior layout must be the sole unrestricted wildcard automatic technical TEST layout, with its intact current certificate and proof/receipt evidence hash. Its complete former approval is retained in append-only history before the atomic update. Restricted variants, allocation allowlists, visual approvals, production approvals, stale source/evidence and unrelated layouts remain blocked for explicit review. All normal fresh cloud-byte, ICC, source, proof and commit fences still run first.
Only auto_editions_technical.py and focused technical/reset tests were added to the isolated follow-up. No preparation image, pixel algorithm, transfer protocol or readiness certificate format changed.
The UI's conservative retry guard still held the retained native lease. After checking a fresh matching Companion Idle heartbeat with no processor lock/checkpoint and an acknowledged completed import for its original actor/lease, the operator invoked the existing Technical.retry service. The native token/expiry were asserted unchanged. No readiness flag or layout was changed manually; the technical worker performed the complete verification and guarded handoff.

## Actual final result — 24 October, 17:47:13 Sydney
New preparation d552549166d4931cae248e70bf893a1794c7b9463497eae0bd712a1179b6adc0 is Cloud Ready; matching technical check Succeeded at 2026-10-24 06:47:13.340025 UTC.
Verified 101 receipts with 101 distinct names and cloud file IDs, all with revisions and positive sizes; three proofs; one current automatic TEST layout for the new hash; and exactly one retained-layout supersession history event for the owner request.
Actual output is 11340 × 8018 (90,924,120 pixels), matching the reference floor proportionally. Source PSD hash/revision and embedded ICC SHA256 3f6d674174f3804eb0dabdac90ae17486e898c5063a66f861c116ea033da8301 are preserved; source_modified=false, pixels_converted=false. The native source-background proof records exact native pixels and opaque original/master.
Final comparison matched the full allocation/run/mapping baseline: total 100, next 9, last assigned 8, sold 8, same active run and same mapping timestamp/file ID. All 101 previous preparation receipts remain retained. The existing edition-8 download job remains Ready; no customer order artwork was regenerated or allocation advanced.
Largest available 60-second Render memory sample across native preparation/import/verification was 1,239,396,400 bytes versus the unchanged 2,147,483,600-byte limit. This is not an instantaneous peak claim.
Cloud Ready permits TEST downloads. No supplier Excellent rating, visual approval, physical proof or Production Ready certificate was created. Existing production-readiness requirements remain enforced; the pixel floor does not create native detail missing from the PSD.
Final evidence: .studio/runtime/20261024-a085057b/for-brock-final-evidence.json, for-brock-native-evidence.json and for-brock-memory-samples.json. The guarded operator requests are retained there for review.
