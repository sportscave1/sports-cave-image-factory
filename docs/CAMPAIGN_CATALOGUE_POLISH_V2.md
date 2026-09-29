# Campaign catalogue polish — local verification

29 September 2026. Renderer and editor presentation only; no deployment or real email.

## Link failure and fix

The original image anchor already used the selected product's public `url`; its
`img src` used the separate Shopify CDN image. The anchor lacked `target="_blank"`,
so clicking it navigated the preview iframe to the storefront. A read-only HEAD
request to the actual Alan Jones public product page returned HTTP 200 with:

- `X-Frame-Options: DENY`
- `Content-Security-Policy: ... frame-ancestors 'none' ...`

The storefront deliberately cannot load inside the preview iframe. This was a
navigation-target problem, not an image/CDN or product mapping problem.

All three product anchors now use `_blank` and `noopener noreferrer`, which survive
the existing sanitizer. The existing Streamlit iframe already permits popups and
popup escape; no sandbox permissions or security checks were weakened. Image,
title and CTA were exercised in the actual local Campaign preview and opened the
same public product page in a new tab. The Campaign editor remained open.

Destination path:

`Shopify onlineStoreUrl → existing snapshot url → canonical_product_url → shared campaign_link → image/title/CTA/plaintext → existing rendered send snapshot`.

The renderer rejects non-HTTPS, image/admin, relative, preview and signed destinations.
It does not invent a fallback URL or change stored facts. The existing app/Ads
handle fallback helpers were inspected; importing those page modules into this
renderer would add unrelated coupling. A missing valid URL continues to surface
through existing editor/preflight validation.

Previously the sanitizer assigned a different `html_N` tracking reference to each
anchor. Catalogue links now apply the same existing tracking helper once per product
(`product_<id>`), so all three full hrefs, including tracking parameters, are identical.
The canonical base URL remains in the existing fact snapshot; exact tracked HTML and
plaintext remain in the existing outbound snapshot. Snapshot storage and send logic
were not modified. Authored HTML section tracking is unchanged.

## Visual changes

- Two-column images use consistent 200px image wells; one-column uses 300px.
  Proportional containment preserves the entire artwork without crop/stretch.
- Title: 18px/23px in two columns, 20px/25px in one column, original title casing.
- Small muted-gold limited-edition eyebrow, stronger edition number, one compact
  `NEXT AVAILABLE · N REMAINING` descriptor. Actual edition values are unchanged.
- Explicit tight margins replace default paragraph spacing. Refined smaller
  compare-at price remains struck through. The existing two-decimal formatter stays.
- Black/warm-white CTA, restrained gold border, 38px height and no large radius.
  Existing custom CTA wording remains supported.
- Catalogue editor rows reduced from roughly 37px to 31px. A missing edition mapping
  appears beneath its own title in small muted gold; warning rows are roughly 34px.
- Product picker, ordering, dragging, visibility and all event handlers retain their
  existing behavior. Only a presentation wrapper/class was added around product text.

The same seven artworks at a 600px email viewport measured **2,143.7px before →
1,531px after**, a **28.6% reduction** in catalogue height. The preview panel itself
was not shortened. Results depend on titles and source-image aspect ratios.

## Compatibility and boundaries

The existing 600px table structure and `sc-stack` responsive rule are retained.
Browser checks at 600/430/390/375/320px loaded all seven images and showed no horizontal
overflow. Narrow layouts stack the same cards. One-column rendering was also checked.
No external fonts, email JavaScript, hover effects, object-fit or new sanitizer
allowances were introduced. Email clients that ignore max-height may show a taller
natural-ratio image; this task did not send messages to test individual mail clients.

Public Sports Cave titles, links and artwork images were read from the storefront.
Prices and edition values in browser fixtures are deliberately fabricated; no live
Shopify Admin or Edition Ops data was queried or modified. Local SQL was disposable.

## Files changed

Production:

- `crm_catalogue.py`: compact cards, shared validated destination and safe targets.
- `crm_middle_sections.py`: avoids a second per-anchor tracking transformation on
  already-tracked catalogue links; keeps the shared sanitizer/plaintext pipeline.
- `components/crm_sections/composer.js`: catalogue class and product warning wrapper.
- `components/crm_sections/style.css`: catalogue-only compact controls/rows.

Tests/evidence:

- `tests/test_crm_catalogue_presentation.py`: ten focused renderer/link regressions.
- `tests/test_crm_modular_catalogue.py`: updated display wording and stronger outbound
  snapshot/identical-link assertions.
- `tests/catalogue_preview_app.py`: optional isolated seven-product polish fixture.
- `tests/catalogue_polish_fixture.py`, `tests/fixtures/catalogue_public_cards.json`:
  public artwork fixture, fabricated prices and edition values, no service calls.
- This report and `docs/catalogue-polish-evidence/` screenshots.

## Test results

| Validation | Result |
| --- | --- |
| CRM discovery, disposable PostgreSQL enabled | 211 passed |
| Focused catalogue/presentation rerun after snapshot assertion update | 29 passed |
| Email discovery | 143 passed, 1 SQL-gated skip |
| Support Email discovery | 212 passed |
| SQL-enabled navigation plus outbound snapshot test | 7 passed; covers skipped navigation case |
| Section/component JavaScript | 13 checks passed |
| Python compilation | 6 changed/added modules passed |
| JavaScript syntax | Passed |
| `git diff --check` | Passed |

Browser: actual Campaign workspace checked at exact CSS viewports 1920×1080,
1440×900 and 1366×768, with public artwork images. Desktop/Mobile, compact controls,
one/two columns and separate-tab product links verified. Isolated renderer checks
covered email widths 600/430/390/375/320. The local browser's existing 110% zoom was
accounted for when setting viewport dimensions; dimensions were read back from DOM.

Screenshots: [1920 desktop](catalogue-polish-evidence/desktop-1920.jpg),
[1440 desktop](catalogue-polish-evidence/desktop-1440.jpg),
[1366 desktop](catalogue-polish-evidence/desktop-1366.jpg),
[1366 Mobile preview](catalogue-polish-evidence/mobile-1366.jpg),
[original catalogue](catalogue-polish-evidence/before-600.jpg),
[600px email](catalogue-polish-evidence/email-600.jpg),
[320px email](catalogue-polish-evidence/email-320.jpg).

Edition Ops, Shopify mappings/sync, persistence, snapshot storage, consent, sending,
Inbox, signatures and Automations are unchanged. Marketing remains OFF. No real
email was sent. Nothing was committed, pushed or deployed. Ready for Nathan's local
visual acceptance review.
