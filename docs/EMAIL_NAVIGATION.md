# Email navigation consolidation

Local presentation change only. No migration, production data write, transport change, email send or automation activation.

## Navigation

The shared sidebar in app.py now presents Email with exactly three permission-filtered children: Inbox, Campaigns and Automations. It uses the existing mail icon, disclosure component, charcoal theme and gold active row. CRM & Marketing and the Settings child are removed from the sidebar presentation.

The route identities are unchanged:

| Visible destination | Existing route / renderer |
| --- | --- |
| Email / Inbox | Email / support_email_page.render_page |
| Email / Campaigns | CRM Campaigns / campaign_workspace |
| Email / Automations | CRM Automations / existing Flow editor |

Email parent opens Inbox when the user has mailbox permission; clicking it again can collapse/reopen the group. A CRM-only user cannot gain Inbox permission through the parent. Active child routes and all legacy CRM settings aliases reopen the Email group on direct navigation/refresh. Existing authorization and unsaved-draft navigation guards remain in use. Internal route names, bookmarks and page IDs remain valid.

Only the visible Flow navigation label, heading and inactive caption become Automations. No triggers, timing, flow records or activation logic changed. No mailbox source, CSS, folders, compose/reply/send/Sent behavior changed. Campaign content editing, preview, source storage and testing behavior are retained.

## Campaign Settings

A small secondary Settings control in the Campaigns action bar toggles a section below the editor. A toast identifies its location. Close settings hides it. The section shows plain safe status rows and reuses the existing settings selector/forms, defaulting administrators to Sending & Compliance. Delivery diagnostics are collapsed. Existing Customers, Segments, Templates, Reports, Branding, Connections & Tracking, Prompts and Sending & Compliance remain accessible according to the existing permissions.

Status rows include production delivery Off, actual Smart Sending hours, website tracking status, allowlist configured/missing, and safe sender/reply-to addresses. No secret values are selected or rendered. No switch to activate production marketing was added. Legacy settings URLs remain available with a Back to campaigns control.

## Validation

496 unique tests passed across the relevant isolated suites:

- 144 CRM campaign/storage/Flow/service/UI tests against disposable PostgreSQL.
- 73 Email and 212 support Email regression tests with fabricated transports.
- 57 navigation/startup/other navigation tests.
- 4 sidebar appearance/navigation tests.
- 6 focused Email navigation/settings tests, including exact children, Inbox default/collapse, direct-route refresh, original mailbox dispatch, permissions, settings access, preserved unsaved HTML, no automatic sending and secret redaction.

The combined AppTest sidebar + full-app startup import run encountered Streamlit form-context interference. Running the sidebar/AppTest suites and startup suites in separate processes passed; no production code workaround was added for test-runner state.

Changed Python files compile and git diff --check passes. No schema/storage/service/Email files changed. Browser verification uses actual sidebar, mailbox, Campaign and Flow components with disposable PostgreSQL, fabricated mailbox transport and synthetic Shopify authority. It does not exercise production credentials/authentication. Checked collapsed/expanded Email, Inbox/Campaigns/Automations active states, Campaign Settings, direct refresh and sidebar scrolling at 1920x1080, 1440x900 and 1366x768. Local screenshots are in .venv/email-nav-*.jpg.

## Files

app.py; crm_navigation.py; crm_campaign_page.py; crm_page.py; crm_flow_editor.py (caption only); crm_settings_page.py; tests/test_email_navigation.py; tests/test_sidebar_theme.py; tests/test_crm_workspace.py; tests/test_crm_html_workspace.py; tests/test_crm_storage_recovery.py; docs/EMAIL_NAVIGATION.md.

CRM_MARKETING_ENABLED and production configuration were not modified. Marketing delivery remains disabled and existing internal-test protections remain. Safe for Nathan to review locally and deploy after separate approval; no deployment was performed by this task.

Repository note: HEAD advanced externally to 7cca7c0 during implementation, capturing the earlier composer work and some in-progress navigation access changes. That commit was preserved. This agent did not commit, push or deploy.
