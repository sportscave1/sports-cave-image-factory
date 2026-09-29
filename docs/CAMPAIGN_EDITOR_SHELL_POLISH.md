# Campaign editor shell polish — local verification

## Scope and files

This task changes only Campaign editor presentation and control interactions:

- `crm_html_workspace.py`: Campaign-scoped tabs, panel, fields and fixed Header/Footer presentation.
- `components/crm_sections/style.css`: compact rows, neutral code input, eye controls, drag/focus/hidden states and Add section menu.
- `components/crm_sections/composer.js`: eye toggle presentation, stable focus after a visibility change, real HTML placeholder, menu keyboard/dismissal handling. Existing section events and data payloads are retained.
- `components/crm_sections/index.html`: compact Add section control/menu markup.
- `tests/test_crm_campaign_sections.py`: fixed-row label expectations; accommodate Streamlit AppTest classifying icon expanders as status elements.
- `tests/test_crm_editor_shell.cjs`: focused visibility and command-menu interaction checks.
- This report and `campaign-editor-shell-evidence/*.jpg`.

Earlier uncommitted catalogue rendering work remains intact. No additional catalogue renderer, persistence, audience, compliance, send/test, Inbox or Automations changes were made in this task.

## Visual and interaction changes

The global app styles filled selected tabs gold. Campaign-local overrides now cover both button tabs and the current Streamlit React Aria tab elements. Active tabs use transparent backgrounds, stronger text and the existing `--sc-gold` underline. Keyboard tab semantics remain native.

The panel has 16px padding, a 10px radius and warm-white background. Fixed and movable rows measure 50px. Header/Footer use the existing Material lock icon and a muted Fixed indicator; their source fields and template controls are unchanged. Middle rows use separators, 7px gaps, muted handles, eye/eye-off toggles and explicit Hidden text.

HTML inputs now default to 240px (previous minimum 290px), remain vertically resizable, and use 13px monospace text on a neutral surface. The placeholder is `Paste campaign HTML here…` and never enters saved content. Expanded padding is 12px; focus outlines and small hover states use restrained brand accents.

Add section is a small outlined control with a compact HTML/Catalogue command list. Native keyboard activation, Arrow Up/Down, Escape and outside-click/iframe-blur dismissal work. Focus returns to the trigger on Escape and remains on visibility controls after an acknowledged toggle. Existing Alt+Up/Down reorder controls are retained.

No dependencies, API calls or additional data fetching were introduced. Changes are local CSS, small SVG icons and lightweight event handling. No wall-clock performance improvement is claimed.

## Verification

All testing used the existing isolated Campaign harness with synthetic users/data and disposable local PostgreSQL. Production transport/database/Shopify I/O is blocked by that harness. No email was sent.

- CRM suite: `CRM_TEST_POSTGRES=1 .venv/render-312/Scripts/python.exe -m unittest discover -s tests -p 'test_crm*.py'` — **211 tests passed** (27.681s). Includes Campaign UI, sections, old drafts, save/reload, rendering, templates and send safeguards.
- `node tests/test_crm_sections_component.cjs` — **13 checks passed**: section/product ordering, pointer boundaries, acknowledgements, queued actions and pending edits.
- `node tests/test_crm_editor_shell.cjs` — **8 scenarios passed**: visibility state/events, keyboard command selection, Escape/focus, expanded state, outside click and blur dismissal.
- Python compilation of changed Python files — passed.
- `git diff --check` — passed.

Browser checks in the actual OS/Campaign page at **1920×1080, 1440×900 and 1366×768**:

- Transparent active tabs/gold underline; both tabs and arrow-key switching work.
- Header/Footer expand/collapse and remain fixed; all rows measure 50px.
- HTML textarea measures 240px and retains edits through hide/show and tab switching.
- No horizontal overflow in page or section component; narrow panel scrolls internally.
- Add HTML and Add Catalogue append the correct existing section types.
- Eye state, Hidden label, keyboard focus preservation, menu Escape and outside click work.
- Alt+Up ordering updates actual Campaign section order. Mouse drag confirmed separately against the exact component in the existing standalone local harness (Catalogue moved above HTML Section 1).
- Existing preview reflects HTML edits; backend persistence/regression tests pass.

Screenshots:

- [HTML — 1920×1080](campaign-editor-shell-evidence/html-1920.jpg)
- [HTML — 1440×900](campaign-editor-shell-evidence/html-1440.jpg)
- [Details — 1440×900](campaign-editor-shell-evidence/details-1440.jpg)
- [HTML — 1366×768](campaign-editor-shell-evidence/html-1366.jpg)
- [Add section — 1366×768](campaign-editor-shell-evidence/menu-1366.jpg)

Marketing remains OFF; its configuration/gates are untouched. No real emails, production data writes, commits, pushes or deployments occurred. Ready for Nathan's local visual acceptance review.
