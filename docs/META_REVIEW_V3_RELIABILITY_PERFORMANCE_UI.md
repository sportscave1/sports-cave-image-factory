# Meta Review V3 — reliability, performance and interface

Date: 10 October 2026 (Australia/Sydney). Local baseline: `b526c1d0dc3735599ee0b3ad6410f4f1ba1017e8`.

## Outcome and readiness

Implemented locally: GET-only bounded recovery, complete-report stale fallback, distinct failure/empty states, shorter failure cooldown, concurrent identical-report coalescing, faster table styling, early display of complete campaign totals, and scoped compact toolbar/table styling. No advertising writes, production data changes, commits, pushes, merges or deployments were performed.

Ready for a controlled deployment of these fixes after the supplied deployment command passes its fresh-main checks. **This is not a claim that all production performance targets have been met.** Production credentials were absent from the local environment and `.env`; live Meta latency, the actual failing endpoint/trace, real campaign images and the full production navigation/handoff journey remain unverified. No production token was requested or exported.

## Failure investigation

The inspected execution path is `render_page → cached_read → load_overview → load_campaigns/Reader.pages → Reader.get → meta_ads_client._request`. The overview reads account identity, campaign metadata, campaign Insights and country delivery. The page then reads supplemental conversion-hour evidence. Detailed ads, creatives and saved preferences load only for a selected campaign.

Confirmed application contributors:

* `meta_review_live.Reader.get()` previously made one GET attempt. HTTP 400/code 2/subcode 1504044 immediately escaped to the report cache.
* `cached_read()` cached that failure for 120 seconds, the same TTL as a successful report. A rerun during that period returned the failure without trying Meta again. Manual Refresh expired entries and therefore often succeeded on the next attempt.
* Failed loads with no data were passed to the ordinary empty-list renderer. That produced both an API error and “No live campaigns returned.” This was a presentation bug, not evidence of an empty account.
* Prior successful data was already retained by the cache, but the overview did not call the existing timestamp/stale-status renderer. It now does.
* The sync reader only retried 502/503/504 once, immediately. It now shares the Review GET policy.
* Country association scanned all country rows once per campaign; table styles repeatedly used Pandas scalar `.loc` writes.

The supplied error is consistent with a temporary service failure, but its production cause is **not established**. Mocked reproduction uses the exact supplied HTTP/code/subcode. There is no production request trace proving an outage, timeout, rate limit, bad parameter or query-cost cause. A successful manual retry argues against a consistently invalid token; it does not prove token and permission problems never occur. No evidence justified changing attribution, pagination fields or account configuration.

Responsibility: the upstream error response is Meta's; failure amplification, missing retry, long negative caching and contradictory empty-state text were application-controlled. Network latency and Meta availability are not locally controllable.

## Recovery and cache contract

`meta_review_retry.get()` is called only by the live and sync Review GET readers. It never wraps `_post()` or other advertising writes.

* At most three attempts, with exponential delays of 1 and 2 seconds plus 0–0.5 seconds jitter. `Retry-After` seconds or HTTP dates take precedence. A delay exceeding the remaining budget aborts recovery instead of sleeping indefinitely.
* A 35-second scheduling budget per GET, within the shared report reader deadline. Overview/detail reports now share their 90-second reader across core pagination and country reads; sync retains its 180-second deadline. Connection timeout is at most five seconds; total-aware request/read timeout is at most 30 seconds and shrinks with the remaining budget. Late results are rejected.
* HTTP 429/500/502/503/504, qualifying code 2 (including the supplied subcode), recognized rate codes, explicitly transient responses, timeouts and connection interruptions are retryable. Explicit `is_transient=false` is respected. Invalid parameters, authentication and permission codes 10/100/102/190/200/294 and HTTP 401/403 are not retried as temporary errors.
* Error metadata now retains `is_transient` and `Retry-After`; GET duration/attempt/status/code/subcode logs contain no tokens, URLs, parameters or response bodies. Other client callers retain their existing 30-second timeout and no new retry behavior.
* A process-local in-flight registry coalesces identical report loads. Waiting callers receive independent copies. Different accounts, API versions, token rotations, date ranges and report kinds remain separate. Attribution is still the fixed unified-attribution request setting; no alternative attribution configuration was introduced.
* Successful reports remain cached for 120 seconds. Failed loads have a ten-second cooldown, extended to honor `Retry-After`. Refresh preserves prior successful data and respects an outstanding server-requested cooldown. There is no timer repeatedly forcing whole-page reruns.
* Only complete validated results replace the cache. Page failures, cursor loops, malformed responses and pagination limits never publish partial results. Account identity checks remain intact.
* Failed refreshes keep the exact matching prior report, its original timestamp and its prior supplemental observations together. They do not combine stale totals with newly fetched recency data. Cache eviction remains bounded to 24 entries; no cross-account or cross-period fallback is used.

Requests' socket timeouts are not a hard operating-system cancellation of a connection that keeps trickling bytes. Deadlines prevent further attempts/pages and reject late results, but a strict externally enforced wall-clock kill is not claimed. Coalescing is within one server process, not across separate Render workers. Exhaustion produces a warning and a usable Refresh control; it does not retry forever.

## Accurate UI states

| Condition | Presentation |
|---|---|
| Successful report with campaigns | Campaigns and actual refreshed timestamp |
| Successful zero result | No campaigns matched the selected reporting scope |
| Failure with matching complete cache | Compact warning, STALE CACHED META, original refresh date/time, preserved rows |
| Failure without matching cache | Clean retry explanation; no claim that campaigns do not exist |
| Failure after a successful empty report | Explicitly describes the cached empty report and current failure |

Unconfigured connections also avoid an erroneous successful-empty message. Stale status is visible outside the table and cannot be mistaken for a fresh live result.

## Reporting period

`meta_review_search.reporting_default()` explicitly returns the previous calendar-year date through today, with leap-day protection. Existing tests require this behavior. The screenshot's 10/10/2025–10/10/2026 range follows that rule; it is not an accidental cache label. Explicit user selections remain untouched.

| Requested live comparison | Result |
|---|---|
| Yesterday and today | Not measured: no configured local Meta credentials |
| Last seven days | Not measured: same limitation |
| Last 30 days | Not measured: same limitation |
| Current calendar-year window | Not measured: same limitation |

A larger reporting window may require more upstream computation, but no measured latency or failure-rate comparison supports changing this product default. No report was shortened or relabeled. Conversion attribution and the separately defined recent-sale observation window remain unchanged.

## Performance method and baseline

Repeatable scripts: `scripts/benchmark_meta_review_v3.py`, `scripts/benchmark_meta_review_workflow.py`, and `tests/check_meta_review_v3_ui.py`. Tests use synthetic data and mocks; browser external requests are blocked. Baseline modules were exported from the baseline commit before changes, and the final module snapshot excludes concurrently added shared table imports. Windows, local Python/Streamlit 1.58, installed Chrome and Edge were used.

CPU measurements use 30 samples, AppTest measurements 20, browser measurements ten per browser. p50 is the median; p95 uses the empirical lower percentile (`sorted[floor(.95*(n−1))]`). Small browser samples are directional, not a production SLA. CPU/style timings include DataFrame and Styler computation but exclude browser paint. The first style import is warmed separately. New-session browser timings include browser navigation and the mock application, not a cold Render process. Browser refresh waits for a new fixture run marker, not merely an already-visible table.

### Local CPU, milliseconds (before → after)

| Operation | p50 | p95 |
|---|---:|---:|
| 100-row table styles | 76.196 → 5.751 | 98.028 → 7.325 |
| 1,000-row table styles | 949.479 → 37.197 | 1186.752 → 58.244 |
| 100-row search | 3.666 → 3.813 | 4.795 → 4.405 |
| 1,000-row search | 37.045 → 48.949 | 47.951 → 81.452 |
| 1,000-row numeric sort | 1.576 → 1.667 | 1.770 → 2.665 |
| 1,000-row warm cache copy | 2.221 → 2.480 | 2.462 → 3.535 |

The measured improvement is table styling (approximately 96% lower 1,000-row median). Search, sort and copy algorithms were intentionally unchanged; sample variation is not presented as an improvement.

### Mock Streamlit/Python full reruns, milliseconds (before → after)

| Operation | p50 | p95 |
|---|---:|---:|
| New mock session | 28.983 → 36.707 | 36.000 → 42.852 |
| Warm full rerun | 28.125 → 24.116 | 33.443 → 31.235 |
| Manual mock refresh | 31.240 → 39.265 | 35.179 → 44.809 |
| Search full rerun | 24.838 → 24.759 | 28.251 → 28.950 |
| Sort full rerun | 30.404 → 26.014 | 34.338 → 28.659 |

These AppTest runs use eight campaigns. Production search/sort still use the existing fragment; AppTest full-rerun timings must not be substituted for browser interaction latency. Cold/refresh Python work increased by approximately eight milliseconds because it now also renders an early primary-metrics preview. This is an explicit tradeoff for useful content while the optional network read runs, not a claim that every operation became faster. Refresh samples reset AppTest's prior button trigger outside the timing interval and assert that a new mock report was actually requested.

### Loopback browser, milliseconds (before → after)

| Operation | Chrome p50 / p95 | Edge p50 / p95 |
|---|---:|---:|
| New mock session | 450.46 / 516.67 → 334.30 / 424.69 | 407.24 / 483.76 → 332.28 / 424.71 |
| Search to no-match result | 131.26 / 240.29 → 114.56 / 135.31 | 175.97 / 239.37 → 117.77 / 128.99 |
| Manual mock refresh | 248.71 / 350.84 → 231.84 / 253.79 | 242.03 / 348.37 → 227.83 / 245.30 |

Browser samples include Playwright interaction/wait overhead. They do not establish production warm-navigation or network targets. Real browser search did not meet the 100 ms median target in these samples. Local numeric sort and warm Python processing are comfortably below the requested CPU-scale targets, but selection paint, cached popup browser latency and production warm opening were not established.

## Full workflow audit coverage

| Requested action | Evidence / measurement limit |
|---|---|
| First cold opening | Mock new-session browser + AppTest timings; real process/network cold start unmeasured |
| Warm return | Warm AppTest cache rerun measured; real navigation return unmeasured |
| Campaign API retrieval | Request sequencing/pagination/unit tests; actual Meta latency unmeasured |
| Initial campaign table | CPU style benchmark and browser render wait measured |
| Refresh From Meta | AppTest and browser timings, stale/empty/error regression checks |
| Search | CPU, AppTest and Chrome/Edge interaction measurements |
| Sort | Numeric CPU/AppTest measurements and existing identity tests |
| Change reporting period | Existing period isolation/control tests; live latency unmeasured |
| Campaign popup | Existing popup/cache/selection AppTests pass; browser p50/p95 unmeasured |
| Individual ads | Lazy selected-campaign mocked read tests pass; actual network unmeasured |
| Creative images/winning details | Existing creative/carousel resolution tests pass; real image download/paint unmeasured |
| Campaign statistics | Existing metric/summary tests pass; no separate production timing |
| Advanced metrics | Chrome/Edge desktop/narrow access and metric tests pass; no isolated paint timing |
| Winning ad selection | Existing automatic/manual selection tests pass; browser timing unmeasured |
| Creative Refresh handoff | Existing handoff/navigation/original-reference tests pass; no production handoff performed |
| Return to Meta Review | Cache reuse tests pass; complete production navigation timing unmeasured |
| Failed-request recovery | Exact code/subcode mocked retry, exhaustion, stale fallback and browser error-state tests; actual incident unobserved |

Database/storage latency was not measured. The main overview performs no database reads; selected-campaign preferences use the pre-existing cached path. Images/creative reads remain lazy. No measurement has been invented for a missing layer or operation.

## Bottlenecks and changes

1. **Measured:** repeated Pandas scalar style writes dominated large-table CPU time. Build style dictionaries and one DataFrame instead, preserving values, formatting and semantic bands.
2. **Confirmed structural, production magnitude unknown:** failed calls blocked the report for 120 seconds with no retry. Bounded GET recovery and shorter negative caching address this.
3. **Confirmed structural, production magnitude unknown:** optional conversion-hour reads delayed useful table content. The page now streams an initial read-only grid of complete primary metrics, with recency/actions explicitly pending, before loading the optional report; the final interactive table replaces it. Warm reads do not build this extra preview.
4. **Algorithmic, not separately benchmarked:** country delivery is indexed by campaign once instead of repeatedly scanning the full list. Country-specific benchmark rules are unchanged.
5. **Already fast:** sorting/copying. Preserved these and the existing search fragment, instead of adding caching or concurrency complexity. No added speculative parallel Meta traffic.

## Interface comparison and preservation

Before: active cells used colored fills, controls lacked a consistent outlined treatment, the overview omitted freshness text, and a large red failure banner could accompany an empty-campaign claim.

After: scoped Segoe UI typography around the native grid, subtle borders, neutral active-cell background with its existing green text/dot, compact outlined controls, restrained gold focus, a toolbar separator and compact connection warning. Narrow controls stack and page padding contracts. The reference was `crm_automation_analytics_ui.py` and `components/crm_checkout_table/index.html`; no checkout/customer logic was copied.

The native Streamlit grid is retained for virtualization, scrolling, sticky headers, keyboard interaction, pinned campaign names, selection and true numeric sorting. It is not a pixel-identical custom checkout table. Existing 32-pixel campaign rows and the contained 660-pixel maximum height remain. Header/theme rendering inside the canvas follows the application's existing theme; broad theme changes were deliberately excluded.

All campaign columns remain: Campaign, Format, Status, Spend, Sales, ROAS, CPA, CTR, CPC, ATC, Checkout, Last Sale and Action. Advanced metrics remain available. No changes to website purchase mapping, Meta-reported ROAS, inline-link CTR/CPC, attribution, recommendations, status interpretation, last-sale calculations, winning creative logic, uploaded references, saved selections or handoff payloads. Rows still map selection to the displayed sorted/filtered order. No changes to other Ads modules or Render topology.

## Validation and limitations

The isolated release snapshot ran **492 tests: 485 passed, seven skipped**, with no failures. The Render topology validator passed: the canonical primary remains `sports-cave-os` / `srv-d8kl4on7f7vs73dvavv0`. The broader Meta suite covers read and mocked write-client regression contracts; it never performs live advertising writes. Seven PostgreSQL job tests require an explicitly enabled local database fixture and remain skipped. Browser checks passed in Chrome and Edge at 1440 and 390 pixels, covering toolbar access, table containment, advanced metrics, stale cached rows and failure without cache. No JavaScript errors were observed. Initial browser fixture failures (open sidebar and asynchronous resize) were corrected before final verification; intermediate numbers using an already-hidden status widget were discarded. The final helper was also exercised in `-ValidateOnly` mode; this mode does not fetch, commit, push or deploy.

Remaining limits: no live incident reproduction, no real four-period latency comparison, no production trace access, no full browser creative-refresh journey, no independent 1,000-row scrolling FPS/selection-paint measurement, and no cross-process request coalescing. The native grid's virtualization is retained, not newly proven against a production-size account. Auth failures remain visible and require connection repair. Long genuine report queries can still hit the bounded deadline.

## Release safety and manual deployment

Concurrent Email work and a separate shared-table change were present in the workspace. Shared-table imports/row-height additions in `ads_meta_review_page.py` and `.streamlit/config.toml` were excluded from this task's release snapshot without reverting them in the working tree. The exact release patch includes only the six application modules, regression/fixture/browser files, benchmark scripts and this report.

The local deployment helper verifies the release-patch hash, clones into a new isolated directory, fetches GitHub `main`, applies the patch with three-way conflict detection, verifies the staged path allowlist, runs the broader Meta tests and topology validator, then commits and performs a normal `HEAD:main` push. A conflict, test failure or concurrent remote advance stops the operation. It never force-pushes, stashes, resets, switches the shared checkout, or deletes unrelated/untracked files. The original checkout intentionally remains untouched and may be behind after deployment. Deployment helper/patch/manifest and temporary test artifacts are not included in the production commit.

The push uses the existing repository remote and its existing Render automatic deployment integration. It creates no service and performs no Blueprint sync. No new Render configuration or ad-account identity is introduced.

Run this **one PowerShell command** manually in VS Code:

```powershell
& { Set-Location -LiteralPath 'C:\Users\hello\Documents\sports-cave-image-factory'; & '.\scripts\deploy_meta_review_v3.ps1' }
```
