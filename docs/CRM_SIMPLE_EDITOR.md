# Campaigns V1 simplified editor

Implemented locally. No commit, push, deployment, production database mutation or real email send.

## Workflow

New Campaign saves an Untitled campaign DRAFT and immediately opens one editor. Subject and Preview text are blank. HTML is the initial mode. Campaign names in the compact list open their editor directly; optional filters are in a popover. The grouped actions are Save draft, Preview, Send test and Back to campaigns. Duplicate, archive, restore, history and reports remain under More. Pending edits must be saved or discarded before destructive navigation/actions.

Audience, market, purpose, segments, country/sport/order/last-purchase filters, exclusions, Smart Sending and eligibility stay under Advanced settings. Existing templates, Shopify product/image selection and prompt/copy import are retained. Flows and Settings remain accessible.

## Content and storage

Optional `content_mode` and `custom_html` fields use the existing JSON campaign document and version history. No schema migration or removed column/table. Legacy documents continue to render their existing blocks/legacy fields. Switching modes retains both sources; only the selected mode renders. Template snapshots retain HTML mode/source too. Content changes invalidate prior testing and are audited using existing content_changed events.

HTML source is kept unchanged for editing/reload. A conservative standard-library parser reconstructs safe balanced email markup for preview/test delivery, generating plain text and appending the locked system footer. Public HTTPS links and durable JPEG/PNG images use existing validation; images require alt text. Existing test-link tracking is applied to HTML links. Scripts, event handlers, forms, SVG, embedded documents and unsafe styles never render. Head stylesheet rules are not imported: use inline email CSS. Unsupported CSS/document wrappers may therefore change the pasted design's appearance; review the layout before testing. Original source remains available. The existing overall document and rendered HTML size limits remain in force; drafts exceeding them show an explicit save error.

The lightweight HTML component sends debounced edits to the Streamlit session for automatic preview (no database write on each keystroke). Save draft is the persistence boundary. The block component has a draggable tray and pointer-based ordering handles, keyboard Alt+Arrow ordering, selection, duplication and deletion. The server validates exact block ID sets and rejects stale/replayed operations. Ordered block arrays persist using the existing draft/version model. No new dependencies.

## Safety

CRM_MARKETING_ENABLED and existing marketing infrastructure were not changed. Production sending remains disabled. Send test only opens the existing admin-only preflight/manual single allowlisted recipient workflow; it cannot dispatch an audience. No real test was sent. Consent, suppression, deduplication, Smart Sending, attribution, webhooks and normal Email transport are unchanged.

## Verification

- 134 CRM tests passed, including seven new focused editor/content/storage regressions.
- 73 Email and 212 support Email tests passed (mocked transport).
- 34 navigation/startup tests passed.
- Changed Python files compile; git diff --check passes.
- Actual Streamlit CRM pages tested locally with disposable PostgreSQL and synthetic Shopify, external sends blocked. These checks did not connect to production.
- Browser checked at 1440x900 and 1920x1080: HTML/editor and one preview beside each other, grouped actions, Advanced collapsed. 1440x900 has the actions at the bottom of the viewport; larger desktop has additional space. Blocks with expanded editing controls can require modest vertical scrolling.
- Browser verified HTML paste/automatic preview, save, reload, direct list opening, mode preservation, drag a new block, drag divider above text, save/reopen with correct order, admin test preflight without sending, Flows and Settings.
- Preview widths 320, 375, 390 and 430 verified by rendered iframe width, plus Desktop up to 600px (constrained to available column width).

## Files

crm_campaign_page.py; crm_page.py; crm_campaign_content.py; crm_campaign_html.py; crm_block_editor.py; crm_campaign_store.py; crm_workspace_store.py; components/crm_blocks/index.html; components/crm_html_editor/index.html; tests/test_crm_simple_editor.py; tests/test_crm_ui.py; tests/test_crm_storage_recovery.py; docs/CRM_SIMPLE_EDITOR.md.

Nathan can review the local editor and save drafts. After deployment approval, manually test one approved internal mailbox using the existing configured allowlist. No live/bulk activation is part of this change.
