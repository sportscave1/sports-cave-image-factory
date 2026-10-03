# Automation preview production-loading repair

## Evidence and cause boundary

Read-only checks against the canonical deployed host
`sports-cave-image-factory.onrender.com` returned HTTP 200 for both stable preview/
size HTML entrypoints, preview.js, and the middle editor HTML/JS/CSS. Normalized
deployed bytes matched tracked local files. No CSP or X-Frame-Options header was
returned on those asset responses. The files are tracked, declarations use local
`__file__` paths, and no frontend development URL or npm build is required.

Thus missing build output was not reproduced. The screenshot's warning means the
frontend did not complete Streamlit's ready handshake, not necessarily an HTTP
asset failure. The old preview.js called `parent.addEventListener` before its
ready signal; the middle editor assigned `parent.scCampaignGoToSection` before
its ready signal. These accesses fail when parent access is restricted.

A controlled opaque-origin iframe reproduced a SecurityError at the editor parent
assignment and zero ready signals. With guarded optional parent hooks it produces
one ready signal and no exceptions. The analogous preview/size parent-event-listener
dependency has been removed entirely. The original authenticated production
browser's console/origin policy was not available; do not claim its particular
restriction, proxy issue or cached browser state was conclusively identified.

## Production-safe implementation

- `crm_abandoned_checkout_ui.automation_canvas` uses built-in Streamlit HTML iframe
  rendering, with desktop/mobile widths, bounded height, scrolling and isolated
  email CSS. No separately registered preview frontend, asset URL or bundle.
- `crm_email_size_ui.automation_size_meter` uses native `st.html` to display the
  report computed from the same final message. It lives in the preview fragment
  so content edits update it without an external-container mutation or JS bridge.
- Removed both old declarations and the unused `components/crm_automation_preview`
  HTML/JS files. The middle section editor still requires its existing tracked
  release assets; optional parent-window hooks cannot abort initialization.
- Pinned checkout and bounded hydration/output caches remain. Device/copy/Save
  actions do not fetch checkout data. Identical native iframe srcdoc remains
  unchanged; no transient digest/key is sent to an external frontend.
- Only pending initial lookup gets a one-second completion fragment. One completion
  app rerun removes that timer. Explicit refresh waits up to ten seconds for its
  existing bounded background lookup; a still-pending lookup uses the same temporary
  completion mechanism. Settled editors do not poll or chase cache expiry.
- Last-good preview is retained after rendering errors; a first-render failure
  shows compact app-level advice and logs the exception class without email HTML,
  customer data or token values. No permanent infrastructure skeleton.
- Preview-only style compilation recovery uses default checkout styling over
  hydrated markup, which still passes normal production-render sanitization.
  Warning metadata stays outside the campaign document/schema. Strict live
  compilation/publication/enrollment isolation is unchanged.

## Pipeline check (synthetic data only)

| Stage | Result |
| --- | --- |
| Editable template | 1,941 characters; marker present |
| Native checkout markup | 781 characters |
| Compiled middle markup | 2,400 characters |
| Sanitized middle markup | 2,327 characters |
| Final email | 6,417 characters / 6,421 UTF-8 bytes |
| Digest | 64 characters; marker absent from final email |

This pipeline produced non-empty HTML. It did not reproduce a CSS/sanitizer cause
for the component loading screenshot. Injected compiler failure renders a visible
default-styled preview; the same injected failure raises on the strict live path.

## Verification

- 141 Python automation/email/checkout/size/tracking/Campaign regression tests passed,
  including stopping a completed lookup timer after first-render failure.
- 28 additional shared composer/sections/image/JSON-boundary tests passed.
- ASGI smoke uses Streamlit's production-style `App` under Uvicorn, with no frontend
  dev server, isolated PostgreSQL and mocked external APIs. Requests to both old
  preview/size component paths are deliberately blocked; zero requests occur.
- 90 seconds idle plus a slow global rerun: preview/size stay visible, opacity stays
  1, zero additional Shopify requests, hydrations, iframe remounts/loads or image
  requests; scroll retained. Save/device/same/changed/failed refresh checks pass.
- Legacy real/sample fallback browser tests pass: 60-second idle stability,
  20-character edit produces one update, no extra checkout lookup, visible size,
  preserved surrounding HTML and responsive editor/email viewport checks.
- Master Edit/Save/Use/Reset and draft independence pass. White/gold variant and
  CTA styling still respond to authored template CSS, including `!important`.
- Restricted-origin editor bootstrap, sorting, acknowledgement queue, pending edits,
  catalogue copy/CTA debounce, history, image controls and section-navigation JS
  tests pass. Compilation, JS syntax and `git diff --check` pass.

No live email, production data write, commit, push or deployment was performed.
Authenticated production UI verification after deployment remains necessary.

## Files

Runtime: `crm_abandoned_checkout.py`, `crm_abandoned_checkout_ui.py`,
`crm_automation_store.py`, `crm_automation_ui.py`, `crm_checkout_preview.py`,
`crm_email_size_ui.py`, `components/crm_sections/composer.js`.

Removed: `components/crm_automation_preview/index.html`,
`components/crm_automation_preview/preview.js`.

Tests: `tests/fixtures/crm_automation_preview_server.py`,
`tests/test_crm_component_origin_ui.cjs`,
`tests/test_crm_automation_preview_stability.py`, `tests/test_crm_automation_ui.py`,
`tests/test_crm_automation_pinned_preview_ui.cjs`,
`tests/test_crm_checkout_preview_fallback_ui.cjs`,
`tests/test_crm_checkout_template_styles_ui.cjs`,
`tests/test_crm_sections_component.cjs`, `tests/test_crm_test_sections.cjs`.

Evidence: this report and regenerated synthetic real/sample/template screenshots.
