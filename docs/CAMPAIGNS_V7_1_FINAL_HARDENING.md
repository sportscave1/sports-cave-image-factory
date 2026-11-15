# Campaigns V7.1 final hardening — local verification

**Implemented locally. Not committed, pushed or deployed.**

This pass used synthetic recipients and a newly initialized, loopback-only PostgreSQL cluster. It did not read or modify production records, call Shopify/Resend, send real emails, or change Render topology. Existing V7/V8 work was retained. Production readiness is not declared; the limitations below are release gates, not passing checks.

## Findings and changes

1. **Detail interactions unnecessarily rerendered the enclosing page.** The operational view now runs as one Streamlit fragment. Header actions and status share one progress result instead of entering a nested status fragment and independently requesting the same cached projection. Polling also refreshes action availability. A failed status read disables timing actions rather than failing the page. The normal view performs one bounded progress query; it does not load a template, recipient snapshot, analytics, or dialog context.
2. **Dialog widget reruns refetched their opening context.** Opening revision and draft timing are now retained for that dialog opening. Reopening clears the context. Saving still calls the transactional backend with the original expected revision; caching does not bypass stale-edit rejection. The display uses the existing short-lived progress cache.
3. **Fixed-time schedule amendments repeated timezone parsing/conversion for every recipient.** The fixed instant and market validation are now computed once per transaction. Original frozen timing, recipient identities, payloads and tracking keys are unchanged.
4. **The countdown reformatted the unchanged local timestamp every second.** A cached formatter and per-node timestamp guard eliminate those repeated formatting calls and DOM writes. Countdown anchors reset if a retained node receives a new server timestamp. The monotonic/server-clock countdown, visibility behavior and zero-network tick remain intact.
5. **Mobile Home overflow was hidden from document-width checks.** The global mobile column rule imposed a 168px minimum on the action column. At 320px, the main scrolling region was 369px wide even though the document reported 320px. Scoped column rules now retain the 76px action column without overflow. An invalid `calc(100vw -24px)` expression was corrected. Mobile KPI padding, icons and line heights were reduced without removing metrics or controls.
6. **Strict timezone evidence was incomplete.** New recipient-local validation no longer accepts customer-level country as address provenance. Conflicting populated country/state fields reject. Australian postcode/state contradictions, malformed or missing postcodes, and listed ambiguous/border regions reject. Valid NT/0800/Australia-Darwin evidence passes. The legacy resolver remains unchanged so historical schedules are not silently reinterpreted.

The older report's full AppTest benchmark included rereading/parsing the large `app.py` source and reconstructing the sidebar on every sample. Profiling the campaign function alone measured approximately 9ms for the copied V7 view and 8ms for the pre-hardening V7.1 view. Consequently the old 326/370ms comparison does **not** isolate a database or detail-function regression. Confirmed costs above were removed, but the exact cause of any production latency change cannot be established from a synthetic fixture.

## Performance evidence

Forty measured warm samples per phase, after four warmup rounds, alternate phase order under identical synthetic conditions. All phases use the same 1,085-recipient aggregate, shared backend infrastructure, and Streamlit version. The isolated comparison omits the artificial sidebar-source parser for every phase. It is server-render evidence, not real database or production/browser latency.

| Isolated detail render | p50 ms | p95 ms |
|---|---:|---:|
| Copied V7 baseline | 17.60 | 20.74 |
| V7.1 before hardening | 18.02 | 21.54 |
| Hardened detail | 14.99 | 19.74 |

The hardened render is about 16.8% faster at p50 and 8.4% at p95 than the pre-hardening view. Raw values: `campaign-hardening-evidence/render.json`. Baseline copies are in `tmp/campaign-hardening-before`; the older V7 copies remain in `tmp/campaign-v7-1-baseline`. Shared helper imports mean this is a presentation comparison, not two complete deployed application builds.

Final browser initial-load measurements used the restarted final-source fixture, no concurrent regression workload, the same 1440×900 viewport, two warmup rounds and 20 measured navigations per phase/browser. Phase order alternated. Timing ends when both Email preview and the scheduled countdown are mounted. The fixture includes the same sidebar reconstruction in both phases.

| Browser initial load | Before p50 / p95 ms | After p50 / p95 ms |
|---|---:|---:|
| Chrome | 2,982.43 / 3,505.74 | 2,979.85 / 3,507.25 |
| Edge | 3,124.54 / 4,070.72 | 3,143.89 / 4,069.90 |

Initial loading is effectively flat in these samples: Chrome p95 rose 1.51ms and Edge p50 rose 19.35ms. No statistically established improvement or strict win on every metric is claimed. The isolated render target passed; full initial-load parity on both percentiles remains unproven. Neither benchmark measures production database/network conditions.

Final combined raw evidence: `campaign-hardening-evidence/browser-final.json`; separate timing samples: `timing-chrome.json` and `timing-msedge.json`. An intermediate run is retained as `browser-intermediate.json`; it had mixed/regressed timings. Running the old benchmark during profiling regenerated `campaign-v7-1-evidence/render-benchmarks.json`; the original report's historical summary remains unchanged.

## Real PostgreSQL concurrency

**12 tests passed** in 9.455 seconds. This is native PostgreSQL with independent psycopg connections, not PGlite or a serialized HTTP adapter. The cluster lives at `tmp/campaign-hardening-real-pg`, listens only on `127.0.0.1:55479`, and uses the dedicated database `campaign_hardening`. Tests apply the repository's CRM migrations and fabricate reviewed queues using the real local queue code.

The race harness pauses one transaction while it holds the campaign row lock, starts a second connection, and verifies a different backend PID is actually waiting on a PostgreSQL lock before releasing the first. Timeouts prevent hangs. Cases cover:

- Two distinct synthetic administrators proposing different times from the same opening revision: one succeeds, the stale operation rejects.
- Simultaneous duplicate operation IDs: both receive the same receipt without another amendment.
- Edit before worker preparation and worker preparation before edit: future recipients stay pending and cannot be claimed early.
- Send Now before worker preparation and the reverse order: batches use the original queue and immutable content.
- An edit waiting while a worker actually claims due recipients into a frozen batch: the edit rejects and claimed rows remain untouched.
- Send Now while outage gating waits: the committed immediate override is honored.
- Outage gating wins first: blocked recipients remain blocked and amendment rejects.
- Postponement while worker activation waits: the worker rereads effective timing and does not start the postponed campaign.
- An actual PostgreSQL division-by-zero error after updates: all updates and operation receipts roll back; retry succeeds once.
- Termination of the amendment's own local backend before commit: rollback preserves the original rows; retry returns one durable acknowledgement.

Every race checks recipient IDs, identity hashes, customer IDs, idempotency keys, template identity/version and the entire immutable template payload. Batch retries retain the same recipient list, request hash and provider idempotency key. External HTTP is blocked. A worker transaction begun before Send Now can see a transaction-start `now()` older than the new due instant; it safely defers until the next tick, which is explicitly tested.

Evidence: `campaign-hardening-evidence/concurrency-final.log`. Opt-in execution requires `CRM_TEST_REAL_POSTGRES=1`; normal discovery skips the native cluster tests. No database-lock or worker-delivery behavior was changed by this pass.

## Timezone investigation and historical remediation proposal

Only existing local evidence was inspected: `campaign-v7-1-evidence/timezone-read-only.json` and the V7.1/V8 reports. These are historical observations, not a current production-state check.

| Frozen value | Source label | Count | What the code proves |
|---|---|---:|---|
| Australia/Darwin | address_timezone | 1,041 | A syntactically valid explicit timezone won before geography was considered. |
| UTC | global_utc_fallback | 43 | No supported geography/explicit-zone resolution succeeded; UTC was used as fallback. |
| Europe/London | address_timezone | 1 | The same explicit-value precedence applied; UK address geography is not proven. |

Legacy `resolve()` checks address `timeZone`, then customer `timezone`/`timeZone`, and labels either result `address_timezone`. It does not check agreement with country, province or postcode. The current Shopify adapter requests address timezone directly; no Darwin default was found in that path. The AU country fallback is Sydney, not Darwin. The global UTC fallback can also represent an unsupported country mapping, not just an empty address.

The frozen evidence does not retain the original geographic fields. Therefore **why those customers supplied those explicit values cannot be determined locally**. It would be incorrect to call all 1,041 Darwin assignments wrong, or to call the London assignment legitimate or illegitimate without geography. The new tests reproduce all three legacy branches and prove that contradictory new AU evidence rejects while consistent Darwin evidence passes.

Postcodes are not universal timezone geocoders. ABS documents postcodes crossing state boundaries; Australia Post lists Broken Hill under 2880/NSW and 0872 localities in South Australia. The new check is deliberately conservative and rejects listed ambiguous regions. It is not an exhaustive international address-verification service. Sources: [ABS Postal Areas](https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs/edition-3-july-2021-june-2026/non-abs-structures/postal-areas), [Australia Post 2880](https://auspost.com.au/postcode/288), [Australia Post 0872](https://auspost.com.au/postcode/0872).

Separate proposed remediation, **not executed**:

The separately reviewable process is also saved in [Historical timezone remediation proposal](CAMPAIGN_HISTORICAL_TIMEZONE_REMEDIATION_PROPOSAL.md).

1. Obtain separately authorized minimal geography evidence keyed to existing recipient identities: address country, state, postcode, address timezone, source and observation date. Avoid names, email addresses and unrelated customer fields in the review artifact.
2. Compare that evidence in report-only mode, classifying consistent, contradictory, incomplete and changed-since-snapshot records. Current addresses alone do not prove historical addresses were wrong. Review aggregate counts and specific proposed corrections before any write.
3. Correct verified source data only under separate authorization, then use it for a new review. Preserve the original frozen timezone/schedule, audience, payload and tracking identities; retain an audit trail of evidence and decisions.
4. Treat any existing campaign recovery as a distinct operation requiring a fresh aggregate of claims, attempts, accepted/uncertain receipts, due window and worker health. Never rely on the old Bathurst observation. Due, blocked, attempted or uncertain work remains outside the amendment path; do not create replacement recipients or blanket-resend it.

## Regression evidence

The clean native-PostgreSQL run passed **329 tests in 128.007 seconds**. It covers Campaigns V7.1/V8, queue/review/preparation, native batch dispatch, tracking, consent/unsubscribe, recovery, Home/progress/cache, authoring sections and UI read behavior. A final focused run passed **37 tests** after the Home CSS and detail changes. Logs are `regression-clean.log` and `final-ui-regression.log` in the evidence directory.

Earlier failing runs are retained. Fixture repairs preserve meaningful checks: scheduled admission now respects the real database clock before a synthetic queue is advanced; the bounded opt-out test excludes unrelated accumulated fixture work; Home's terminal label follows the existing Needs attention contract; section tests compare persisted brand sections rather than requiring their absence; leave tests check the settled AppTest tree after navigation while retaining saved/discarded-content assertions. The database was recreated between broad runs to avoid prior synthetic opt-outs/order scans contaminating results. No application safeguard was weakened to make a test pass.

## Chrome and Edge acceptance

Both installed browser channels were available and exercised headlessly. **16 interaction cases passed**: Home and detail in Chrome and Edge at 1440×900, 820×1180, 390×844 and 320×740. Each case is saved separately as `campaign-hardening-evidence/acceptance-<browser>-<view>-<width>.json`, with screenshots and the complete `browser-final.log`.

Checks covered native control names, keyboard menu opening, menu bounds, Escape with focus inside the menu, cancel without mutation, editing 17:00 to 18:00, saving and observing the updated schedule, explicit Send Now confirmation using Enter, Home becoming Queued, an advancing countdown, exactly two intended fixture amendments, and exactly one document navigation. Independent SQL tests verify duplicate operation replay and immutable queue behavior. The browser backend is synthetic; it does not exercise authenticated production routing, actual provider delivery or live customer records.

Separate scheduled-state checks measured the main scroll container, not just the document. All 16 layouts had no horizontal overflow. Desktop/tablet Home and all detail views fit their tested viewport heights. Mobile Home retains vertical scrolling for metrics, filters and campaign information; its measured height is 1,082–1,220px at the two narrow widths, down from the observed 1,302px 320px layout before the mobile spacing fix. This is not a claim that every screen needs zero vertical scrolling.

Opening the three-dot menu sent **zero HTTP requests and zero outgoing WebSocket frames** in the separate layout checks. Seven of the eight instrumented openings took approximately 31–41ms wall-clock; one Edge/mobile sample took 232ms. These few samples do not establish a guaranteed sub-100ms p95. Evidence: `layout.json`, `layout.log` and scheduled-state screenshots.

**Keyboard caveat:** an intermediate Edge run failed to close the menu with Escape while focus remained on the trigger. The final matrix explicitly focuses a menu item before Escape and passes. The original failure is retained in `browser-focus-diagnostic.log`; trigger-focus Escape reliability has not been proven fixed. Do not describe the full keyboard acceptance requirement as unconditionally complete.

## Files changed by this pass

Runtime: `crm_campaign_progress_ui.py`, `crm_campaign_timing_ui.py`, `crm_campaign_countdown.py`, `crm_campaign_schedule.py`, `crm_campaign_home.py`.

Existing tests: `tests/test_crm_campaign_v2.py` (complete synthetic postcode evidence), `tests/test_crm_production_v2.py`, `tests/test_crm_home_live_progress.py`, `tests/test_crm_campaign_sections.py`, `tests/test_campaign_leave_dialog.py`, `tests/test_crm_production_unsubscribe.py`.

New harnesses: `tests/campaign_real_postgres.py`, `tests/test_campaign_hardening_concurrency.py`, `tests/test_campaign_hardening.py`, `tests/run_campaign_hardening_regression.py`, `tests/fixtures/campaign_hardening_preview.py`, `tests/benchmark_campaign_hardening.py`, `tests/check_campaign_hardening_browser.py`, `tests/check_campaign_hardening_layout.py`.

Documentation/evidence: this report, `docs/CAMPAIGN_HISTORICAL_TIMEZONE_REMEDIATION_PROPOSAL.md`, `docs/campaign-hardening-evidence/*`, and the regenerated original render-benchmark evidence noted above. `source-manifest.json` records the final changed Python source hashes. No commits, pushes, deployment files, production recipient data, CRM/Shopify records, frozen snapshots, original campaign schedules or Resend protections were changed.

## Remaining release gates

- **Initial-load performance:** strict p50 and p95 parity across both browsers is not established. The isolated server-render improvement must not be presented as an overall initial-load improvement.
- **Keyboard acceptance:** investigate/reproduce the intermittent Edge trigger-focus Escape failure. Menu-item-focus Escape passes; that narrower result does not prove the failing variant was fixed.
- **Timezone evidence:** the historical Bathurst geography is absent locally, so the three observed distributions cannot be conclusively classified. This blocks historical correction, not a conclusion that Darwin is wrong. International postcode-level validation and rare geographic coverage are also not comprehensively proven; the added postcode checks are conservative AU checks, not a worldwide geocoder.
- **Scope of evidence:** browser tests use fabricated local data and mocked mutations; PostgreSQL mutation/concurrency tests are separate. No authenticated whole-application/production performance or real-provider delivery acceptance was performed, consistent with the local-only/no-email instruction.

**Production readiness is not declared. Implemented locally; not committed, pushed or deployed.**
