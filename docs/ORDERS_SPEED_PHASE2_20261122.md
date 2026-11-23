# Orders speed — Phase 2, 22 November 2026

## Backend changes

- Polling claims already-ready merge/QA/upload/product work before running the initial preparation planner. If none is ready, it prepares once and claims again. Existing priority and sequential-item behaviour stay intact.
- Product selection, artwork claim/permit/readback, and dashboard QA now use short read transactions and an atomic final validation/commit. Supplier HTTP requests, original-JPG downloads and authoritative artwork checks run outside those transactions.
- The final commit takes the existing browser advisory lock, locks observed records with NOWAIT, rechecks all observed values and sibling membership, then atomically records all changes. Reset or competing claims discard stale results. Save/Select/shipping permission is returned only after commit.
- Group QA resolves each exact allocation once per verification phase. Siblings share the Fulfilment order lookup, variant mapping and original shipping mirror within that phase. Copies protect cached results; no cache crosses requests, independent supplier readbacks or the original-file download boundary.
- Submission preflight releases its candidate transaction before supplier/source reads. Before reserving its one-use submission intent, it rechecks the owner setting, leader, all siblings and complete group membership in a short transaction. Group reservation reuses those validated units without network work inside the transaction.
- Each whole-order submission preflight uses one supplier response for all item checks. The independent fresh pre-POST check remains. A two-item successful submission requires three supplier order reads: initial preflight, fresh pre-POST, and acknowledgement, instead of five plus repeated source resolution.
- Browser stages record planning_ms in backend preparation metadata. No technical controls were added to the Orders interface.

## Verification and limits

Offline fixtures only; live customer records were not copied into development and no submitted production order was reset or paid for to manufacture a test. Tests cover transaction lifetime during supplier reads/downloads, Reset during claim/permit/readback, grouped atomic failure, overlapping claims, owner pause during preflight, separate fresh readbacks, and one submission for all items.

The initial JPG/preparation planner and the separate-order merge coordinator retain their existing fencing in this release. This is the hot browser/QA/submission-path optimisation, not a replacement of every background transaction. Countdown preferences, mappings, QA criteria, tax policy, merge/cancellation safeguards and uncertain-write rules are unchanged. No companion reload is required because extension files and permissions are unchanged.

## Following phases

1. Durable arrival-to-companion wake-up with replay and fallback polling; the idle browser alarm can still take up to 30 seconds.
2. Incremental new-row feed to preserve table scroll, search and selection without a full Streamlit rerun.
3. Separately migrate the remaining initial-preparation/merge coordinator transactions to durable stage leases, with crash/replay tests before changing their write fencing.
