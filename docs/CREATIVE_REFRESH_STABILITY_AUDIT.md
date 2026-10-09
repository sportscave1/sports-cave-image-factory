# Creative Refresh stability audit — 9 October 2026

Local implementation and mocked verification only. No live advertising writes,
deployment, schema change or new dependency.

## Connected execution paths inspected

`app.py` dispatches the Creative Refresh route through
`ads_creative_refresh.render_page` to `ads_page.render_page('creative_refresh')`.
This is a full page, not a dismissible Streamlit dialog. The Campaign review
dialog in `ads_meta_review_page` owns the winner selection; Refresh Winning Ad
and Build From Best Components feed the existing `meta_review_handoff` contract.
The source strip is a client-side iframe rendered inside a Streamlit fragment.
Card scrolling does not regenerate the advertising workflow.

The audit followed source archives (`meta_carousel_view`), product association,
prompt plan retention (`ads_refresh_plan`), edited copy and uploads (`ads_page`),
CSV popovers, saved workspace (`ads_refresh_saved`), POST NOW
(`ads_posting_handoff`/`ads_posting_page`), app dispatch and shared connection
recovery (`session_recovery.py` / `components/session_recovery.js`).

Normal input commits, explicit Save/POST NOW and sidebar navigation legitimately
rerun the app. No periodic rerun is owned by Creative Refresh itself. Other
pages' fragments and notification functionality were not disabled. Existing
prompt-plan bounds, unchanged-upload identity checks and successful archive
preview caching were retained rather than replaced.

## Reproduced defects and fixes

### A replayed winner can restart the draft

`meta_review_handoff.hydrate` stripped `campaign_type_resolution` from the active
source, but compared it against a pending package that could still contain that
field. The same winner was then treated as different: the Carousel result and
image workflow were cleared. Product fields were also hydrated before any
duplicate check, replacing local edits on replays.

The new test failed against the original implementation. The fix compares the
same normalized representation before modifying state. An identical replay
consumes the pending event without touching the draft, product URL or images.
A different winner still replaces the workflow. A diagnostic logs replay
suppression without including creative/customer payloads.

### Shared connection recovery silently reloads an unsaved Refresh page

The shell's connection-recovery script treated a successful health probe as
permission to reload. It sent the email checkpoint event, but Creative Refresh
has in-memory media/copy rather than that email-specific checkpoint.

A real local browser test loaded the old script, edited a headline and simulated
Streamlit's Connection error dialog plus disabled sidebar state. The health
probe caused a navigation and the unsaved headline was lost. With the new
script, an active Creative Refresh marker prevents that automatic destructive
reload and adds a visible explanation inside the genuine connection dialog.
After the simulated interruption clears, editing continues with the same value.
The script still performs normal bounded recovery for other pages. It never
unlocks disabled controls or removes Streamlit's connection-error dialog.

This is protection from a destructive recovery action, not proof that a dead
server session can be recovered. A manual reload or permanently lost server
session can still lose unsaved media; explicit saved workspaces remain the
durable recovery path. The warning states this limitation.

### Failed archive reads repeat during every rerender

Successful archived media was already cached, but missing/error responses were
silently retried on every render. Four unavailable cards across twenty rerenders
made eighty archive reads. Failure entries are now bounded to twenty, expire
after thirty seconds, and can be cleared immediately with Retry source images.
Copy and source associations are untouched. Original URLs remain available as
fallbacks. The UI identifies affected positions; logs contain only card number
and exception class, not URLs, tokens or private payloads.

## Measurements

Local benchmark, four unavailable archives and twenty rerenders, warmed Python
imports, no network and no artificial request delay:

| Measurement | Before | After |
|---|---:|---:|
| Archive read attempts | 80 | 4 |
| Total local CPU/wall sample | 9.902 ms | 3.151 ms |

Request reduction is the useful result; the CPU sample does not predict database
or production latency. The raw result is in `tmp/refresh-failure-benchmark.json`.

Browser timings and heap samples are recorded in
`tmp/refresh-stability-browser.json`. They are local mocked-storage measurements,
not production benchmarks. Heap samples include normal allocation/GC variation
and cannot establish absence of a long-term leak. No production initial-load,
database-lock or websocket availability claim is made.

The extended run completed 360 card actions and 126 handoff replays across six
Chrome/Edge sessions. Each session had 55–56 background fragment ticks and an
additional 15-second idle period. Median card actions were 8–22 ms and initial
opens 1.025–1.661 seconds. Archive reads were exactly three per card across
initial success, forced outage and restored success, with no extra warm reads.
Browser heap samples rose from roughly 32–47 MB to 58–65 MB during these short
sessions; this is recorded, not presented as proof of leak-free extended use.

## Verification and scope

390 focused Python regressions passed, including the new replay/failure tests,
existing Meta Review Carousel contract, 4/5/6-card save/restore, CSV compatibility,
Instant Experience, POST NOW and mocked Meta recovery. The shared shell/email
checkpoint JavaScript tests also pass. Existing known legacy New Ads expectation
failures are documented in `CREATIVE_REFRESH_SAVE_HANDOFF_REPAIR.md`.

The reconnect browser test reproduces the old data loss and verifies the fix.
The browser stress matrix covers Chrome and Edge with 4/5/6 cards, background
fragment ticks, repeated client-side card movement, duplicate handoffs, archive
failure/recovery and retained edited copy. See the raw browser result for the
completed run's iteration counts and measurements.

The existing full browser regression also passed in both Chrome and Edge:
CSV import, image upload/preview, prompt clipboard, IE and Carousel save and
POST NOW, at 1366/1024/750/390px with no horizontal overflow. Outputs are in
`tmp/refresh-overhaul-chrome.txt` and `tmp/refresh-overhaul-edge.txt`.

Two initial stress-run harness failures were investigated: a loopback port was
still unavailable after a prior run, and a counter assertion read an intermediate
render (8 reads before the next completed render reported 12). Configurable
isolated ports and waiting for the completed counter resolved those harness
issues; assertions on exact request counts and retained copy remain in place.

The earlier local save/handoff repair remains in place: optional review JSON is
not a save gate; partial workspaces use existing durable storage; missing media
does not become a fabricated upload; Create Ad retains real validation and
PAUSED safeguards. See `CREATIVE_REFRESH_SAVE_HANDOFF_REPAIR.md` for those files.

## Files changed by this audit

- `meta_review_handoff.py`: duplicate application guard before state mutation.
- `meta_carousel_view.py`: bounded failure retry cache and actionable retry UI.
- `components/session_recovery.js`: scoped protection against destructive reload.
- `tests/test_refresh_stability.py`: replay and archive-failure regressions.
- `tests/test_refresh_stability_ui.cjs`: Chrome/Edge stress and measurements.
- `tests/test_refresh_reconnection_ui.cjs`: old/new recovery reproduction.
- `tests/refresh_failure_benchmark.py`: reproducible before/after benchmark.
- `tests/fixtures/refresh_ui.py`: opt-in synthetic background/failure controls.
- `scripts/run_refresh_browser.py`: configurable loopback port for isolation.
- `tests/test_ads_refresh_ui.cjs`: browser/port selection for existing regression.

## Still unverified

The two reproducible restart/data-loss mechanisms are repaired; they cannot be
claimed as the exclusive cause of every production incident without production
browser/network traces. Real authentication expiry, server restarts, multi-hour
sessions, slow production archives and genuine websocket reconnect behavior were
not recreated end-to-end. The browser recovery test simulates the frontend
connection-error condition; it does not kill a production websocket or server.

No broad rewrite, CSV/generation contract change, new autosave database or global
polling removal was introduced. Release requires review of the complete local
diff; no deployment or database migration was performed by this task.
