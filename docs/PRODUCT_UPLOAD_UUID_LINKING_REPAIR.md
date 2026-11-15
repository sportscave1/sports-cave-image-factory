# PSD linking failure: confirmed UUID receipt error

## Verified context

Local task: C:/Dev/SportsCaveWorktrees/sports-cave-products-diagnose-psd-linking-service-failure-20261020-a5ecd572
Branch: codex/task/products-diagnose-psd-linking-service-failure-20261020-a5ecd572
Owner: codex-link-diagnostic-20261020
Clean task baseline and live app revision: 70e91502e395fed620dcc644066518ba8ae902a1. The clean PRODUCTS category entry checkout and task branch were verified before edits. Other worktrees were untouched.

## Production read-only evidence

Render deploy dep-dbbkvjmk1f9s73bvjmkg is live at the baseline revision. User confirmed Nathan's workspace for read-only logs. At 2026-10-20 11:39:23 UTC, operation 46f83a53-da95-4438-9e55-5c26ee4a6f54 failed in `Mapping.map -> _step -> _guard -> Intakes.locked -> json.dumps` with `TypeError: Object of type UUID is not JSON serializable`.

POST /api/product-uploads/map returned HTTP 200 when the background job was accepted; GET mapping-status returned HTTP 200 with the persisted Mapping failed state. There is no evidence of a failed HTTP endpoint or companion at this stage. A fresh read-only health probe returned 200 ok.

The authoritative database confirms product 15430466666803 has Edition Ops record 733, edition total 100, next number 1 and a consistent active UUID run. Both edition_runs.id and edition_products.active_edition_run_id are PostgreSQL uuid columns. Psycopg returns native UUID objects. Existing fixture runs were bigint, which concealed this defect.

The failed operation has only Finding product in Edition Ops completed, no persisted edition/run IDs, no move intent or moved receipt, and no authoritative PSD mapping. Its captured source metadata was validated before Linking PSD. The UUID exception happened before a move could be attempted.

An earlier operation (48fe3e9a-ceb0-4589-8585-95f05eaed54d) owns the existing preparation hold for this exact product/file. Read-only comparisons confirm the same account and identical source metadata, failed state, no live lease and no preparation job. The hold was not deleted, transferred or bypassed. After the code is deployed, the original attempt is the safe recovery path.

## Actual service path and repair

mapping.js submits map and polls mapping-status. product_upload_api submits the in-process sync-map job; Mapping reads the existing Edition Ops identity, persists its run, then uses the existing Dropbox adapter. The adapter uses the shared Files Dropbox context and files_move_v2 with autorename false. This mapping stage does not use a Windows companion. The existing configured source is Review under the Designs Live directory; it moves/renames the captured PSD file into Designs Live, not its parent folder.

Mapping now converts native UUID run IDs to their exact string representation at the database-to-receipt boundary. Final locked active-run comparison uses equivalent string values, so JSON text is not incorrectly compared with a native UUID. No run or edition values change.

For a different saved operation owned by the same account for the same product and file, the existing hold rejection offers Open original mapping attempt using the established upload-resume URL. It does not mutate the hold. Conflicts with another owner/product/file still fail closed. Unexpected application exceptions are distinguished from connection failures instead of always claiming service unavailability.

No lookup, webhook, ingestion, shared syncing, numbering, mockup or upload changes. Existing filename sanitising, move intent, exact file identity, conflict checks, link persistence and completion verification remain.

## Verification and limits

A local test with actual UUID database columns and a psycopg-shaped UUID result adapter reproduced the identical traceback before the fix. Provider writes are simulated. The regression tests exercise complete finalisation, repeated completed mapping, service outage and retry, lost move acknowledgement, link failure after move, and recovery through the original hold-owning operation. Final local verification: 53 mapping tests passed, along with JavaScript lifecycle/recovery checks and Studio verification.

Real evidence is Render logs, HTTP request status logs, current app health and read-only database schema/progress. Local success uses disposable PGlite PostgreSQL and mocked Dropbox, not a real production move. Live destination access/write permission and end-to-end finalisation remain unverified.

No service restart or credential/configuration correction is indicated by the observed exception. Initial implementation and verification were local only. The user subsequently authorised committing, pushing and deploying this patch to the existing sports-cave-os service. No production record changes or artwork moves are performed during release verification.
