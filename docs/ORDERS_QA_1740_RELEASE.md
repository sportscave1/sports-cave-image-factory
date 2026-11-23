# Orders QA 1.7.40 release evidence

22 November 2026. Authorized task 20261121-66569b83. Previous server revision db57e934; installed package baseline 1.7.39. No supplier countdown/preferences or service topology changes.

## Implemented phases

1. Stability: wait for the exact item's quality badge and restored shipping selector; canonicalize the worker-owned order tab before fresh QA. Poor quality and wrong identity still fail verification.
2. Observability: paired, token-scoped stage reports stored separately from permit/workflow records; runtime version heartbeat; bounded stage histories, retry time and stale-wait labels in the existing review panel. Admin-only on-demand metrics provide backend stage p50/p95, status counts and ready age over at most 500 recent preparation records. Diagnostics contain no customer addresses, artwork URLs or raw tokens. Existing backend stage durations remain authoritative. This is diagnostic progress, not a new delivery acknowledgement protocol.
3. Readiness: shared MutationObserver helper with bounded deadline, cleanup and polling fallback. Immediately available controls incur no added sleep. Existing fit/persistence delays remain where no equivalent positive persisted signal exists.
4. Queue: prefer continuation of the active order; after the existing bounded chain, wake in 100 ms rather than waiting for fallback polling. One native writer remains mandatory. A review outcome yields the order so other ready work can continue. Failed transports do not start a tight retry loop.
5. Recovery: only allowlisted read/readback requests retry temporary transport/429/502/503/504 failures, with 1/2-second backoff inside one total deadline. Never replay Select, permit, Save, shipping writes, Submit or merge mutations automatically. Existing durable write-intent reconciliation remains intact.
6. Release discipline: repeatable local release-gate script, GitHub CI evidence upload, complete package dependency checks, scaling regressions and duplicate-delivery fault soak. CI does not itself change branch protection or Render deployment policy.

The flow stays variant → upload numbered artwork → exact-item QA → next item → shared order QA → one guarded submission. Certificate completion still requires production/payment evidence and successful customer-account upload.

## Validation

- Full combined gate: 228 Python checks and 90 Node checks passed; no skipped suites; canonical Render topology validator passed.
- Final metrics addition: 13 runtime checks passed (12 overlap the combined gate; one additional aggregate/privacy check). 229 distinct Python checks across these runs.
- Synthetic 1/2/5/10-item final-submission fixtures: three supplier reads, two source checks per item and one Submit per order. Local measured cost 16.74/31.85/37.17/50.63 ms. These are local final-worker timings, not live end-to-end latency or production percentiles.
- Synthetic queue soak: 1,000 jobs, duplicate wake bursts and 59 disconnects before claim; maximum native concurrency one, no duplicate executions. This does not simulate every lost-response or real supplier failure.
- Delayed controls, replaced rows, stale/reset tokens, uncertain writes, source/address validation, fragment reruns and package contents are covered by focused suites.

## Live acceptance and limits

Activation must report 1.7.40 from the paired desktop. At release preparation, allocations 965 and 968 had independently verified saved artworks but old QA wait failures. Guarded recovery may recheck them without reuploading. The single-item order is eligible for full acceptance; the multi-item order cannot submit until its other two genuine PSD edition-layer defects are repaired. Do not Reset paid/submitted orders or manufacture purchases to complete a canary. Separate-purchase merge acceptance still needs a genuine eligible pair.

The plan's under-five-second queue/UI targets, sub-500-ms readiness overhead and browser memory budget require representative production observation. They are targets, not measured release claims. Supplier outages, poor images, identity conflicts, invalid source layers and uncertain writes remain real review conditions. No implementation can promise universal success.

## Rollback

Retain the 1.7.39 installed-file backup and db57e934 baseline. If necessary, deploy a reviewed revert of this release and restore only the changed extension files, then reload. Do not delete durable preparation receipts, Reset successful orders, erase merge/write intents or alter Prodigi countdowns. Telemetry records are separate and can be ignored safely by the previous workflow.
