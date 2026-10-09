# Email automation thumbnails

## Root cause
The former preview was not an image asset. An IntersectionObserver clicked hidden Streamlit buttons and kept one active DOM node until it disconnected. A mount-time click could be lost while the trigger stayed connected; the queue then stalled indefinitely. The offline browser reproduction had 12 grey triggers; manually clicking the already-mounted first control loaded five previews immediately. The implementation also used draft documents and current settings, not immutable published versions.

## Implementation
- `crm_flow_thumbnail.py`: visible-first, bounded retry controller, fixed 76x100 display area, lazy WebP images, explicit LIVE version/DRAFT labels, broken-image fallback and on-demand full preview. No hidden full-email iframes or page-thread HTML rendering.
- `crm_thumbnail_cache.py`: bounded background queue, subprocess deadline, local private disk cache (4096 assets), atomic writes and duplicate suppression. Errors never change publication/sending state.
- `crm_thumbnail_store.py`: private durable assets and three-minute fenced leases in the existing `crm_runtime_state` table. Worker/web instances share assets; restart recovery does not regenerate a valid asset. No migration. Local disk hits make no database queries; shared hits use one indexed read; fresh on-demand generation uses a state read, lease claim, exact-version template read and asset write, all off the page thread. Publication prewarming already has the frozen content and avoids that template read.
- `crm_thumbnail_render.py`: isolated Chromium process, 600x790 source capture reduced to 240x316 WebP. The simple fixture produces 3684 bytes; complex fixtures observed 3388-6430 bytes. Playwright is pinned. A missing Chromium binary is installed only by the bounded background renderer; deployment readiness logs identify unsupported runtime dependencies. It never installs or renders on navigation.
- `crm_automation_publication.py`: best-effort prewarming after a successful transaction, for queued and direct publishing. Sending and authoritative publication selection are unchanged.
- `sports_cave_server.py`: non-blocking synthetic renderer readiness check on Render, without database/customer/provider access.

Keys include renderer revision, automation ID, immutable template ID and publication version. Draft-only stages use a separate revision/content hash. Edited drafts cannot replace live images. Every stage uses the same code, including 4, 5, 6 and later stages, archived and disabled flows. Legacy missing assets are recovered automatically when visible.

The database assets have existing server-only permissions and are never given public URLs. WebP bytes are delivered within the authenticated Streamlit session. Generated previews use neutral example data, JavaScript-disabled Chromium and a deny-by-default network policy. Only bounded public Shopify raster assets and the deployment-owned public email asset base are allowed; signed/query-token URLs, tracking endpoints, redirects and other requests are blocked. Full HTML preview loads only on an explicit click.

## Verification
Disposable loopback PostgreSQL, mocked Shopify/Resend and a synthetic 12-stage browser fixture only. No customer emails were sent. Desktop (1440px) and narrow (390px) checks cover viewport lazy loading, later-stage recovery, real WebPs, no hidden preview iframes, refresh, full-preview click and broken-image fallback. Regression tests cover frozen versions, drafts, stages 4-6, missing/corrupt cache recovery, nonblocking deduplication, cross-service leases, stale claims, restart reuse and unchanged delivery/analytics counts.

Single-run local Chromium comparison, same 12-stage fixture:

| Measurement | Before | After |
| --- | ---: | ---: |
| First navigation: stage controls visible | 1038 ms | 454 ms |
| Warm navigation: stage controls visible | 429 ms | 327 ms |
| First thumbnail, fresh generated asset | HTML at 1048 ms | WebP at 3837 ms |
| Warm navigation thumbnail | stalled >20 s | 398 ms |

Fresh generation is intentionally asynchronous. These are synthetic local observations, not production latency or statistical performance guarantees. A separate cached-assets run measured initial controls 430/398 ms and warm controls 449/358 ms (before/after). Original HTML rendering could work on one load and stall on the next.

One broader existing test (`test_automation_only_polling_and_debounce`) fails on a source-string assertion in unchanged `crm_section_ui.py`; it is outside this fix. Final focused release suite: **106 tests passed on Python 3.12.8** against disposable PostgreSQL, including the current live-publication repair. Real Chromium rendered WebPs on both Python 3.14 and 3.12. Browser acceptance passed with no page exceptions.

## Production status
Pending rollout verification. The production browser tool failed to initialize with `helper_unknown_error: setup refresh had errors`; SSH access returned `Permission denied (publickey)`. These prevent authenticated visual verification unless access recovers. Render deployment and synthetic renderer readiness can still be checked independently. No Blueprint sync, topology change, flow activation, manual publication or live email send is part of this release.
