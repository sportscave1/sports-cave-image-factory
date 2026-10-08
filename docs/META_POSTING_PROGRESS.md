# Shared Meta posting progress

## Cause and implementation

New Ads and Creative Refresh already hand off to `ads_posting_page.py` and use
`MetaPostingService`. Posting itself ran synchronously inside a Streamlit script
run. Progress existed only in that run's `st.status`; terminal results were copied
into session state. The persistent ledger was available in history, but there was
no active job monitor or durable-result reopening. Losing/rerunning the browser
request could therefore leave an unexplained screen despite Meta work occurring.

Both entry points now use the same `ads_posting_progress.py` panel, existing
result renderer and existing Meta service. `meta_posting_jobs.py` is a bounded
executor around that service, not a second Meta posting implementation.

- Reserve the existing submission UUID in `meta_posting_submissions` before
  dispatch. Duplicate reservations cannot dispatch another worker.
- Hydrate that reservation with the service's validated request and use the
  existing lease, fingerprint checks, resource checkpoints and reconciliation.
- Run independently of the browser session. Poll only the progress fragment
  every two seconds; stop when terminal status and worker completion agree.
- Display actual stage callbacks and the number of Meta-confirmed paused ads.
  Percentages represent confirmed ad count, not estimated elapsed work.
- Restore via `meta_posting_job` in the URL/session, or open a saved result from
  Recent Posting Jobs. No Meta creation occurs while reading status.
- Retry only FAILED jobs whose unchanged request is retained locally. Completed
  IDs are reconciled by the existing service. Ambiguous outcomes are not replayed.
- Preserve the existing Ads Manager link, campaign/ad-set/ad details and paused
  verification. Existing-target campaigns/ad sets retain their actual status.

## Changed production files

- `ads_posting_page.py`: shared job submission, result restoration and history actions.
- `ads_posting_progress.py`: shared progress, terminal results and retry controls.
- `meta_posting_jobs.py`: bounded executor and job snapshots over the existing ledger.
- `meta_posting_service.py`: atomic reservation/read methods and reservation hydration.

No migration, new infrastructure, dependency, deployment, activation or production
Meta operation was performed. Existing posting migrations must already be applied.

## Verification

217 unittest cases passed, including existing posting, carousel, saved-package
handoff, collection diagnostics and template-copy regressions. Added tests cover
background submission, duplicate suppression across job managers, confirmed paused
counts, uncertain outcomes, validation errors, partial retries, durable results,
and UI restoration. SQL tests use the real ledger migrations in disposable PGlite
PostgreSQL with the actual `SupabasePostingStore` SQL and a mocked Meta client.

Chrome/Playwright against the mocked Streamlit fixture verified immediate progress,
refresh during work, partial failure, retry, completed result restoration, one
progress bar, no JavaScript errors and no horizontal overflow at 390px. Observed
click-to-progress was **123ms** locally; this is not a production latency claim.
Python compilation and `git diff --check` passed. This Streamlit application has no
separate frontend production build or configured type-check/lint target.

Reproduce (separate terminals, repository root):

```powershell
node tests/meta_posting_postgres_server.mjs
$env:META_POSTING_SQL_TEST='1'
.venv/Scripts/python.exe -m unittest tests.test_meta_posting_jobs tests.test_meta_posting_jobs_sql tests.test_meta_posting_progress

$env:META_POSTING_UI_FIXTURE='1'
.venv/Scripts/python.exe -m streamlit run tests/meta_posting_progress_fixture.py --server.headless true --server.address 127.0.0.1 --server.port 8891 --browser.gatherUsageStats false
# Against a fresh fixture process, with Playwright available to Node:
node tests/meta_posting_progress_browser.cjs
```

## Limits

The ledger and created IDs survive process restarts. Execution/input buffers do
not: an interrupted server process is held for reconciliation rather than blindly
replaying a potentially accepted Meta request. At most two jobs execute and eight
requests are retained per process; older finished requests may lose one-click retry
and require the original inputs through posting setup. Browser refresh/navigation
does not have this limitation. Opening history or the job URL remains available.

Live Meta latency, provider permissions and deployment behaviour were not tested.
Tests made no real campaigns, ad sets, Instant Experiences or ads.
