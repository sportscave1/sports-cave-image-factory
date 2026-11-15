# Abandoned checkout preview repair

## Root cause

`AutomationStore.preview_document()` used the publication validator before visual
rendering. That validator correctly rejects Liquid for live publication, but its
exception also stopped embedded preview, Live Preview and size calculation.
Unavailable/pending Shopify preview data similarly stopped rendering.

## Repair

Editor and Live Preview use the latest valid checkout asynchronously, retain a
session-scoped last-good checkout during refresh/failure, and otherwise render a
clearly labelled sample immediately. Sample mode reuses already-selected catalogue
facts when available without new product requests. Otherwise it uses neutral
sample text, no fabricated price, and no recovery link. Missing images are supported.

Known legacy checkout loops/markers are substituted in a deep-copied document
using the existing native `abandoned_checkout_products` renderer. Surrounding
authored HTML, section IDs, header/footer and saved draft are preserved. Complete
and incomplete Liquid tokens are removed from the visual copy. A small caption
explains the legacy substitution. This is preview substitution, not a persistent
draft migration: saved Liquid still blocks publication until replaced with the
native block.

Send Test uses preview context/sample fallback and disables the recovery action.
The hydrated final preview is passed through existing email rendering and size
analysis. Live Preview retains its desktop/mobile controls.

Live delivery is unchanged: only the exact enrollment checkout/customer may resolve;
recovered, mismatched, unresolved or sample contexts fail closed. Neither the live
engine nor its runtime uses the new preview helper. The 95 KB guard remains intact.

## Files

Runtime: `crm_checkout_preview.py`, `crm_abandoned_checkout.py`,
`crm_abandoned_checkout_ui.py`, `crm_automation_store.py`,
`crm_campaign_send_ui.py`, `crm_email_size_ui.py`, `crm_html_workspace.py`.

Tests: `tests/test_crm_checkout_preview_fallback.py`,
`tests/test_crm_checkout_preview_fallback_ui.cjs`,
`tests/test_crm_abandoned_checkout.py`, `tests/test_crm_native_automations.py`,
`tests/fixtures/crm_automation_preview.py`.

Evidence: `docs/performance-evidence/checkout-fallback-real.png`,
`docs/performance-evidence/checkout-fallback-sample.png` (synthetic fixture data).

## Local validation

- Combined Python suite: **173 passed, zero skipped**, with disposable loopback
  PostgreSQL and mocked Shopify/Resend. Covers checkout resolution/legacy/sample,
  automation persistence, strict delivery, campaign send flow, tracking, email size,
  editor sections, preview performance and Campaigns first paint.
- Browser fixture: real checkout and simulated Shopify failure passed. Embedded
  and Live Preview show the full design, retain HTML Sections 1/2, hide raw Liquid,
  display labels and size; desktop/mobile controls work. No horizontal overflow at
  OS viewport widths 1366, 768, 390 and 320 pixels.
- `py_compile` for changed Python files and `git diff --check`: passed.

No production database, Shopify or Resend request was made. No email was sent.
No commit, push or deployment was performed. Production acceptance against the
existing Reminder 1 record still needs verification in the connected environment.
