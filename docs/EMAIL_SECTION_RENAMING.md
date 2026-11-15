# Shared email section renaming

Campaigns and every automation email step use the existing middle-section component.
The three-dot button directly after the visibility eye opens Rename. Its compact
popup provides a prefilled name, Save, Cancel and Reset to default; Enter saves and
Escape cancels. Fixed Header/Footer sections remain outside this component.

Names are internal `middle_sections[].name` metadata in existing draft JSON.
Reset stores an empty name so the current default label is shown. This also retains
the authored checkout-section boundary without rewriting/splitting its HTML.
No new table, migration, service, dependency or deployment configuration is required.
No production publication or customer email was triggered during development.

Changed implementation files:

- `components/crm_sections/composer.js`: menu, rename popup, keyboard handling,
  validation and updated accessible source labels.
- `components/crm_sections/style.css`: small controls using existing editor colours.
- `crm_middle_sections.py`: validated metadata events and explicit reset.
- `crm_checkout_migration.py`, `crm_checkout_preview.py`: preserve reset checkout
  section boundaries and native previews.

Tests added:

- `tests/test_crm_section_names.py`: metadata-only rendering, all editable types,
  invalid inputs, pending source edits, reorder/duplicate, SQL persistence, campaign
  duplication, flow/step duplication and published template metadata.
- `tests/test_crm_section_names_ui.cjs`: real Campaigns and Automations routes,
  Save/Cancel/Enter/Escape/reset, unchanged visibility/expansion, tab changes,
  page reload/reopening, section duplication/reordering.
- `tests/fixtures/crm_section_names_campaign.py`: existing campaign route with
  synthetic Shopify and disposable loopback SQL.

Verification: 92 Python tests passed; browser test passed for both editor routes;
section component and history tests passed; Python compilation, JavaScript syntax
and `git diff --check` passed. External HTTP was blocked in browser fixtures.
No root frontend build/typecheck script exists for this Python/Streamlit project.
