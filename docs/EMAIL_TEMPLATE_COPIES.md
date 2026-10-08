# Email template copies and editable checkout HTML

Implemented in the existing shared Campaigns/Automations composer. No deployment,
production database updates, enrolments or customer sends were performed by this task.

## Behaviour

- Email defaults contains compact Header, Footer and Abandoned Checkout Edit rows.
  Checkout editing uses the existing `abandoned_checkout_master_v1` runtime-state
  record and optimistic revision check; its identity/storage is unchanged.
- Add section → Abandoned Checkout reads the latest saved master and copies its
  authored HTML/CSS into an independent, named HTML section. Pending source edits
  survive insertion. Individual flow steps and campaign drafts retain their own copies.
- Existing split checkout sections are joined in the editable draft only. Published
  versions and delivery history are not rewritten. The protected checkout marker
  is resolved by the existing recipient renderer; customer facts are never saved
  into authored HTML. Duplicate visible checkout markers still block publication.
- Source editing, previews, rename, duplicate, visibility, ordering and deletion use
  the existing section event/storage mechanism. Checkout CSS remains subject to
  the existing supported class contract and safe HTML validation.
- Header/footer snapshots are retained rather than replaced on every render.
  New email copies use current defaults; changing masters does not replace saved copies.
- Campaign previews use sample checkout data with a disabled recovery action.
  Campaign drafts containing checkout content remain saveable, but preflight and
  rendering block delivery without the recovery automation's checkout context.
- Template editors reuse the outer automation dialog as a subview, avoiding nested
  Streamlit dialogs. Campaigns retain their existing template dialogs.

## Files changed for this request

`crm_checkout_section.py`, `crm_template_modal.py`, `crm_middle_sections.py`,
`crm_section_ui.py`, `components/crm_sections/composer.js`,
`components/crm_sections/index.html`, `crm_checkout_migration.py`,
`crm_checkout_preview.py`, `crm_abandoned_checkout_ui.py`,
`crm_brand_template_ui.py`, `crm_campaign_library.py`, `crm_campaign_sections.py`,
`crm_campaign_page.py`, `crm_campaign_content.py`, `crm_html_workspace.py`,
`crm_automation_store.py`, `crm_automation_ui.py`,
`tests/test_crm_checkout_section.py`, `tests/test_crm_checkout_section_ui.cjs`.

Some changes were committed by another operation during this task; the list above
includes those changes as well as the remaining working-tree changes.

## Verification

- 121 tests run against disposable local PostgreSQL: 120 passed, one skipped.
  Suites: checkout_section, simple_editor, checkout_template_styles,
  checkout_publish_migration, section_ux, brand_templates, template_picker,
  native_automations, flow_builder, automation_ui, checkout_preview_fallback,
  checkout_details (all prefixed `tests.test_crm_`).
- `tests/test_crm_checkout_section_ui.cjs`: browser verification of master edit/save,
  independent existing copy, latest-master insertion, editable source/live preview,
  save/reopen and desktop/mobile layout. All external browser requests blocked.
- `tests/test_crm_sections_component.cjs` and `tests/test_crm_section_history.cjs` pass.
- `tests/test_crm_flow_builder_ui.cjs` passes, including the existing overview,
  sequence operations, shared composer, timing, simulation and four viewport sizes.
- Python compilation, JavaScript syntax checking and `git diff --check` pass.
- The broader run also found three pre-existing failures in
  `tests.test_crm_html_workspace.SqlWorkspaceTests`: delete_confirmation,
  empty_compose and recent_open tests expect removed campaign-home controls.
  All three failures were reproduced using the original campaign modules from
  commit `48625f4`, without replacing working-tree files.

No DDL, migration, dependencies, new scheduler or service configuration required.
Deploy through the existing workflow when approved. This Python/Streamlit project
has no root frontend build/typecheck script; compilation and runtime tests were used.
