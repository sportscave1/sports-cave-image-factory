# Auto Editions Phase 1 — 22 November 2026

Phase 1 implements the recovery and JPG-handoff fixes described in
AUTO_EDITIONS_UPLOAD_LATENCY_20261122.md, together with the requested usage-panel
readability correction. User authorised execution of Phase 1, including its
planned release, in the follow-up request.

- Explicit light label/help text and contrasting form fields/buttons override
  inherited page styles. Empty values explain Uncapped, Not used and Not set;
  existing values and Maximum speed remain unchanged.
- Transient requests/urllib failures retain packages for bounded recovery.
  Authentication, identity, cancellation and disk failures stay guarded.
- Due Cloud Ready preparations take precedence over older passive repair monitors
  so existing eligible order-JPG reconciliation can run promptly.
- Server import reports Validating and Publishing on the exact current lease.
  These display writes cannot extend or resurrect a completed/superseded lease;
  failure to report progress does not fail the import. Upload heartbeats preserve
  these server stages. Technical verification and pending/generating order JPGs
  have distinct labels. Preparation ready does not imply order JPGs complete.
- Status popup reports the last successful status-read time and explicitly marks
  delayed reads as last known state. Existing polling cadence is unchanged.

Validation: 132 focused tests passed across real Edge UI, header/status payload,
synthetic PostgreSQL queue/repair contracts, preparation-host recovery, package
completion, transfer preservation and top bar. Includes inherited black-on-black
CSS, empty-field meaning, unsaved edits, duplicate clicks, transient/permanent
failures, 60 older passive repairs, stage-heartbeat races and superseded leases.
Render topology validator passed. No artwork pixels, profiles or transfer mode
were changed. Resumable protocol activation and publishing optimisation belong
to later phases.
