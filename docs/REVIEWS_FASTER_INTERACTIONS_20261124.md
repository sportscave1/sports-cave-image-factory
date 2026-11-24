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
