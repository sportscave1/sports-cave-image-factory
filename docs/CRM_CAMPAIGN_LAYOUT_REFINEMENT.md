# Campaign editor layout refinement — local verification

Implemented 28 September 2026. No commit, push, deployment, production database
operation or email send was performed for this change.

## Changes

- Campaign-only CSS overrides the accumulated top spacing with the existing
  top-bar height plus 8px. The global top bar is unchanged.
- Two columns: a 360px control panel (330px at the requested smaller desktop
  sizes) and a stretching preview. Both have viewport-relative heights and
  internal scrolling. Recent campaigns remains below the workspace.
- The control panel has Campaign Details / HTML tabs. Existing details,
  audiences, internal tests, templates and More remain available.
- HTML has collapsed Header, expanded Body and collapsed Footer sections.
  New bodies are empty. Header defaults use the existing configured logo or
  SPORTS CAVE text and existing test-only branding; no invented assets.
- Footer starts from an editable branded HTML template. The previous separate
  `{{SYSTEM_FOOTER}}` layer is superseded by [one editable footer](CRM_SINGLE_FOOTER.md).
  No missing fields or wording are restored. A visible authored unsubscribe
  anchor is checked only for future live readiness, without modifying the design.
- Desktop and Mobile icon buttons select 600px and 390px previews. Outgoing
  HTML stays responsive; 430/375/320 support remains.
- Header and footer sources use optional `html_sections` in existing document
  JSON. Body remains `custom_html`. Original source strings persist unchanged;
  only rendered output is sanitized. No database migration is needed.
- History detects section changes, duplication retains them, and existing
  template snapshots now include them.
- Legacy drafts without `html_sections` keep their original rendering path.
  Opening, editing their body or saving does not insert new wrappers. Editing
  their Header/Footer explicitly opts into the sectioned path. A comparison
  against HEAD confirmed identical legacy HTML, plain text and subject.
- Preview and mocked internal test delivery both use `render_campaign`; the
  payload equality and repeat-operation protection are tested.
- Textarea edits update on Streamlit input commit (blur / Ctrl+Enter), without
  database writes per keystroke. Save draft remains explicit.

## Files

- `crm_campaign_page.py`: tabs, two-column composition, new defaults and template loading.
- `crm_html_workspace.py`: scoped spacing/layout, section inputs, preview icons.
- `crm_campaign_sections.py`: defaults and safe section assembly (new).
- `crm_campaign_content.py`: optional JSON validation, rendering and preflight.
- `crm_campaign_store.py`: section-change audit detection.
- `crm_workspace_store.py`: preserve sections in existing template snapshots.
- `tests/test_crm_campaign_sections.py`: new rendering/persistence/UI tests.
- `tests/test_crm_html_workspace.py`, `tests/test_email_navigation.py`: updated UI assertions.

Existing unrelated Email Trash working-tree changes were left intact.
Inbox, Flow canvas, delivery transport, audiences, consent, suppression and
Smart Sending implementation were not changed. Marketing remains disabled;
no production environment flags were edited.

## Verification

- CRM discovery (`CRM_TEST_POSTGRES=1`, `test_crm*.py`): 154 passed.
- Email discovery (`test_email*.py`): 99 passed.
- Support Email discovery (`test_support_email*.py`): 212 passed.
- Navigation/startup suites, each in a fresh process: 61 passed (startup scope,
  navigation performance, sidebar cleanup/theme, Analytics and Social Media).
  A combined-process attempt encountered existing Streamlit global-state
  contamination; all suites passed when isolated.
- Changed Python compilation and `git diff --check`: passed.
- Browser used the real application shell with fabricated account/Shopify data
  and isolated storage, not production. Checked 1920x1080, 1440x900, 1366x768
  and Mobile. Preview widths measured 76%, 68% and 66% of workspace respectively.
  No horizontal overflow; long previews scroll internally.
- Rendered email inspected in 600/430/390/375/320px frames: protected footer
  present at every width, with no horizontal overflow.
- Full-shell fixture lost its injected store during an interaction and showed
  a safe storage error. Browser save/reload/reopen was therefore verified in
  the actual Campaign workspace mounted directly with the same isolated SQL
  adapter: campaign name, subject, preview text and body restored successfully.
  Automated AppTest also verifies header/body/footer edits and rerun persistence.
- Screenshots: `.venv/campaign-1920.jpg`, `.venv/campaign-1440.jpg`,
  `.venv/campaign-1366.jpg`, `.venv/campaign-mobile.jpg`.

Safe for Nathan to test locally. Production and actual mailbox delivery were
not tested or modified. Existing Streamlit iframe deprecation warnings remain;
no unrelated component migration was undertaken.
