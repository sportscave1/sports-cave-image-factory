# Editable abandoned checkout template styling

## Previous ownership

`crm_abandoned_checkout.block_html()` supplied inline colours, fonts, sizes,
weights, margins and padding. The shared HTML sanitizer discarded `<style>` and
most classes, so template CSS could not control that generated product markup.

## New ownership

The editable default is `templates/abandoned_checkout_collector_reminder.html`.
It contains checkout CSS, intro/outro HTML and exactly one protected
`<!--SC_ABANDONED_CHECKOUT-->` marker. No theme colours or typography remain in
`block_html()`: it provides escaped data, semantic table markup, checked images,
the exact recovery URL and structural width/height/table attributes only.

Stable class contract:

`sc-cart-block`, `sc-cart-label`, `sc-cart-image-wrap`, `sc-cart-image`,
`sc-cart-title`, `sc-cart-variant`, `sc-cart-meta`, `sc-cart-price`,
`sc-cart-button-wrap`, `sc-cart-button`, `sc-cart-extra-items`.

`crm_checkout_styles` reads simple class-only CSS rules using the existing safe
email-property/value boundary. It applies the authored values to generated markup,
handles `!important`, removes stylesheet blocks and passes resulting inline HTML
through the existing sanitizer. CSS URLs, expressions, arbitrary selectors,
external stylesheets, scripts and unsupported layout values are not accepted.
The sanitizer preserves only these exact class names on existing email-safe tags;
general pasted stylesheets/arbitrary classes remain unsupported.

Normal authored checkout CSS overrides renderer structural defaults. The template
controls image maximum width, colours, backgrounds, typography, spacing and button
presentation. Old typed blocks without class CSS use the same default HTML file's
CSS as a render-only compatibility fallback, preserving stored drafts.

## Master editing and persistence

Automation → Templates offers **Use** and **Edit** for Collector Reminder. Edit
opens the actual saved HTML with a hydrated preview; **Save template** persists it
in existing `crm_runtime_state` under `abandoned_checkout_master_v1`. A row lock and
revision check prevent lost concurrent edits. No migration or production data
write was performed during implementation.

**Reset to default** restores the file's original HTML/CSS in the editor; Save
persists the reset. **Use** loads saved master HTML and copies it into the current
email as HTML Section 1, a native products section and HTML Section 2. It retains
the normal global header/footer. Existing drafts and published versions remain
independent; saving the master does not mutate them.

Master Save validates one marker, all contract CSS selectors, no Liquid, safe
HTML/static URLs, protected image/CTA ownership and the 95 KB template limit.
Hydrated final size is still checked at delivery. Publication rejects duplicate
native blocks and wrong trigger context. Invalid legacy preview styling can fall
back safely without relaxing master-save/live-publication validation.

## Send safety

Preview/Test/live use the same hydration + CSS compilation. Test still disables
the real recovery action. Live rendering still checks exact enrollment checkout
identity/customer and recovered state before hydration. Latest/sample preview data
cannot substitute into live sends. Lookup, consent, recovery, tracking and transport
logic are unchanged; no Shopify/customer API calls were added for styling.

## Local validation

- Combined Python regression: **188 passed, zero skipped**, using disposable
  loopback PostgreSQL and mocked providers. Subsequent focused run: **72 passed**.
- Browser: white variant → gold, white title → red, custom CTA background; changes
  visible in master preview. Save/reopen persistence, Use, unchanged existing draft,
  Reset and email widths 600/430/390/375/320 passed.
- Existing legacy/sample/idle browser checks remain part of validation.
- Python compilation and `git diff --check` passed.

Table markup and final inline CSS provide conservative email-client fallback.
Actual Gmail/Outlook client rendering and production Shopify latency were not
tested. No live email, commit, push or deployment was performed.

## Files changed for this task

- `crm_abandoned_checkout.py`
- `crm_abandoned_checkout_ui.py`
- `crm_campaign_html.py` (exact checkout-class preservation only)
- `crm_checkout_preview.py`
- `crm_checkout_styles.py`
- `crm_checkout_template.py`
- `templates/abandoned_checkout_collector_reminder.html`
- `tests/test_crm_checkout_template_styles.py`
- `tests/test_crm_checkout_template_styles_ui.cjs`
- `tests/test_crm_automation_preview_stability.py`
- `docs/performance-evidence/checkout-template-styles.png`
- `docs/performance-evidence/checkout-fallback-real.png`
- `docs/performance-evidence/checkout-fallback-sample.png`
- this report
