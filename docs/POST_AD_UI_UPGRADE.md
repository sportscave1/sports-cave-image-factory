Post Ad UI and progress upgrade — local verification, 9 October 2026

Implemented locally. No commit, push, deployment, production database change or real Meta creation was performed. The posting engine, request construction, campaign structures, validation, defaults and PAUSED creation rules are unchanged.

The Post Ad interface now has scoped off-white styling, restrained gold segmented selections, a compact heading with Refresh Meta beside it, paired mode/type controls, compact upload rows, two-column product/targeting controls, image/copy columns for each creative, smaller review previews and grouped review rows. Every final creation path uses **Create Ad**. Carousel still has five ordered cards and five independent primary-text variations; Instant Experience still creates three route-specific ads.

The normal page no longer renders the green connection status, Advanced Meta Diagnostics or Recent Posting jobs. Diagnostic service functions, validate-only checks, template-copy troubleshooting functions, recent-job reader, posting ledger, history APIs and recovery logic remain. Genuine connection failures still block posting and provide refresh/credential guidance. Full-resolution image data and existing 320px preview generation remain unchanged.

Changed application files:

- `ads_posting_page.py`: scoped page wrapper, layout, review/success summary, exact action label, retained widget values, deferred product-helper import and indexed product lookup. Rebuilds the selector when supplied product rows change.
- `ads_posting_style.py`: Post Ad-only CSS and narrow-screen fallback.
- `ads_posting_progress.py`: optional compact result presentation, verification-aware progress, elapsed/current-operation feedback, durable object checkpoint indicators, status-read recovery and explicit unknown-outcome messages.
- `meta_posting_jobs.py`: observational operation timestamps; no changes to job reservation, retries, resource creation or reconciliation.

Changed/added verification files: `tests/test_post_ad_compact.py`, `tests/test_meta_posting.py`, `tests/test_meta_posting_jobs.py`, `tests/test_meta_collection_diagnostics.py`, `tests/test_meta_collection_template_copy.py`, `tests/meta_posting_progress_fixture.py`, `tests/meta_posting_progress_browser.cjs`, `tests/fixtures/post_ad_compact_preview.py`, `tests/post_ad_layout_browser.cjs`, and `scripts/benchmark_post_ad.py`. Existing UI assertions were updated only where this request intentionally changes visible controls.

Progress uses the existing bounded background executor and durable submission UUID. The UI shows validation immediately beside the action, then follows that same job in a two-second Streamlit fragment. The job UUID remains in the URL for reload recovery. Live operation text comes from existing service callbacks; success ticks come from saved object IDs, not guessed operation completion. The progress bar counts confirmed paused ads plus final verification, and cannot reach completion from saved IDs alone. It is not an estimate of elapsed time remaining.

The existing client keeps 30-second read and 45-second write request timeouts. No automatic write retry was added. Five consecutive status-read failures pause automatic polling and expose a read-only Retry status action. An operation lasting over 90 seconds shows an explicit slow/unknown-outcome explanation; a checkpoint without a local worker warns that another worker may still be active. Neither condition launches another job. A process restart retains the ledger and URL identity, but cannot recover in-memory elapsed-time information or the original worker.

Safe retry continues through the same reservation and original request. Existing IDs are reconciled and reused. FAILED jobs can offer Retry incomplete steps only while their request is retained locally; AMBIGUOUS outcomes are not automatically replayed. Mocked partial-failure tests confirm one campaign, one ad set and three ads after recovery, with the original first ad retained. This is evidence for duplicate prevention within the existing job protocol, not a claim that manually starting an unrelated new submission can never create similar ads.

Performance investigation found a substantial eager import of the large New Ads module before the heading/job monitor could render. Its product helpers are now imported on demand. Existing Meta metadata/session caches, CSV fingerprinting and uploaded-image reuse were already present and were retained. There is no new network-data cache or stale-data policy. The form still loads required references synchronously; real Meta/Edition Ops network latency was not measured or changed.

| Measurement | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Post Ad module startup, median of five fresh processes with Streamlit preloaded | 1,874.6 ms | 277.5 ms | 85.2% lower blocking import cost before first page output/job monitoring |
| Offline browser full form ready, first 1440px navigation | 1,585 ms | 1,552 ms | Single samples; no proven full-form loading gain |
| Offline browser ready, subsequent 1280px navigation | 273 ms | 278 ms | Essentially unchanged; local timing noise |
| AppTest initial renderer median, six warm-process samples | 12.43 ms | 13.78 ms | Small layout overhead; not faster |
| AppTest rerender median | 12.72 ms | 14.40 ms | Small layout overhead; not faster |
| Indexed product selection, 10,000-row synthetic stress test | 0.3167 ms | 0.00053 ms | Removes repeated linear scanning; this is a microbenchmark, not end-to-end speed |
| Click to live progress in mocked browser | — | 114 ms | Job identity restored on reload |

The 10,000-row stress test exceeds the current catalog reader's 1,500-row limit; its purpose is to isolate lookup scaling. No production latency or sustained throughput claims are made from it. Cold total renderer times include test imports and OS file caching and are retained in raw evidence, but are not treated as a causal speed comparison.

Settled empty Instant Experience form heights in the same offline fixture:

| Viewport width | Before | After | Reduction |
| --- | ---: | ---: | ---: |
| 1440px | 3148px | 2055px | 34.7% |
| 1280px | 3173px | 2081px | 34.4% |
| 768px | 3218px | 2125px | 34.0% |
| 390px | 3884px | 3422px | 11.9% |

No horizontal overflow or browser exceptions occurred at these widths in either Instant Experience or Carousel. All five carousel cards, six upload controls including CSV, and five primary-text controls remained visible in the DOM. Desktop compaction is approximately the lower end of the requested range; small screens deliberately retain single-column readability. These measurements use the real page renderer with synthetic metadata, without the full authenticated OS navigation shell or long populated copy.

269 focused Python tests passed. Coverage includes form fields/modes, CSV hydration, creative uploads, state preservation through a hidden form, unchanged campaign structures, three-ad and carousel creation, paused status, real service callbacks, final-verification gating, partial results, same-job retry, ambiguous outcomes, rate limiting, request timeouts and network loss. Browser tests passed for responsive layout, partial failure/retry, saved job URL restoration, verified success, Ads Manager link and zero horizontal overflow. `git diff --check` passed.

Reproduce Python verification with the repository virtual environment:

```powershell
$env:TEMP=(Resolve-Path tmp).Path
$env:TMP=$env:TEMP
.venv/Scripts/python.exe -m unittest tests.test_post_ad_compact tests.test_meta_posting tests.test_meta_carousel_posting tests.test_meta_posting_jobs tests.test_meta_posting_progress tests.test_posting_import_csv tests.test_ads_posting_handoff tests.test_meta_collection_diagnostics tests.test_meta_collection_template_copy
.venv/Scripts/python.exe scripts/benchmark_post_ad.py
```

The browser layout runner targets only loopback port 8537; serve `tests/fixtures/post_ad_compact_preview.py` there. The progress runner targets loopback port 8891; serve `tests/meta_posting_progress_fixture.py` with `META_POSTING_UI_FIXTURE=1` and `POST_AD_COMPACT_PROGRESS=1`, and set the latter for the Node runner too. Both browser scripts use Playwright with installed Chrome. Fixtures mock Meta/storage and prohibit external HTTP calls.

Raw timing evidence and screenshots are in [post-ad-ui-evidence](post-ad-ui-evidence/). Remaining limitations are unmeasured production/network performance, no authenticated full-shell browser run, session-only preservation of draft upload bytes (not cross-browser draft persistence), and manual reconciliation after a lost worker or ambiguous write. These limitations do not trigger automatic duplicate submissions.
