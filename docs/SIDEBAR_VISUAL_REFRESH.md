# Sidebar visual refresh

Presentation-only change. Existing menu entries, order, labels, route IDs, permission checks, callbacks, icons and top-bar logo/branding are unchanged. No Collapse control or quote was added. The earlier CRM work in the working tree was preserved without further edits.

## Implementation

`sidebar_theme.py` is the shared source of sidebar CSS, injected by the existing `app.py::inject_styles`. Replaced the old light sidebar rules rather than scattering overrides through pages. Theme tokens cover charcoal gradient (#151716 to #101211), panel (#272826), hover (#30312e), text (#eeeeeb), muted text (#9b9b95), subtle border and muted gold. Rows are 40px, children 37px, labels 13.5px and existing icons 18px. Shared disclosure/children selectors apply to every navigation family. Active children use gold; their expanded parent remains charcoal. Keyboard focus remains visible. Hidden history-navigation helper wrappers no longer leave empty gaps.

The sidebar remains the existing width and below the existing top-bar brand. It is anchored while the menu scrolls internally, without a horizontal scrollbar. Main content is excluded from every theme selector. Files uses a separate iframe, so its bundled CSS was recoloured to the same palette; launcher JavaScript and destinations are unchanged.

## Behaviour

No new navigation system or callbacks. Existing parent overview navigation, disclosure state and active-child expansion/restoration remain authoritative. This intentionally preserves existing behaviour, including keeping the active route family expanded. CRM Campaigns/Flows/Settings and other families retain their actual existing routes and labels.

## Verification

- Syntax-tree comparison against HEAD: only `inject_styles` changed in app.py; all other functions and all top-level configuration/import/router statements are identical.
- 4 focused sidebar tests passed (scope, no extra controls, child navigation/active restoration, parent/top-level destinations).
- 86 of 87 existing navigation/startup/Files/top-bar/social/analytics regression tests passed.
- One existing stale top-bar test still expects `resetInitialSidebarScroll`, which is absent from the unchanged HEAD top-bar component. No production top-bar JavaScript was modified to satisfy that obsolete assertion.
- Python compilation and git diff --check passed.
- Browser checked at 1366x768, 1440x900 and 1920x1080 using the actual extracted sidebar helpers and CSS in an isolated Streamlit harness. Verified top-level selection, CRM children, refresh restoration, another disclosure family, internal scrolling and no horizontal content overflow. Operational page loaders and production services were deliberately not invoked. Existing logo/top-bar component was not mounted in this isolated harness.
- No database writes, production changes, commits, pushes or deployments were performed.

## Files for this task

app.py; sidebar_theme.py (new); components/files_window_launcher/index.html; tests/sidebar_preview_app.py (new); tests/test_sidebar_theme.py (new); tests/test_sidebar_navigation_cleanup.py; tests/test_navigation_performance.py; tests/test_files_window_launcher.py; tests/test_top_bar.py; docs/SIDEBAR_VISUAL_REFRESH.md.

Local screenshots: .venv/sidebar-1366.jpg, .venv/sidebar-1440.jpg, .venv/sidebar-1920.jpg.
