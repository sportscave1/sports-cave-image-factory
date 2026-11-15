# Compact automation toolbar and publication state

The existing flow and individual-email editors now share one compact native
toolbar. Email editing retains Settings / Editor / Templates and the existing
preview, source editor, test-email control, section names and template editors.
The redundant native dialog title is hidden only for this automation editor.
Desktop controls are 38px high; smaller viewports wrap without toolbar overflow.
Truncated automation names retain the full name in a tooltip.

## Publishing behaviour

- Never published: Publish now.
- Published, effective draft unchanged: non-interactive Up to date.
- Published, effective draft changed: Publish changes.
- Paused publishing retains PAUSED and its original paused timestamp. Only Resume
  recalculates pending deadlines through the existing throttled resume mechanism.
- Opening, previewing, internal section labels, editor conversion, audience counts
  and copy-review metadata do not create meaningful publication differences.
- Comparisons use immutable publication content, not revision/timestamp flags.
  Existing publications are reconstructed from saved jobs and exact template
  versions. New publications retain the entire flow in existing config JSON,
  including disabled steps, so later edits can be compared accurately.
- Master defaults are not read as a live comparison source. Previously published
  header/footer copies are retained when opening older drafts without snapshots.
- Save draft remains independent of publication. Existing autosave disables the
  button once saved; pending browser edits enable it. The publication barrier
  flushes section inputs and native focused fields before requesting the exact
  intended saved revision. Concurrent edits fail the optimistic revision check.
- Unchanged publication requests are no-ops, including direct/server callers.
  Changed publications still use the existing durable validation job and worker.
  The editor remains open and refreshes Publishing → Up to date on completion.
- Publication never creates enrollments or submits mail. Existing recipients keep
  their frozen sequences, template versions, schedules and historical records.

## Changed files

Implementation:

- `crm_automation_toolbar.py`
- `crm_automation_publish_state.py`
- `crm_automation_publication.py`
- `crm_automation_store.py`
- `crm_automation_ui.py`
- `crm_flow_builder.py`
- `crm_campaign_page.py` (automation-only toolbar refresh)
- `components/crm_sections/automation_publish.js`

Tests / fixtures:

- `tests/test_crm_automation_publication.py`
- `tests/test_crm_native_automations.py`
- `tests/test_crm_automation_ui.py`
- `tests/test_crm_automation_toolbar_ui.cjs`
- `tests/test_crm_flow_builder_ui.cjs`
- `tests/test_crm_checkout_section_ui.cjs`
- `tests/fixtures/crm_automation_preview.py`

## Verification and release

92 tests passed across publication, native automation, Flow Builder, automation UI,
section renaming, checkout sections and checkout migration suites. Coverage includes
no-op requests, content/settings changes, legacy reconstruction, pause/resume,
frozen customer journeys, duplicate-safe sending and publication history.

Browser tests passed for the toolbar, Flow Builder and shared template editor.
Toolbar checks cover a live v1 flow, unchanged state, HTML edits, refresh persistence,
an unblurred subject immediately before Publish, paused publication to v2, Up to date,
Resume, Send test controls, back navigation and 1440/1000/750/390/320px layouts.
All database and browser fixtures were local/synthetic; external browser requests
were blocked and no customer emails were sent.

Python compilation, JavaScript syntax checking and `git diff --check` passed.
There is no root production-build/typecheck command for this Python/Streamlit app.

No database schema migration, dependencies, new services or scheduler configuration
are needed. `published_flow` is additive JSON in the existing automation record,
written only on a changed publication. Release the app and existing CRM worker
through the normal deployment workflow. This task did not deploy.
