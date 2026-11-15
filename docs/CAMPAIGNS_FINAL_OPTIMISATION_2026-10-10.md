# Campaigns V7 / V7.1 / V8 final local optimisation

10 October 2026. **Local changes only. No commit, push, deployment, production migration, production record mutation or email delivery.** Work is in `.tmp-full-system-release`; the original dirty working copy and existing release-report edits were preserved. HEAD remains `7391a7206048cc5d7006691b0e944bf06e6b03c9`.

## Deployed baseline

Read-only Render checks confirmed the same consolidated commit LIVE on all four existing services: `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`), `sports-cave-os-webhooks`, `sports-cave-seo-worker`, and `sports-cave-seo-daily-sync`. No cron was manually invoked. Read-only Supabase checks on the canonical project confirmed the Flow-test and durable-preparation migrations, preparation table and enabled publication trigger. No new migration is required or proposed.

Reviewed the October 10 full-system release report, `CAMPAIGNS_V7_1_PREMIUM_UI_SCHEDULE_MANAGEMENT.md`, `CAMPAIGN_SCHEDULING_V8_RELIABILITY_TIMEZONE_REPAIR.md`, `CAMPAIGN_AUDIENCE_PREPARATION.md` and `EMAIL_EDITOR_V6_PERFORMANCE_AND_CUSTOMISATION.md`. Older pre-deployment statements in those reports are historical; the consolidated commit and live service checks establish this task's baseline. An exact `git archive` of that commit supplied the comparison source, without resetting either checkout.

## Root causes and local fixes

1. **Immutable detail routing did editor work first.** A cold scheduled detail performed 10 database reads: compliance, branding, two header/footer reads, recovery lookup, campaign existence, full draft, recovery eligibility, full campaign and progress. It also transformed/copied the authoring document and repeatedly emitted composer CSS before showing the operational view. The new read-only route fetches bounded campaign/preparation metadata and one authoritative progress snapshot. It does not fetch draft HTML, initialise editor settings or write recovery pointers. Preview content remains lazy. Warm editable drafts retain their existing path; archived draft opening and dirty-draft leave protection are preserved.
2. **Two Back controls in the full workspace.** The operational view now allows its own Back button to be omitted when the workspace already supplies one. The workspace button retains normal fragment navigation.
3. **Menu dismissal could depend on native overlay focus/event timing.** An Edge 320px outside-click failure was reproduced after keyboard cycling. Streamlit gives the popover itself `role=dialog`; a broad modal guard incorrectly bypassed the initial fallback. The final helper distinguishes an actual Streamlit modal, installs one capture listener for Escape and one for outside pointer-down, uses the existing native trigger to close, and restores trigger focus only for Escape. It leaves outside actions and real modal interactions intact. No custom replacement menu or server round trip was introduced. The historical Escape failure was not deterministically reproduced in the original baseline; do not claim a proven internal Edge/browser defect.
4. **Refresh could interrupt an open control.** Detail polling now pauses for open dialogs/popovers as well as hidden documents. Existing bounded cache, active/idle cadence and terminal stopping remain. Countdown is still browser-local and generates no per-second database requests.
5. **Empty progress presentation.** Empty terminal details and unstarted Home queues no longer render empty progress bars; meaningful counts and explicit Queued/Preparing status remain.
6. **Regression harness drift.** Streamlit 1.65 changed AppTest query-parameter shapes, session-state access and relative fixture resolution. Tests now support the deployed runtime without weakening their identity, duplicate-send or recovery assertions. Leftover synthetic campaigns initially contaminated worker-selection tests; recreating only the disposable test database resolved that isolation issue. No production sending logic was changed to satisfy tests.

## Measurements

All figures below are **p50 / p95 milliseconds**, normally 20 measured samples after warm-up. Raw samples are in `campaign-final-evidence/`. Browser figures are local Chrome/Edge against loopback fixtures with external HTTP blocked, not production end-to-end results. Native SQL measurements use independent real PostgreSQL connections and the same synthetic 1,085-recipient scheduled campaign. There is no injected latency in the reported native SQL measurements.

| Measurement | Before | After | Interpretation |
| --- | ---: | ---: | --- |
| Campaigns Home initial load, Chrome loopback | 2055 / 3057 | 2012 / 3118 | No demonstrated improvement; tail slightly higher |
| Campaign detail initial load, native SQL workspace render | 1004 / 1089 | 739 / 837 | 26% / 23% lower in this local sample |
| Campaign detail initial load, Chrome zero-latency mock | 3029 / 3096 | 3011 / 3142 | No demonstrated browser improvement |
| Warm Home render, AppTest with mocked reads | 440 / 508 | 472 / 584 | No improvement claim; this is not browser navigation |
| Warm detail rerender, native SQL | 545 / 580 | 465 / 552 | 15% lower median; small p95 difference is not conclusive |
| Three-dot menu opening | See final interaction table below | See below | Native opening; no query or WebSocket request |
| Schedule dialog opening | See final interaction table below | See below | Measured from an idle page; cancellation rerun settled between samples |
| Schedule save, real local SQL | Separate baseline not collected; implementation unchanged | 100 / 136 | Same immutable/fenced schedule operation; no speed claim |
| One-click durable acceptance, real local SQL, 3 synthetic recipients | Separate baseline not collected; implementation unchanged | 35 / 37 | Acceptance only; excludes prior review/background verification/browser navigation |
| Progress refresh, real local SQL, 1,085 recipients | Separate baseline not collected; implementation unchanged | 40 / 44 | One aggregate read; no provider/Shopify request |

The full native-SQL detail path drops **10 to 2 reads cold**, and **4 to 1 additional reads warm** with the existing two-second progress cache. The profile records about 267 ms across the old database calls versus 70 ms for the new two calls. PostgreSQL EXPLAIN ANALYZE measured only 0.089 ms for metadata and 1.518 ms for the progress query itself: repeated connection/driver/round-trip overhead, not a missing SQL index, dominated this local case. Returned-value sizes in the profile are Python representation sizes, not wire-byte measurements.

The sidebar fixture spends about 400 ms reading/parsing the large application source and constructing the sidebar. That AST extraction is a **test-fixture cost**, not evidence that production repeats an AST parse. AppTest timing includes script startup/rendering but not an authenticated production browser session. The browser fixture shows approximately three seconds for detail despite much faster isolated rendering; eliminating database round trips alone does not prove that whole-app browser startup is fixed. Production stage logs were unavailable, and WAN latency, production startup and full authenticated navigation were not independently decomposed. Do not subtract server timings from a different browser run and label the remainder network latency.

| Local browser interaction | Before p50 / p95 ms | After p50 / p95 ms |
| --- | ---: | ---: |
| chrome menu | 30 / 48 | 31 / 48 |
| msedge menu | 29 / 39 | 31 / 55 |
| chrome schedule dialog | 302 / 323 | 304 / 324 |
| msedge schedule dialog | 345 / 391 | 341 / 368 |

No meaningful opening-speed improvement is claimed. An earlier dialog benchmark mixed the next opening with the prior Cancel action's full rerun, producing 0.9-second tails. The corrected benchmark explicitly waits for the fixture run counter to advance after cancellation. Its final figures above are from the final menu implementation; the earlier samples are retained separately as invalid for isolated opening comparisons. Normal cancel reruns remain existing behaviour.

## Reliability and regression evidence

- **335 relevant regressions pass** on a freshly recreated disposable PostgreSQL database; external requests are blocked. Coverage includes V7/V7.1/V8, preparation, delivery batching/retries/uncertainty, consent/suppression, tracking, history, recovery and Home caches/progress.
- **12 real concurrent PostgreSQL tests pass**, using simultaneous transactions and distinct backend connections: administrator/administrator stale revision, worker claim/preparation versus edit or Send Now, outage gate, rollback/failure, retries and duplicate operations. Frozen recipient IDs/payloads remain stable and no early/duplicate dispatch is authorised.
- **48 targeted routing/Home/recovery checks pass** after the navigation adjustment; a final **11-test routing/first-paint pass** includes archived draft preservation and fail-closed database errors. These overlap the main suite and are not advertised as additional unique regressions.
- Chrome and Edge Home/detail acceptance passes at **1440, 820, 390 and 320 px**: 16 combinations, no horizontal overflow, correct menu positioning, schedule confirmation/save, Send Now acknowledgement, ticking countdown, no duplicated amendments or unexpected document navigation. The 320px journeys were repeated after empty-bar changes.
- The final dedicated menu run passes **192 Escape cycles, 48 outside-click cycles and 64 Tab/Shift+Tab cycles**, across both browsers and all four widths, with **zero menu-generated WebSocket requests**, one menu instance, focus restoration and no exceptions.
- V6 editor browser checks pass in Chrome and Edge for rapid switch, sibling isolation, exact HTML reopen, explicit save and browser reload. Catalogue picker and Flow acceptance from the consolidated release is reused because their implementation is unchanged; it was not represented as a fresh complete rerun.

The durable-acceptance tests cover repeated clicks, separate application sessions, lost commit acknowledgement recovering the original operation, no recipient/provider verification during acceptance, lease expiry/restart fencing, immutable publication and consent changes during preparation. A receipt means Preparing, not Sent. Preparing remains explicitly awaiting verification; it does not assert a worker is actively sending. SENT remains an authoritative stored worker outcome, and provider acceptance is labelled submitted rather than delivered.

Scheduling tests retain stale-revision rejection, operation receipts, row locking, untouched recipient identities, postponement/no early dispatch, attempted/accepted/uncertain delivery immutability, DST gaps/folds and recipient-local timezone validation. No queue-publishing, worker, consent, Resend or timezone algorithm was changed in this pass.

## Bathurst protection and historical remediation proposal

No Bathurst geography, recipient schedule, campaign state, delivery record, recovery or resend action was taken. The prior read-only investigation remains the evidence: 1,041 Darwin assignments have the legacy `address_timezone` label, 43 have UTC fallback and one has London. The legacy resolver accepted address or customer timezone before geography and used the same label for both. Frozen records do not retain enough original geography to prove those Darwin assignments wrong. UTC fallback is not a verified location, and current customer geography cannot prove historical geography. Strict new-schedule tests reject incomplete or contradictory country/state/postcode/timezone evidence and accept consistent NT/Darwin evidence.

A separate historical process would first collect dated source evidence, classify consistent/contradictory/unprovable rows, and produce a dry-run comparison preserving frozen identity/content hashes. A human would review only proven corrections and explicitly authorise a separately designed remediation. Current addresses alone are insufficient, and neither automatic frozen-schedule rewriting nor release/recovery of overdue, blocked or uncertain recipients is authorised. This pass supplies no automatic remediation mechanism.

## Files and release limits

Runtime: `crm_campaign_page.py`, `crm_campaign_progress_ui.py`, `crm_campaign_home.py`, new `crm_campaign_menu.py`.

Tests/harness: `tests/test_campaign_final.py`, `tests/test_campaign_hardening.py`, `tests/test_crm_campaign_first_paint.py`, `tests/test_crm_send_flow.py`, `tests/test_crm_send_progress.py`, `tests/check_campaign_hardening_browser.py`, `tests/check_campaign_final_menu.py`, `tests/check_campaign_final_browser.py`, `tests/fixtures/campaign_final_preview.py`, `tests/benchmark_campaign_final.py`, `tests/benchmark_campaign_operations.py`, `tests/profile_campaign_final.py`. This report and its local evidence are new. The already-dirty consolidated release report was not edited by this pass.

**Functional local checks pass; full production readiness is not claimed.** The measured reduction in real local detail reads/rendering is established, but the requested complete authenticated browser startup/warm-navigation p50/p95 target is not established. Home and mock-browser p95 results do not demonstrate an improvement. Original intermittent native Escape behaviour was not deterministically reproduced, although the final scoped handling passed the expanded repeated tests. These are explicit acceptance limits, not successful production checks. All changes remain local for a separately authorised release; production retains the consolidated baseline.
