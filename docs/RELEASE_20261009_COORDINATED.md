# Coordinated Sports Cave OS release — 9 October 2026

## Scope and provenance

Production and GitHub main were both `87b0ea5` at the start. Email Performance V5,
customer-like Send Test and Discount Editor V2 were already deployed. This release
adds the completed local code-only discount, Creative Refresh draft/recovery and
stability repairs, and merges the completed premium image work through `803fa25`.
Existing commits remain in history. No topology, dependency or migration changes
are included relative to the previously live revision.

The premium image work explicitly requires manual review of uploaded refreshed
images before POST NOW. Draft Save remains available; empty saved drafts may
enter Posting to add images, where Create Ad retains its validation. Optional
historical execution JSON is not a Save requirement. The merge retains the newer
snapshot-write failure handling and dynamic Carousel card ordering/counts.

Discount code remains mandatory in offer HTML; value is optional when no numerical
claim is made. Association, conflict checks, authoritative value validation and
send-time holds remain separate from editable presentation. Invalid presentation
shows a useful error instead of reusing the previous successful preview. No live
draft, publication, journey, discount or enabled state is modified by this release.

## Validation

- 892 project Python files compiled; Git whitespace and Render topology checks.
- Image/Ads/Meta/premium compatibility run: 1,468 tests, eight existing optional
  environment skips. The sole merge-test setup inconsistency was corrected with
  explicit assertions for both state transitions; 76 merge-affected tests then
  passed, including that entire suite. No assertion was disabled.
- Three Refresh stability unit tests passed; earlier local Refresh regression
  covered 390 tests before reconciliation.
- Discount/CRM/Send Test/publication/recovery/preview run: 132 tests, one existing
  failure in `test_automation_only_polling_and_debounce`, reproduced using
  `87b0ea5` source. It expects an obsolete literal in unchanged `crm_section_ui.py`.
- Discount, disposable Campaign-save benchmark and Edition Ops safety run: 73
  tests passed. All provider transports were mocked/blocked.
- Discount browser: code-only editing, useful invalid-HTML error, correction,
  stable association, movement, hide/restore/removal and desktop/mobile passed.
- Creative Refresh browser: Carousel/IE import, upload, clipboard, Save/POST NOW
  and four responsive widths passed. Empty four-card draft -> real Posting ->
  refresh -> return passed at desktop and narrow widths with Create Ad disabled.
- Chrome/Edge stress: 360 card actions, 126 handoff replays, background polling,
  archive outage/recovery passed across four/five/six-card fixtures.
- JavaScript session recovery and both clipboard contracts passed.

An earlier legacy section-persistence suite also has a known baseline assertion
expecting no native header/footer sections. This release does not claim the whole
repository suite is green. SQL-specific Meta job tests remain among the optional
skips; mocked posting/idempotency tests run without creating Meta objects.

## Measured local performance

Four archived cards across 20 outage rerenders: 80 -> 4 archive reads; local CPU
wall time 13.192 -> 4.950 ms. No network latency was simulated. Disposable Campaign
save (24 samples): unchanged p50 0.008 ms with zero writes; modified p50 29.588 ms,
p95 71.831 ms. Discount selector opens in 224 ms; initial mocked Shopify results
1,352 ms, search 1,522 ms. These are fixture measurements, not production latency.

## Deployment boundaries

Use existing GitHub-main auto-deploy for primary `sports-cave-os`, webhooks,
`sports-cave-seo-worker` (supervises both CRM and SEO) and SEO daily cron. Do not
create services or trigger the cron manually. The suspended historical duplicate
is excluded. No new migration or Shopify permission step is required.

Temporary evidence, local databases, screenshots, nested review checkout gitlink
changes, caches and credentials are deliberately excluded and retained locally.
Do not publish Email 3 or send a live test as a deployment check. Authenticated
production editor and actual Email 3/MYCAVE5 state require a read-only authenticated
session; fixture tests do not prove those current production values.
