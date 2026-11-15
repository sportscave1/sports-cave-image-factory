# Automation editor navigation fix

Implemented locally; no deployment, schema migration, scheduler change or customer sends.

## Causes verified

- `workspace()` rendered the complete overview before opening the editor dialog. Its dashboard components, read fragments and refresh controls remained mounted underneath the editor. Browser frame sampling reproduced both surfaces being present throughout navigation.
- Overview styles lived in that changing subtree. Streamlit replaces elements by delta position during reruns; route-specific content and styles were not given an explicit replacement boundary. This left old content available during progressive rendering.
- BaseWeb applied separate 400 ms opacity transitions to the dialog and its parent, plus a transform transition. Computed-style inspection and animation inspection confirmed this, rather than a missing JavaScript chunk or React hydration error.
- Icons depended entirely on stylesheet dimensions. Giant icons were **not reproduced** in the local baseline; intrinsic image dimensions now prevent that particular fallback even without the stylesheet.
- Initial composer rendering repeated reads of the same automation and unnecessarily requested another toolbar refresh even when no content changed.

## Changes

- `crm_automation_ui.py`: stable critical-style location and route placeholder; explicitly remove overview before editor reads; retain overview cache for Back; render the existing dialog before its essential read; compact loading/error/retry states; remove only this dialog's entrance transitions without overriding opacity or visibility; pass the already-read record through initialization; defer composer imports until an email is selected; avoid redundant mount-time toolbar refresh.
- `crm_automation_store.py`: optional already-read row for normalization and draft extraction; copy before editing and validate matching identity. Independent toolbar interactions still read fresh backend state. No new cross-request data cache.
- `crm_automation_home.py`: intrinsic 21×21 icon dimensions; avoid duplicate stylesheet emission when the route already owns the styles.
- `tests/test_crm_automation_navigation.py`: route isolation, cache retention, read reuse, copy isolation, identity validation and icon dimensions.
- `tests/test_crm_automation_navigation_ui.cjs`: per-animation-frame inspection; cold/warm/throttled navigation; back/direct refresh; multiple flows and steps; repeated clicks; tabs; resizing; delayed/failed reads with retry.
- `tests/fixtures/crm_automation_preview.py`: synthetic one-shot delayed/failing editor reads.
- `tests/fixtures/crm_automation_navigation_baseline.py`: isolated comparison against revision `edbeb70`, loaded once per process without modifying the checkout.
- `tests/test_crm_flow_builder_ui.cjs`: assert overview unmounts while editing and returns on Back.

The existing template and activity tabs already load their contents on demand; this remains unchanged. Preview hydration already runs independently and retains its existing cache. No dashboard analytics, delivery history or activity reads are started by the editor route. All step documents remain in the existing single draft JSON record; this change does not introduce a second storage model or pretend to fetch those separately.

## Controlled local measurements

Headless installed Chrome, Windows, 1440×1000; identical disposable three-flow PostgreSQL fixtures; external browser and provider requests blocked. “Cold” starts with a new browser context and opens the overview before the editor. “Warm” reopens after Back. Throttling combines 150 ms network latency, 200 KB/s download, 100 KB/s upload and 4× CPU slowdown.

Measured from the browser automation's click invocation to the first sampled frame containing the toolbar. Single observations, not production percentiles; timings vary between runs.

| Scenario | Before | After | Dashboard/editor overlap frames before → after | Faded frames before → after |
|---|---:|---:|---:|---:|
| Cold | 306 ms | 106 ms | 25 → 0 | 19 → 0 |
| Warm | 188 ms | 332 ms | 22 → 0 | 19 → 0 |
| Throttled | 1,007 ms | 495 ms | 28 → 0 | 5 → 0 |

Raw results: `tmp/navigation-controlled-before.json` and `tmp/navigation-controlled-after.json`. Frame sampling found zero oversized icons or JavaScript page errors in either run. The warm 100–200 ms target was not achieved in this sample: Back now remounts the overview using retained data rather than leaving it under the dialog. No claim is made that every navigation became faster.

## Verification

- 109 targeted Python tests passed, including SQL-backed publishing/versioning, native automations, flow builder, section names, checkout sections, navigation, loading and production entrypoint import contracts.
- Navigation browser suite passed, including normal/cold/warm/throttled paths, direct refresh, Settings/Editor/Templates, switching steps and flows, repeated clicks, 320/390/750/1000 px widths, a two-second essential-read delay and recovery from a synthetic failure.
- Existing compact-toolbar browser suite passed: draft edits, refresh, paused publication to v2, resume, test controls, responsive layout and Back. Only synthetic publication jobs were processed; no customer emails were sent.
- Existing Flow Builder browser suite passed: add, name, enable/disable, reorder, duplicate, delete, timing, simulation, activity, composer, Back and responsive widths.
- Python compilation, JavaScript syntax and `git diff --check` passed.
- One additional, pre-existing source-string assertion fails in `tests.test_crm_automation_preview_stability.PreviewStabilityTests.test_automation_only_polling_and_debounce`: it expects the removed `not any(s['type']==BLOCK` implementation in `crm_section_ui.py`. That module was unchanged by this task; the new editable checkout implementation is covered by the passing checkout suites.

No standalone application frontend build or type-check command is configured. Render's build installs `requirements.txt`; dependency installation/deployment was not performed. Offline production entrypoint import/build-contract tests and Python compilation passed. The authenticated production desktop shell and actual production network latency were not tested; validate there through the normal deployment workflow.
