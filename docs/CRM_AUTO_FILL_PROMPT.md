# Campaign Settings: Auto fill prompt

Implemented in the existing Settings tab, immediately above Campaign name. A
small right-aligned text action and separate accessible help popover open a
490px native dialog. It is a manual prompt builder, not an AI integration or a
second editor. Campaign name, Subject and `content.preheader` are never assigned
by the helper. Existing autosave, segment, timing, template and send paths remain.

## Files and authority

- `crm_campaign_page.py`: Settings entrypoint and label-line character feedback.
- `crm_prompt_ui.py`: fragment-scoped trigger, native dialog/comboboxes, 250ms
  search commit, paginated selections, manual fallback, copy/failure UI and focus.
- `crm_campaign_prompt.py`: central 31-purpose configuration, deterministic
  public-context projection, validation, freshness and length rules.
- `prompts/sports_cave_campaign_prompt_v1.txt`: complete fixed instruction set.
- `crm_prompt_readers.py`: adapters over existing authorised read services.
- `crm_shopify.py`: optional public description on the existing products reader;
  existing callers retain their old query.
- `tests/test_crm_prompt_helper.py`, `tests/test_crm_prompt_clipboard.cjs`,
  `tests/fixtures/crm_prompt_preview.py`: offline validation and browser fixture.
- `docs/examples/campaign-product-prompt.txt` and
  `docs/examples/campaign-collection-prompt.txt`: complete generated fixture
  prompts. IDs, counts and URLs in these examples are fabricated test context,
  not live verified catalogue facts.

Edition selection uses `supabase_backend.list_edition_products_read_only` with
nine rows per page (eight visible plus a next-page sentinel). Existing title,
handle and SKU search semantics are reused. Fresh scarcity checks use the same
ledger/integrity projection through `crm_catalogue.edition_for` and Edition Ops'
existing `_widget_status` rules. No inventory/cursor arithmetic, allocation,
initialisation, reservation or repair is performed. Unknown or blocked integrity
fails closed for availability claims; optional edition size may be omitted.

Public product details use `Shopify.products(..., public_context=True)`.
Collection search uses the existing authorised `Shopify.query` transport with
eight-result cursor pages, without a collection-type filter or product preload.
It is the bounded counterpart of `Catalogue.collections`. Canonical URLs use
Shopify's collection handle and `shop.primaryDomain.url`; manual targets never
receive generated identity/URL/facts. The existing account-scoped picker cache
and Shopify query cache supply metadata reuse.

## Safety and lifecycle

Inputs are scoped by the existing campaign key, with separate target-mode state.
Search edits clear the prior identity before a new lookup, including outages.
Native dialog requests are serial; there is no asynchronous search worker whose
late response could overwrite a newer target. Query-specific widgets and input
fingerprints invalidate old prompts, and client input immediately disables Copy.

Offers need entered terms and eligibility context. Deadlines require an explicit
ISO date/time with offset or `YYYY-MM-DD HH:MM Area/City`; ambiguous DST times and
expired deadlines are rejected. Recipient-local schedules are checked
conservatively against the latest possible timezone rather than assuming Sydney.
Release, early-access, bestseller and relationship claims need user-confirmed
context. Free-form facts are labelled user-confirmed, not independently verified.

Low/final stock reads fresh canonical availability on Submit and Copy. A changed
count requires Submit again; sensitive readiness is cleared on reopening. Zero
low stock is blocked with an explicit Availability / waitlist switch. Final type
with zero uses sold-out facts without inferring retirement. Unsupported scarcity
is limited to neutral availability, with an explicit support flag in context.
Scheduled availability is an observation, not a forecast or future urgency claim.
Collection availability requires an explicitly selected, verified member edition;
the helper never invents a collection-wide remainder. Common numeric stock/size
conflicts and unsupported urgency notes are rejected rather than overriding the
ledger. Natural-language assertions still require truthful operator-entered
context; no AI fact-checking or external research is performed.

Copy revalidates current context before writing the clipboard. It reports Copied
only after success; denial/unsupported access reveals read-only selectable text.
The full prompt stays collapsed behind View prompt. Existing HTML parser and
public URL guards clean/cap selected facts; raw customer/order rows, recipients,
credentials and counts are excluded. Internal IDs are context only, explicitly
excluded from ChatGPT's three output values.

Dialog updates do not invoke the composer save/send functions. Native Escape/X
close without a page rerun; a local scroll anchor preserves the background and
returns focus without scrolling. Subject/Preview counts use Unicode code points
(Python/JavaScript-consistent, including spaces/punctuation), are advisory only,
and leave the existing 150/250/250 field limits unchanged.

## Validation

- 422 CRM tests completed successfully, one skipped, on disposable local SQL.
  An earlier count assertion collided with browser-fixture seeding; the final
  run was isolated after stopping that fixture and passed.
- Ten focused helper tests cover selection/read pagination, manual identity
  clearing during API failure, public projection, no draft mutation, validation,
  deadlines, sold-out/unknown/conflicting availability and neutral fallback.
- Actual clipboard JavaScript tested for success, denial, unsupported access and
  escaped script content; Python compilation and `git diff --check` passed.
- Collection and product context queries validated against Shopify 2026-07.
  The reused product query retains an existing featuredImage deprecation warning.
- Browser fixture: 1440×900, 1366×768 and 820×768. Product generation/copy,
  collection page two, offline explicit manual entry, keyboard help/Escape/focus,
  sensitive reopen invalidation and no horizontal modal overflow verified.
  At 1366/820 widths, the final dialog stayed between y=48 and y=720 in the
  768px viewport. The real pointer workflow retained a 40px background offset
  through open/Submit/Copy/Escape. Locator auto-scrolling was excluded from that
  measurement. Final clean browser session had no console errors.

Live Shopify/Edition Ops data was not exercised. Browser catalogue data and
availability were explicit fixtures; the production code is wired to the real
readers above. Clipboard denial was tested in the JavaScript harness, while actual
clipboard success was verified in the browser. No production data, send queue,
edition record, credentials or schema were changed by this task. No AI API,
polling service, migration or dependency added. No commit, push or deploy performed.
