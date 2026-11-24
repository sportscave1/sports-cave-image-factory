# Reviews startup — Phase 4

24 November 2026. Scope: private OS Reviews startup only. User authorised Git/Render release. Preserve the existing table, storefront, emails, moderation, review text and media.

## Measured baseline

25 authenticated live interactions saved in `artifacts/reviews-startup-phase4-20261124/live-before.json`: five full reloads, ten search/clear changes and ten next/previous changes. Rows took 4745/4874/4762/4850/5073ms (median 4850ms); resolved summary took 6762/6890/6726/6866/7156ms (median 6866ms). Browser-control/network overhead is included. Cached filter changes were 466–1211ms. A cold next page took 4435ms; subsequent page changes still incurred full OS reruns.

Account validation logs were approximately 150ms. The read path used fresh transactional connections, summary needed two separate reads, and completed background data waited for the 1.2s timer and full OS rerun. Historical reviews also started redundant unread-receipt transactions despite having no arrival notification.

## Changes

- Start only the current authorised Reviews Overview reads before shell/sidebar rendering. Reuse the same per-session filter/page cache; other tabs and routes do not prefetch.
- Borrow the existing exclusive bounded OS database read pool for private rows, summary and unread count, with its four-second deadline and stale-connection handling. Writes remain transactional. No new pool, service or result sharing across users.
- Read summary totals and the exact rolling UTC 30-day slice in one SQL statement. Public review order and query path are unchanged.
- Allow one capped 250ms initial completion window. Cached refreshes never wait; slow storage retains the existing asynchronous fallback and last-good rows. No new timer or faster polling.
- Skip seen-receipt work for historical rows without arrival notifications. New active arrivals still use per-account visible-review receipts.
- Log bounded read queue/execution durations without customer data.

## Verification

- 70 focused tests passed with disposable local PostgreSQL enabled (reviews, edits/audits, notifications, Shop ingestion, widgets, startup boundaries and read pool). Six application-scope tests plus eleven subtests passed separately. Separate invocation avoids shared Streamlit/AppTest global context contamination.
- Real loopback-only browser regression passed: ten widths from 320–1920px, Open/Edit/save on synthetic rows, pagination, cache reuse on resize, delayed/failing storage, last-good retention and Retry recovery. Synthetic first display was 443ms at 1920px; next page 354ms; last-good rows remained present 70ms after refresh. No JavaScript exceptions.
- An AST comparison proves table CSS and row markup are identical to published layout commit `82dbd17d`. Access denial queues no jobs; current filter/page keys are preserved; completion wait is capped; historical arrivals do no receipt work; one pooled summary query is used.
- Isolated browser CI added, with synthetic data and blocked external transport. No provider credentials, real emails, review writes or theme changes during testing.
- Canonical Render topology validation and diff checks passed. No infrastructure changes or database migration.

Live acceptance results will be recorded after rollout using the same 25-interaction protocol. These measurements are observed timings, not a guarantee for every network or cold service start.
