# Campaigns V1 HTML workspace

Implemented locally. No commit, push, deployment, production database mutation or email send. No migrations required.

## Primary workflow and layout

Campaigns opens directly into the email composer. There is no campaign-list landing screen, duplicated Campaigns / Flows / Settings navigation, Refresh, wizard or prominent search/filter dashboard. Navigation remains in the existing OS sidebar. Other CRM routes are unchanged.

A new compose session has no database ID: Untitled campaign, DRAFT, blank subject, preview text and HTML. Opening the page, switching preview widths and editing source do not insert a database draft or revision. The explicit Save draft action inserts the first record, then uses existing optimistic versioned updates. Session-only unsaved content is not durable across a disconnected session or hard reload; save explicitly. More > + New starts another local compose. Switching drafts or pages with unsaved edits requires saving or explicitly discarding them.

The compact top bar contains the current title/status, Marketing delivery OFF / Tests only, Save draft, Send test and More. Save is the only gold action. A 240px independently scrolling left panel contains Campaign Details (name, subject, preview text, market), collapsed Audience, Test, Templates and More. Audience retains filters, segments, exclusions, eligibility and Smart Sending without replacing the editor. Existing version history, reports and templates load only on request.

The center is a large white monospace HTML surface with HTML / Preview controls. An always-visible preview sits to the right. Its compact width selector displays exactly one layout at Desktop (600), 430, 390, 375 or 320px. Source edits update session state after a short debounce or blur, then refresh the preview; they do not save to the database. The source canvas height follows the viewport without growing when the page is scrolled. Long emails scroll within the preview frame. Existing Flow preview controls, including images-off/plain text, are unchanged.

Recent campaigns appears below the composer, with six rows per page and Campaign, Status, Market, Updated and Last test columns. Click a campaign cell or select its row to open it in the same editor above. Optional search/archived filters are collapsed. The query fetches at most seven rows for pagination; it does not fetch revision history or calculate audiences on page load. Duplicate, archive/restore, history and safe draft deletion remain in More. There is no schema change.

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

## Verification — final composer-first update

- 144 CRM tests passed against disposable PostgreSQL, including original HTML persistence, unsaved compose, no database insertion on page load/rerun, explicit save, recent-draft reopening, unsaved-change protection, lazy history/templates/eligibility, safe tests and deletion, and existing Flows/Settings behavior.
- 73 Email and 212 support Email regression tests passed with mocked transports.
- 34 navigation/startup tests passed.
- Changed Python files compile; JavaScript syntax check and git diff --check pass.
- Browser verification uses the actual Streamlit CRM UI/components and existing sidebar with disposable PostgreSQL and synthetic Shopify data. External HTTP requests are blocked. It does not exercise production authentication or production data.
- Browser checks: direct blank composer, full HTML paste and live right preview, explicit save, reopening saved source from recent campaigns, HTML/Preview round trip, collapsed Audience, restricted Test panel, named Delete confirmation/cancel, separate Flows and Settings. Permanent draft deletion is tested in isolated SQL; no user data is deleted in the browser.
- Screen sizes: 1920x1080, 1440x900 and 1366x768. The editor and right preview dominate the initial viewport. Lower desktop heights require modest vertical scrolling; controls can scroll independently. Recent campaigns stays below the editor.
- Screenshots: .venv/composer-1920.jpg, .venv/composer-1440.jpg, .venv/composer-1366.jpg. These show the local verification environment. Missing legal/sender configuration is intentionally represented by the existing test-only preview warnings.

## Files changed in the final simplification

crm_campaign_page.py; crm_html_workspace.py; crm_page.py; components/crm_html_editor/index.html; tests/test_crm_html_workspace.py; tests/test_crm_simple_editor.py; tests/test_crm_storage_recovery.py; docs/CRM_SIMPLE_EDITOR.md.

Only campaign presentation and related tests/documentation changed. Existing backend/schema, Email, Orders, Edition Ops, Product Uploads, Ads, SEO, Shopify access, permissions and delivery settings remain unchanged. Block storage/helpers are retained outside the primary V1 UI.

Nathan can safely review/edit/save drafts locally and after a separately approved deployment. A manual internal test still requires the existing configured admin allowlist, saved reviewed content and preflight. No production/bulk sending or deployment is authorized by this change. No commit, push, deployment or real email send was performed.
