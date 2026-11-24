# Faster Reviews interactions

24 November 2026. User authorised optimisation, unchanged table layout, testing and Git/Render release. Continuation of Phase 4.

## Diagnosis and changes

Five new authenticated baseline reloads displayed rows in 3288/3292/3053/3531/2927ms. The browser reload command returned in 256–378ms; the remaining time was genuine display waiting, not just command overhead. A production trace showed document response at 07:04:50.310 UTC, WebSocket acceptance at 51.263, script start at 52.494 and script completion at 53.107. The script itself took 613ms; pooled Reviews reads took 162/323ms in that trace. The largest remaining cold-load cost is before app execution in the Streamlit connection/startup path. These timestamps do not establish a single cause for that entire interval.

The table interaction path also discarded one render and rebuilt the whole OS twice on each page change. This release:

- Makes Overview a Streamlit fragment. Normal table interactions update the review section, preserving the shell. Pagination callbacks update the offset before rendering, avoiding a second rerun.
- Revalidates fragment interactions through the existing OS account policy and the same 30-second revalidation bound. Denied access clears the fragment and queues no review reads. No authentication weakening or cross-user cache.
- Registers existing slow-read completion delivery inside the owning fragment. Slow new filters, refresh errors, last-good rows and retry remain supported without permanent new polling.
- Selects only list fields for Overview: a 161-character body prefix preserves the exact 160-character display and ellipsis, and only the date-known metadata is transferred. Open/Edit still load the full record with current edit version and audit behaviour. Original review data is unchanged. Public queries and widgets are unchanged.
- Leaves table CSS and row markup identical, verified against the published layout. No new services, schema or theme changes.

## Verification before release

73 focused tests passed with disposable local PostgreSQL, including identical HTML from compact/full rows with a large fabricated payload and long Unicode body, original full editor data, permission denial before reads, notifications, public widgets and ingestion. Six application startup tests and eleven subtests passed separately. The real offline browser test passed at ten widths (320–1920px), including native Open/Edit/save, pagination without rerunning the shell, a brand-new slow filter, delayed failure, retained rows and Retry recovery. Provider transports blocked and synthetic data only.

Live baseline and final measurements are stored separately under `artifacts/reviews-faster-20261124/`. Sub-second warm table updates and full browser reload are measured separately; no promise that an entirely new Streamlit connection loads in under a second.

## Live acceptance

Runtime `616861d06012b54600be8748798daab4b049b796` is Live on the canonical primary and both existing supporting services. [CI 45346859786](https://github.com/sportscave1/sports-cave-image-factory/actions/runs/45346859786) passed all steps, including the ten-width browser regression and a slow new filter. No infrastructure configuration changed.

| Signed-in browser measurement | Before median | After median |
|---|---:|---:|
| Five reloads to first rows | 3288ms | 3027ms |
| Same five reloads to resolved summary | 3361ms | 3122ms |
| Ten mouse Next/Previous changes | 1977ms | 1185ms |
| Ten keyboard Next/Previous changes, additional final check | Not sampled | 583ms |

Mouse-driven pagination improved by about 40%. Its automated click includes bringing the footer button into view and browser-control overhead; keyboard measurements use Enter on the same native buttons and are not substituted into the mouse comparison. Nine of ten keyboard changes were below one second (447–736ms); one took 1231ms. Mouse changes ranged from 970–2557ms. This is not reliably sub-second for every interaction. Full reloads remained approximately three seconds, with 3.7–4.2s outliers; five samples do not prove that the small reload difference is a stable gain. The remaining full-reload target is not achieved.

Read-only production size check for the first 26 rows (25 displayed plus sentinel): full JSON rows 46,175 bytes versus compact 15,007 bytes, about 68% less database transfer. Published count remained 209. Live normal table reads were 143–153ms on reloads, versus approximately 283–285ms in the preceding Phase 4 measurement; one later refresh was slower at 410ms. No new indexes or caches were added.

Live checks confirmed unchanged 1440/881/390px geometry, no horizontal overflow, full Open/Edit labels and 44px phone actions. Open and Edit loaded the full review and were closed without saving. E Maddock remains published with four stars and rating-only text. No JavaScript errors. Temporary viewport reset. Screenshot and raw before/after measurements are saved beside this release's artifacts.

Local browser first-row median was 360ms across ten widths, next page 304ms and retained last-good rows visible 99ms after refresh. Resizing reused existing reads; pagination did not rerun the fixture shell. The remaining cold-load delay is in the broader connection/bootstrap/render path before the review query; this trace does not identify a single root cause for that whole interval. Avoid claiming a guaranteed sub-second full reload or weakening authentication to meet that number.
