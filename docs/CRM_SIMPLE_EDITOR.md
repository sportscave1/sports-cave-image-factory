# Campaigns V1 HTML workspace

Implemented locally. No commit, push, deployment, production database mutation or email send. No migrations required.

## Primary workflow and layout

Campaigns uses a compact clickable campaign list with Campaign, Status, Audience, Market, Updated and Last test columns. Filters are optional. New Campaign saves an Untitled campaign DRAFT and immediately opens blank HTML, subject and preview text. No wizard, Blocks tab, drag tray or side-by-side preview appears in the primary editor.

Name, subject and preview text sit above grouped Save draft / Preview / Send test / Back actions. A 250px left panel holds collapsed Details, Audience, Test, More and Templates sections. Audience expands without replacing the canvas. It retains segments, filters, exclusions, eligibility and Smart Sending. More retains duplicate, archive/restore, versions and reports, and adds confirmed draft deletion. Templates use the existing storage only.

The main white workspace switches between HTML source and one Preview. Preview widths are Desktop (600), 430, 390, 375 and 320; images-off and plain-text views remain available. Source edits update session state, not database versions. Save draft is explicit.

## Content preservation and safety

Original HTML is saved/reloaded unchanged. Existing sanitization reconstructs safe email markup, retains supported inline styles/tables/images/links, validates URLs and alt text, generates plain text and inserts the locked mandatory footer. Editing source cannot remove that footer. Scripts, unsafe attributes, forms and unsupported styles cannot render. Head stylesheet rules are not imported; use inline email CSS and review the preview. Existing size limits remain enforced.

Legacy block campaigns open an HTML snapshot of their rendered body. Their block arrays and original version history remain stored. Pasted HTML is never converted into blocks. Block components/helpers remain dormant and unchanged. Existing Shopify product/prompt helpers remain in the code but are not part of the primary V1 workspace. No backend tables, columns or consent/eligibility/suppression/deduplication/Smart Sending/tracking/attribution capabilities were removed.

## Draft deletion

The named confirmation warns that deletion is permanent. The service requires campaign-management permission, an explicit confirmation, the exact name and current version, and a row lock. Only a non-archived DRAFT without test/delivery/attribution/suppression references is eligible. Even a failed internal-test record prevents deletion; archive such drafts instead. Only the target draft and its own draft revisions are removed transactionally. An existing activity-log event is attempted afterward; unavailable audit storage is reported rather than pretending it succeeded. No Shopify or mailbox records are touched.

## Flows and Settings

Flows use the same HTML/Preview canvas, with trigger/details/audience/email/test controls in the left panel. Only inactive DRAFT/PAUSED flow emails can save. Each explicit email save forks an immutable versioned template snapshot and updates only the selected flow step; other flows and enrolled template snapshots are unchanged. Optimistic concurrency prevents overwriting changed flow/template state. Trigger edits require the email to be saved first; reload requires an explicit discard checkbox when dirty. Existing workflow configuration remains collapsed under More.

Flow tests prepare a separate campaign test snapshot and use the existing single-recipient admin/allowlist/preflight/idempotency boundary. Preparation never sends an email. Settings remains a separate CRM navigation entry with existing functions.

## Marketing safety

CRM_MARKETING_ENABLED and delivery configuration were not changed. Production delivery remains OFF and flows are not activated. Test sending requires an explicit admin action, saved/reviewed current content and exactly one approved manually entered internal recipient. Audience calculations, preview, page loads and saves never send. No real email was sent during implementation or verification.

## Verification

- 142 CRM tests passed, including 8 new workspace/deletion/flow-storage tests.
- 73 Email and 212 support Email regression tests passed with mocked transport.
- 34 navigation/startup tests passed.
- Final focused 21-test rerun passed after spacing and unsaved-flow protection changes.
- Changed Python files compile; git diff --check passes.
- Browser exercised actual Streamlit CRM UI/components with disposable PostgreSQL and synthetic Shopify, with external requests blocked. Production credentials/data were not used.
- Checked at 1440x900 and 1920x1080: campaign list, blank New Campaign, HTML paste/save, source preservation after server reload, same-surface preview, Audience panel, restricted Test panel, named Delete confirmation/cancel, Flows and Settings. Permanent deletion is covered by isolated SQL tests, not a browser deletion of user data.
- 1920x1080 campaign editor fits on one screen. 1440x900 can require modest vertical scrolling to the canvas bottom; primary actions stay at the top. Long settings scroll within the left panel. Email preview itself scrolls inside its frame.
- Desktop and 320px preview frame widths verified in this pass; intermediate sizes retain the same previously verified shared rendering path.
- Screenshots: .venv/crm-ultra-1920.jpg and .venv/crm-ultra-1440.jpg (local verification environment; OS production shell/auth was not exercised).

## Files changed in this update

crm_campaign_page.py; crm_campaign_store.py; crm_page.py; crm_html_workspace.py (new); crm_flow_editor.py (new); components/crm_html_editor/index.html; tests/test_crm_html_workspace.py (new); tests/test_crm_ui.py; tests/test_crm_storage_recovery.py; docs/CRM_SIMPLE_EDITOR.md.

Nathan can safely review/edit/save drafts locally. A manual internal test requires the existing configured admin allowlist and preflight. No production/bulk sending or deployment is authorized by this change.
