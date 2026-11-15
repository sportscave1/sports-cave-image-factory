> Release reconciliation: included in the October 11 authorized consolidated release; see `releases/SPORTS_CAVE_OS_FULL_SYSTEM_UPDATE_2026-10-10.md`. Historical local-only statements below describe the original task. Lifecycle customer activation remains locked.

# Automations V6 — compact UI and analytics verification

10 October 2026. **Implemented locally; not committed, pushed or deployed.**

Work is in `.tmp-full-system-release`, based on `584931b157534985deb8482a4ea4aeba307070fd`. Its pre-existing release-report edits, prior Campaigns evidence and the dirty original checkout were preserved. No production connections, migrations, record changes or email delivery were used.

## Causes and changes

1. **Whitespace:** zero-height script/routing elements still occupied Streamlit vertical-gap slots. Automations also reused the Campaigns container and its negative margin, with duplicated heading/card spacing. Scripts and bound route controls now share hidden containers; Automations has its own container selector. Only ancestor gaps containing that Home container are zeroed; content retains normal spacing. No global negative-margin workaround was added. At 1440px the heading box moved from y=180 to y=84 under a 64px top bar: **116px to 20px clearance**. Tablet/mobile clearance also measures 20px below their responsive top bars. Desktop six-card height in the multi-currency fixture decreased from 236.4px to 180.9px; content can still grow to remain readable.
2. **Analytics delay:** the summary performed four sequential database/connection transactions (current/prior delivery and revenue). Optional table metrics entered the two-worker queue before the cards. A single SQL statement now returns both periods, and card jobs are submitted ahead of optional row metrics after the critical identity table has rendered. Existing accepted/non-test denominators, event deduplication, period boundaries, average per-automation click rate, attribution eligibility and separate currencies are unchanged.
3. **Repeated work:** the existing successful-results cache was session-local. New browser sessions recalculated unchanged aggregates. A small process-memory cache now reuses successful counts and delivery/revenue summaries across sessions without a database or background-job call on a valid hit. Existing section fragments handle stale refreshes; the OS page does not rerun for their completion.
4. **Responsive issues found during acceptance:** unbroken automation names overflowed Recent Activity cards at tablet width; they now wrap and the card grid uses available container width. At 320px the native select button focused its input and scrolled upward 45px between pointer-down and pointer-up, losing the click. A delegated handler scoped to Automations' Trigger/Sort buttons focuses their input with `preventScroll` before the native action. Keyboard behavior and the native dropdown remain intact.

## Cache behavior and safeguards

- Scope: connection factory, authenticated actor, store namespace and rolling-30-day UTC report definition. Cross-session reuse is disabled without a concrete actor/store namespace. Fragment permissions and actor identity are checked; changing scope disposes the previous session's results.
- Freshness: 180 seconds, with last-success retention limited to one hour and LRU eviction at 32 scopes. Only aggregate values are shared; no recipient/customer rows, browser storage, disk persistence or migrations.
- The UI labels cached figures with their successful update time and identifies the rolling report as of that update. Expired values remain visible while the existing bounded executor refreshes them. Errors show a stale/unavailable indication and preserve the last successful result; incomplete current/prior payloads are rejected.
- Authoring changes invalidate counts; explicit Refresh invalidates counts and delivery metrics. Generation tokens reject late completion after invalidation or eviction. Events from other sessions/workers are reflected on the next visit/interaction after the freshness interval; no new idle polling runs on unrelated pages.
- A process restart or a different server process has a cold cache. Concurrent cold sessions may each perform a bounded read; this change does not add a distributed cache or shared refresh job.

## Performance

All timings are **milliseconds, p50 / p95**. Browser figures are 20 paired samples per condition, interleaving baseline and changed processes, using headless installed Chrome at 1440x1000, Streamlit 1.65, loopback native PostgreSQL, identical synthetic data during each paired run, and blocked non-loopback browser/provider requests. The fixture uses the real sidebar/top bar, CRM routing and Automations code, with synthetic authentication/Shopify boundaries. Both processes were already running; this is not process-cold startup or production end-to-end latency. Visible-paint sampling excludes the OS navigation overlay. Warm timing includes the native sidebar click and browser automation overhead.

| Measurement | Before p50 / p95 | After p50 / p95 |
|---|---:|---:|
| Initial server render | 121.8 / 184.2 | 121.5 / 148.5 |
| Heading visible, cache miss | 672.2 / 792.1 | 677.5 / 731.1 |
| Table visible, cache miss | 672.4 / 792.1 | 677.5 / 731.1 |
| First/fresh analytics, cache miss | 1099.0 / 1264.0 | 1102.0 / 1164.2 |
| New session with reusable cache: heading | 666.3 / 727.3 | 651.7 / 761.9 |
| New session with reusable cache: table | 666.3 / 727.3 | 651.7 / 762.0 |
| New session with reusable cache: analytics | 1086.5 / 1173.0 | 651.7 / 762.0 |
| Warm sidebar return: analytics ready | 535.7 / 612.9 | 578.5 / 700.8 |
| Summary including normal connection/transaction overhead (40 samples) | 134.5 / 159.7 | 40.8 / 50.2 |
| SQL execute/fetch over an already-open loopback connection (40 samples) | 0.5 / 1.5 | 0.3 / 1.2 |

The reusable-cache case improves analytics first paint by **40.0% at the median**; figures appear with the first table/heading paint. A fresh cache hit intentionally does not run a new query, so there is no separate fresh-result timing for that case. Cache misses measure both first and fresh analytics together. The summary cuts **four reads/connections to one**; including active counts, card reads fall **five to two on a miss and to zero on a valid aggregate hit**. Table identity/metrics/activity reads still occur according to their existing caches.

The local SQL itself is very small: connection/transaction overhead dominates the summary measurement. Sub-millisecond SQL execution differences are too noisy to extrapolate. Cold browser and warm-navigation median differences are small, and tail timings vary: **no reliable improvement is claimed for those paths**. The cache benefit and eliminated requests are the supported improvements. Warm return was 42.8ms slower at p50 and 87.9ms slower at p95 in the final run; an earlier paired run measured 609.1/676.2ms before and 574.9/683.0ms after, so its median direction was not repeatable. This variability remains a limitation, not a claimed warm-navigation speedup. Network latency to production, production-sized ledger plans and the entire unrelated OS startup were not measured.

## Verification

- **32 targeted regression tests passed**: analytics, Home reactivity, Automations V5 compatibility, and new aggregate cache tests. Real SQL equality against the previous four-query implementation covers duplicate provider events, currency/eligibility rules, current/prior half-open boundaries, test sends and uncertain receipts. Cache tests cover account/store/connection isolation, copy isolation, expiration, bounded LRU, late-result fencing, invalidation, zero-work hits and last-good retention on rejected refreshes.
- **Chrome and Edge: 8/8 responsive cases passed**, each at 1440, 820, 390 and 320px. Search, trigger filtering, Overview/Recent Activity, create-dialog open/cancel, synthetic existing Flow opening and return navigation passed. Both document and main-content scroll widths fit their viewport/container. No app exception appeared.
- **24/24 native menu cycles passed** across those eight cases: Escape from trigger, interior and action focus, focus restoration, and viewport positioning.
- Acceptance initially exposed the tablet long-label overflow and 320px focus-scroll click loss; both were resolved. The test also switched from the editable combobox text field to its explicit native Open button and waits for prior search results before the next interaction. Assertions on filtering and overflow were retained.
- Sending, trigger execution, recipient eligibility, provider code, schedules, history and database schema were not changed. Existing Flow/Editor save-before-navigation tests passed; synthetic routed Flow navigation was exercised. No full unrelated system audit was repeated.

## Files changed in this task

- `crm_automation_home.py`: scoped compact layout, cache display/refresh, priority and validation, responsive wrapping and dropdown focus.
- `crm_automation_ui.py`: hidden routing container and count invalidation.
- `crm_automation_analytics.py`: one equivalent two-period aggregate statement.
- `crm_automation_aggregate_cache.py` (new): bounded last-success server-memory cache.
- `tests/test_crm_automation_analytics.py`: SQL equivalence and boundary checks.
- `tests/test_automation_v6_cache.py` (new): six cache/validation tests.
- This report and `docs/automations-v6-evidence/`: raw samples, acceptance results, screenshots, test log and local fixture/measurement scripts. Helper scripts were run from the original workspace root against the two isolated source directories; they are evidence, not application startup files.

## Limits and status

The cache is per process and intentionally bounded; previous-session reuse is not guaranteed after restart, eviction, scope change or routing to another server. Production latency and data-scale behavior require a separately authorized release/observation. The local evidence supports these presentation/performance changes; it does not certify unrelated production services. **No deployment has been performed or requested for this task.**
