# Reviews startup — Phase 4

24 November 2026. Scope: private OS Reviews startup only. User authorised Git/Render release. Preserve the existing table, storefront, emails, moderation, review text and media.

## Measured baseline

25 authenticated live interactions saved in `artifacts/reviews-startup-phase4-20261124/live-before.json`: five full reloads, ten search/clear changes and ten next/previous changes. Rows took 4745/4874/4762/4850/5073ms (median 4850ms); resolved summary took 6762/6890/6726/6866/7156ms (median 6866ms). Browser-control/network overhead is included. Cached filter changes were 466–1211ms. A cold next page took 4435ms; subsequent page changes still incurred full OS reruns.

Account validation logs were approximately 150ms. The read path used fresh transactional connections, summary needed two separate reads, and completed background data waited for the 1.2s timer and full OS rerun. Historical reviews also started redundant unread-receipt transactions despite having no arrival notification.

## Changes

- Start only the current authorised Reviews Overview reads before shell/sidebar rendering. Reuse the same per-session filter/page cache; other tabs and routes do not prefetch.
- Borrow the existing exclusive bounded OS database read pool for private rows, summary and unread count, with its four-second deadline and stale-connection handling. Writes remain transactional. No new pool, service or result sharing across users.
- Read summary totals and the exact rolling UTC 30-day slice in one SQL statement. Public review order and query path are unchanged.
- Allow one capped 500ms initial completion window. Cached refreshes never wait; slow storage retains the existing asynchronous fallback and last-good rows. No new timer or faster polling. The initial 250ms trial reduced median live rows to 3103ms and resolved summary to 3178ms, but missed normal 283–471ms reads and incurred an avoidable rerun; the final cap follows that measured range.
- Skip seen-receipt work for historical rows without arrival notifications. New active arrivals still use per-account visible-review receipts.
- Log bounded read queue/execution durations without customer data.

## Verification

- 70 focused tests passed with disposable local PostgreSQL enabled (reviews, edits/audits, notifications, Shop ingestion, widgets, startup boundaries and read pool). Six application-scope tests plus eleven subtests passed separately. Separate invocation avoids shared Streamlit/AppTest global context contamination.
- Real loopback-only browser regression passed: ten widths from 320–1920px, Open/Edit/save on synthetic rows, pagination, cache reuse on resize, delayed/failing storage, last-good retention and Retry recovery. Synthetic first display was 443ms at 1920px; next page 354ms; last-good rows remained present 70ms after refresh. No JavaScript exceptions.
- An AST comparison proves table CSS and row markup are identical to published layout commit `82dbd17d`. Access denial queues no jobs; current filter/page keys are preserved; completion wait is capped; historical arrivals do no receipt work; one pooled summary query is used.
- Isolated browser CI added, with synthetic data and blocked external transport. No provider credentials, real emails, review writes or theme changes during testing.
- Canonical Render topology validation and diff checks passed. No infrastructure changes or database migration.

## Live acceptance

Runtime `0116e7c878e17a352e4f267cd57a0d1cd381d6dd` is Live on the canonical primary and both existing supporting services. Later CI-only commits use `[skip render]` and do not change executable application source.

Repeated the same 25-interaction protocol after rollout:

| Authenticated browser measurement | Before median | Final median |
|---|---:|---:|
| Reload to first review rows, five samples | 4850ms | 3170ms (35% faster) |
| Reload to resolved summary, same five samples | 6866ms | 3248ms (53% faster) |
| Ten search/clear changes | 692ms | 711ms |
| Ten next/previous changes | 2026ms | 2069ms |

Final rows: 3427/3131/3204/2931/3170ms. Final resolved summary: 3521/3265/3239/2959/3248ms. No five-second outlier remained in these five samples. Warm search and page timings do not show a meaningful improvement; the gain is initial startup. Pagination measurements include native button scrolling through 25 rows and browser-control overhead. Avoid treating them as server-only timings. Full reload still takes about three seconds over this connection; it is not instant.

Final live instrumentation: summary 142–152ms, table approximately 283–285ms, queue 0.1–0.8ms on reloads; one filtered query 148ms. These are full pooled read durations, including network transfer, not pure SQL timings. The initial 1.2s completion-timer dependency is avoided for those normal reads. No schema/index change is warranted by this evidence.

The signed-in OS retained total 209 and rating 4.8. Open and Edit dialogs loaded and were closed without saving. E Maddock remains published with four stars and no title/body. Live widths 1440/881/390px had no row overflow, visible 80px Open/Edit buttons and 44px phone actions. No browser JavaScript errors. Temporary viewport override reset. The table CSS and row markup remain identical.

Final synthetic ten-width run after restarting the local server: median first rows 364ms, next page 402ms, retained last-good rows 86ms after triggering a delayed failure. Synthetic and live evidence are separate. Saved measurements and screenshot: `artifacts/reviews-startup-phase4-20261124/`; loopback browser screenshots: `artifacts/reviews-table-responsive-20261124/`.

CI uses the Ubuntu 24.04 runner's installed Chrome, avoiding a redundant browser download. The initial setup attempts were superseded. Final [CI run 45344725569](https://github.com/sportscave1/sports-cave-image-factory/actions/runs/45344725569) passed all steps, including startup/read-pool/access tests, application scope, ten-width browser/actions/outage recovery and evidence upload, on commit `30affc1ab827a2b904d7804cd0351c757a481cc8`. These measurements are observations, not a guarantee for every network or cold service start.
