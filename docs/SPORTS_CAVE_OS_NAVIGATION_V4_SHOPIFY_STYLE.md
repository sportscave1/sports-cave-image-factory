# Sports Cave OS Navigation V4: local performance and release validation

Validated locally on 10 October 2026. The 244px compact sidebar, existing menu order, typography, icons, gold highlighting, badge layout and touch targets are preserved. No commit, push, merge or deployment was performed.

## Release status and limits

The isolated navigation patch applies cleanly to GitHub main **02c81f1d4dcb2c572e63d8aa4004766d458b634d**, including the concurrent table presentation release. The compact V4 styles are already on main. This release contains only the additional navigation fixes and their two tests, not unrelated working-tree changes.

**Full production acceptance is incomplete.** Browser measurements used actual production sidebar, route/history/latest-intent helpers and top-bar controller with offline destination bodies. They do not measure authenticated Orders, Edition Ops, Mockups, Design Studio, Meta Review, Analytics, Email or Automations page initialization, API/database latency or customer content. No live-page throughput speedup is claimed. Chrome and Edge are installed, but native browser control stopped because its policy layer could not determine the browser URL; testing continued in the Codex in-app browser. This is not Chrome/Edge verification.

## Confirmed work removed

- Clicking an already-selected disclosure now reruns the sidebar fragment instead of initializing the whole destination again. Route-changing clicks still use an app rerun. The fallback preserves AppTest/full-script operation where fragment scope is unavailable.
- Same-route suppression still blocks duplicate leaf navigation, but permits a disclosure click to reach the fragment. Route state, permission checks, latest-intent safeguards and draft guards remain in the existing architecture.
- Fragment disclosure state is not unnecessarily reset on every render. Existing route-family forced-open rules remain intact.
- Sidebar width is measured once per observed sidebar node, then updated by ResizeObserver. Identical widths do not rewrite the CSS variable. The timeout fallback remains for environments without ResizeObserver.
- Structural sidebar replacements trigger one coalesced route/badge restoration. Cached notification counts are reapplied without extra API requests; badge insertions do not cause an observer loop. Repeated timer-driven sidebar scans are retained only as a compatibility fallback.

Twenty current Email expansion/collapse clicks left destination render count **2 â†’ 2**. Disclosure response p50/p95 was **199.90 / 213.10ms**, excluding the first click that actually navigated to Email. Orders 4, wall 99 and Email 99+ badges survived the fragment replacements. This demonstrates avoided destination work; it is not a measured full-route speedup.

## Controlled offline AppTest comparison

Independent process trials, five warmups then twenty measured samples per trial, alternating original/compact order AB, BA, AB; three trials and sixty measured samples per variant. Percentiles use pooled samples and nearest-rank p95.

| Variant | Warm p50 | Warm p95 |
| --- | ---: | ---: |
| Original pre-V4 | 381.96ms | 496.66ms |
| Compact V4 | 372.35ms | 433.34ms |

Original trial medians were 418.72, 386.39 and 355.03ms; compact medians 348.04, 390.30 and 364.90ms. The earlier 295.59 â†’ 339.33ms slowdown was not consistently reproduced. These results support substantial measurement variability, not proof that all production overhead is unchanged. The previous cold-start claim is withdrawn.

A ten-sample profile of the old fixture found median AST extraction 282.06ms within 321.76ms AppTest duration. That parsing was test-fixture work, not production application rerun time. The new browser fixture caches extracted production functions. Initial source-cache comparisons and an unapplied width-observer probe were rejected.

## Browser measurements

Final comparison: independent foreground sessions at 1440Ã—900, ten route warmups then twenty measured clicks; two trials in opposite order, compact/current then current/compact. Each cycle visited Orders, Edition Ops, Mockups, Design Studio, Ads, Meta Review, Analytics, Email, Automations and Home. Repeated cycles include returning to pages. Forty measured route completions per variant. Instrumentation spans reruns and separates parent toggles from route-changing clicks. Raw samples and summaries are in `tmp/navigation-v4/acceptance/`.

| Measurement | Compact V4 p50 / p95 ms | Current p50 / p95 ms |
| --- | ---: | ---: |
| Click to pending DOM feedback | 8.65 / 11.10 | 9.35 / 10.60 |
| Click to next feedback animation frame | 22.10 / 106.20 | 22.25 / 92.40 |
| Click to accepted route/epoch | 455.50 / 721.00 | 443.75 / 506.80 |
| Click to visible useful stub content and shell ready | 473.70 / 722.30 | 445.35 / 555.40 |
| Timed Streamlit navigation-helper processing | 40.38 / 68.27 | 38.93 / 42.13 |
| Sidebar portion of processing | 33.29 / 59.02 | 32.62 / 35.07 |

The server interval covers the fixture's production navigation helper/sidebar processing, not the entire Streamlit runtime or real destination initialization. First DOM content can exist underneath the transition overlay; the useful visible-content boundary is shell ready. An animation-frame callback is an approximation of visual feedback, not a compositor presentation timestamp.

Trial ready medians were compact 516.65 and 406.80ms versus current 449.00 and 429.60ms. Earlier original/current runs yielded ready 471.50/620.40ms versus 550.10/715.20ms (59/60 samples), going in the opposite direction. Final pooled results are better, but trial variability and the offline scope prevent a general speed claim.

**Network p50/p95: not independently measured.** Streamlit uses WebSockets; browser elapsed time minus the timed server block also includes queueing, runtime scheduling, DOM rendering and overlay work. It must not be presented as network latency. API/database delays were mocked and are not zero-latency production measurements. No new API calls were added by these fixes.

## Mobile and functional acceptance

The original mobile menu handler worked by keyboard, but at 390px the menu centre hit the overlapping Back button. This was a real shell layout fault, not just a fixture limitation. At widths â‰¤620px, the top bar now uses two rows (100px total) so menu/actions and Back/Forward/Refresh/Files have separate hit areas. Wider mobile remains 56px; desktop remains 64px.

Verified in the in-app browser: pointer and Enter opening, closing via backdrop, navigation to Orders and automatic drawer close, sidebar scrolling (scrollTop changed), desktop/mobile resizing, retained gold highlight and compact icons. Width checks at 320, 390, 430, 750, 820, 1024, 1280, 1366, 1440, 1652 and 1920px retained a 244px sidebar and no document horizontal overflow. The menu centre resolves to the menu button at narrow widths. Full mobile controls including planner were exercised with offline configuration. CSS width token was 244px.

Rapid Orders â†’ Edition Ops â†’ Mockups ended at Mockups. Back returned to Edition Ops and Forward returned to Mockups. Repeated current-page leaf clicks did not increase destination render count. All requested destination labels were reached in the offline browser. Existing route, permission, notification and draft contract tests passed. No unexpected full-page flash was observed in this fixture; this is not a claim about live production page bodies.

![Mobile drawer with separated top-bar controls](../tmp/navigation-v4/acceptance/final-mobile.jpg)

## Regression and release safety

In the fresh main checkout, **104 Python tests completed successfully, including one skipped** (the disposable PostgreSQL-dependent check): navigation V4, sidebar theme, navigation performance/cleanup, email navigation, top bar and order-action notifications. Four Node suites passed: width/fragment-presentation observers, notification badges, history controls and shell request deduplication. Render topology validation passed; no Render configuration was changed. Windows sandbox temp cleanup initially denied access, so the successful isolated suite ran outside that sandbox.

Broader support-email and wall-notification suites did not produce a completed result in the attempted run and are **not counted as passed**. Live destination performance, separate network timing and Chrome/Edge acceptance remain outstanding; the release should not be described as fully production-validated.

`docs/navigation-v4.patch` contains only app.py, components/sports_cave_top_bar/index.html, tests/test_navigation_v4.py and tests/test_navigation_v4_width.cjs. Reports, fixtures, benchmark artifacts, this document and unrelated local work are excluded from the application release.

The manual script verifies the patch SHA256, clones current GitHub main into a new isolated checkout, applies the patch with conflict checks, enforces the exact four-file allowlist, reruns the 104-test suite/Node checks/topology check, then commits and performs a normal push. Concurrent main movement rejects the push rather than overwriting it. It does not stage the shared working tree or create/change a Render service. The push invokes the existing Render auto-deploy configuration; deployment success is not verified locally.

From the repository root, the single manual command is `& .\scripts\deploy_navigation_v4.ps1`. It has been parsed and its pre-commit patch/test steps verified; its commit/push steps were deliberately not run.
