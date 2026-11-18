# Companion status header — local implementation

Task `20261118-71429ec3`, owner `codex-companion-header-20261118-01a1ec26`.
Based on the user-approved, verified live ads queue release `725c0a35`.

The header has separate Design, Uploads and Ads cards for companion administrators.
Each shows current work, stage progress, waiting counts, paused/offline state, or
the latest completed/failed result. Clicking a card opens its details and queue
play/pause button. Upload restart and cancel retain their existing guarded actions;
Ads details link to the saved posting job when available. Opening status details
dismisses overlapping notifications so recovery buttons stay reachable.

Search is a header icon. Clicking it or pressing Ctrl+K opens the existing search
palette above the page without shifting the header. Escape restores focus to the
icon; outside click closes the palette. Existing editor keyboard protections remain.
On smaller displays the three cards occupy a dedicated header row.

Status comes from the existing six-second authenticated polling loop and queue
stores, not a new worker or timer. Design progress retains the existing time-based
estimate and is explicitly labelled. Ads progress represents workflow checkpoints
(prepare/open/generate/post/complete), never measured image generation percentage.
Connection failures retain the last confirmed data with an explicit retrying/stale
indicator. Failure notices are deduplicated and job details retain the full failure.

Administrators see the whole upload queue; other staff retain their existing
requester-scoped upload view and do not receive Design/Ads queue data or controls.
The Ads play/pause action uses the existing admin, same-origin and boolean checks.
Account changes clear the previous header snapshots. Status polling never submits,
restarts or cancels a job. Large ad prompts/results are excluded from the dashboard
query payload. No migration or desktop companion update is required.

## Local verification

- 70 Python tests and 3 subtests passed across `test_morning_design_queue.py`,
  `test_design_publish_ad.py`, `test_companion_header.py`,
  `test_companion_queue_controls.py` and `test_top_bar.py`.
- 3 headless Edge browser tests passed across `test_companion_header_browser.py`
  and `test_upload_restart_browser.py`: actual header CSS/controller at 1600,
  1280, 1024, 820, 600 and 390 pixels; search overlay/focus/dismissal;
  play/pause with no waiting jobs; existing upload restart and cancel.
- Node contracts passed: `test_upload_progress_notifications.cjs`,
  `test_top_bar_navigation.cjs`, `test_top_bar_requests.cjs`. These include
  independent queue state, failure details, duplicate notices, stale/recovered
  polling, queue permissions disappearing, and existing navigation/request behavior.

Database tests use disposable PGlite via AUTO_EDITIONS_TEST_PGLITE. Browser tests
fulfil all HTTP requests with synthetic fixtures; no running app, production
credentials, live customer data, external ad, email or automation is used.
Screenshots are saved outside the repository in the local companion-header-evidence
temporary directory. Changes are uncommitted and have not been deployed.
