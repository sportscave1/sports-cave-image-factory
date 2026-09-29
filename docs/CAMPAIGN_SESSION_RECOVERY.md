# Campaign idle/session recovery — local verification (2026-09-29)

## Proven causes

`campaign_workspace` previously created a new compose document whenever `campaign_editor` was absent from Streamlit session state. Neither the selected campaign nor unsaved content had a durable recovery pointer/checkpoint. Browser section drafts also lived only in component memory. Losing the WebSocket/session therefore selected New Campaign even when earlier work had existed.

The local browser disconnect reproduced two real blocking elements: Streamlit's React Aria `[role="dialog"]` headed **Connection error**, and the existing product-picker dialog. Menu buttons became actually `disabled`; `elementFromPoint` over Home/Orders returned the overlay DIV. The measured cursor was `pointer`, not `not-allowed`. After server restart, dialogs disappeared, buttons were enabled, and the same hit test returned BUTTON. A permanently orphaned overlay beyond reconnection was not reproduced, so its production-specific cause is not asserted.

## Implementation

- `crm_campaign_recovery.py`: atomic draft checkpoint and per-user `last_active_campaign_id` in existing `crm_runtime_state`; stable first-save UUID; revision checks; non-conflicting three-way browser merge; failures retain both copies. No migration/new database.
- `crm_campaign_page.py`: restore before defaults, explicit query campaign ID before active pointer, autosave all composer mutations, save status/retry/separate recovery copy, flush before switching drafts. Empty page opens create no draft; the first meaningful edit does. Non-editable/archived/production campaigns are not automatically restored as editable.
- `crm_campaign_controls.py`, `crm_section_ui.py`: autosave at separate-fragment/discrete-action boundaries, including product selection and Segment.
- `crm_recovery_ui.py`, `components/campaign_recovery/index.html`, `components/campaign_recovery/recovery.js`: 750 ms text debounce, per-user/per-tab sessionStorage emergency copy, acknowledgement-aware cleanup, pending-edit flush on hide/blur/pagehide. No credentials in the copy. Storage failures do not erase the live editor. Normal saving is not dependent on unload events.
- `components/crm_sections/composer.js`: HTML/CTA debounce and pending-copy events; cancel stale drag/drop highlights on blur, pointer cancel and visibility transitions.
- `session_recovery.py`, `components/session_recovery.js`, `app.py`: one app-shell recovery controller with teardown. Healthy focus/resume makes zero requests. Only the verified Connection error + disabled-sidebar state triggers a bounded same-origin health probe, four-second timeout and reload fallback (at most once per minute). It never unlocks buttons or removes genuine dialogs. No business API refresh is added on normal resume.

Manual Save draft remains an immediate checkpoint. Autosave acknowledgement uses the existing composer fragment, not a full application reload. Optimistic conflicts cannot overwrite newer fields: retry or save a separate recovery copy. Lists are treated atomically during merges. Backend remains authoritative; the browser record is cleared only after confirmed persistence, not merely matching temporary UI state.

## Tests

- Full CRM suite: **318 passed** (35.453 s).
- New durable recovery suite: **11 passed** (4.765 s), including complete fresh AppTest session with same campaign ID, name, subject, preview, US Segment, schedule mode, HTML, five catalogue products, options/CTA, hidden/reordered inserted content. Covers first-save response loss, per-user isolation, explicit-route priority, conflicting revisions, independent blur/debounce changes, archive/production exclusion, outage retention and draft-switch blocking.
- Sidebar/theme/navigation/performance: **33 passed** (6.377 s).
- Startup scope regression: **6 passed** (0.876 s).
- Email: **144 run, 143 passed, 1 skipped** (19.482 s).
- Existing top-bar suite: **20 passed, 1 pre-existing failure**. `test_sidebar_is_compact_and_has_no_brand_or_section_headings` expects `resetInitialSidebarScroll`, absent from the unchanged top-bar component. This task does not add that unrelated behavior.
- Node recovery checks pass: healthy resume has zero I/O; hidden cancels probes; disconnected resume probes/reloads without unlocking; 750 ms coalescing; hide flush; failed-save recovery retention; acknowledgement cleanup; unmount removes listeners.
- Existing section component checks pass: 11 ordering/pointer/cleanup checks, 4 queue/ack checks, catalogue setting batching, CTA debounce, template menu checks.
- Python compilation and `git diff --check`: pass. Git emits informational CRLF-to-LF warnings; no whitespace errors.

Tests importing the entire app and Streamlit AppTest fixtures were run in separate processes: importing app installs existing Streamlit compatibility patches and otherwise contaminates combined test runs. No application workaround was added for that test isolation issue.

## Actual browser checks

Used the real Campaign composer and extracted real sidebar helpers in `tests/session_recovery_preview_app.py`, disposable local PostgreSQL and synthetic Shopify/edition services. No production APIs or transports.

1. Typed campaign name/subject without Save draft; queried local SQL to confirm persisted values while field remained focused.
2. Added HTML, Catalogue, five fixture products and custom CTA; local SQL confirmed the five products and CTA.
3. Restarted local server with product picker open: Connection error intercepted clicks; after recovery both dialogs were gone and sidebar buttons were enabled/hittable.
4. Cleared all server session state with fixture control: restored same campaign and preview.
5. Browser reload and Orders -> Campaigns restored the same campaign, HTML, five products and CTA; Saved status visible.
6. Hidden/visible and blur/focus/drag cancellation exercised in deterministic component tests. Actual hour-long idle, OS minimize, and every business page were not exercised. Shared shell was inspected; business loaders were intentionally not run.

Screenshot: `C:/Users/hello/.codex/visualizations/2026/09/27/01a0e4de-ea00-7bd1-aac3-7f4691e4e95f/campaign-recovered.png`. Images in this fixture intentionally use synthetic URLs; this is state recovery verification, not artwork rendering verification.

## Scope and safety

Changed recovery tests: `tests/test_campaign_recovery.py`, `tests/test_session_recovery.cjs`, `tests/session_recovery_preview_app.py`, `tests/test_crm_sections_component.cjs`, `tests/test_crm_ui.py`, `tests/test_crm_html_workspace.py`, `tests/test_crm_modular_catalogue.py`, `tests/test_crm_storage_recovery.py`. Older tests now isolate test-user identity and expect autosave rather than transient-only compose state.

Earlier uncommitted Send Test changes were preserved; they are separate from this lifecycle task. No marketing configuration was changed. No email was sent, no Shopify/edition/production data was changed, and nothing was committed, pushed or deployed. Local fixture data only. Ready for local review; production-specific permanent-overlay behavior still needs observation if it recurs after rollout.
