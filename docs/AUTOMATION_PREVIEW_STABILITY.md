# Automation preview stability and performance

## Findings

The abandoned-checkout canvas ran every three seconds. The action-row size meter
ran every two seconds. Both invoked checkout preview hydration. The context loader
automatically started another Shopify lookup when its 45-second TTL expired.
The canvas repeatedly emitted `components.html` iframe output even with unchanged
content. Local baseline browser observation recorded one iframe load over 30 idle
seconds; server logs confirmed the recurring three-second canvas emissions.
This does not establish the frequency of production flashes.

Size also used a separate production render from the visual preview. Editor HTML
inputs already had a 750 ms debounce; there was no need to invent new persistence.
Email step analytics are opt-in, and the automation home fragments do not poll
while the editor is open. No React effect or external frontend framework is involved.

## Changes

- Removed the Automation-only Live Preview button, dialog and timed canvas functions.
  The embedded Email Preview is the authoritative hydrated visual preview.
- A stable keyed component owns the email iframe. Only a changed final HTML digest
  assigns `srcdoc`; device switches only change width. Content changes restore the
  previous internal scroll position after load.
- There are no settled-state polling timers. While the initial/manual checkout
  lookup is pending, a small completion bridge checks once per second; it stops
  when resolved. One completion rerun updates the action row without remounting the
  keyed iframe. No background refresh starts solely because the cache TTL expires.
- Editor entry checks the existing 45-second cache once. The async checkout read
  starts before sender/default settings are loaded, allowing those reads to overlap.
  A small refresh icon explicitly refreshes checkout context. Last-good data stays
  visible; an identical checkout does not replace the iframe.
- Hydration/legacy substitution is cached by document + context digest. Final
  production HTML and byte analysis are cached by hydrated document + settings +
  automation identity. Preview and size use that same message. The compact size
  component receives changed size output directly from the preview, without a timer
  or a second render. Already-loaded email defaults are reused.
- Automation HTML inputs debounce at 350 ms; Campaigns retain their 750 ms setting.
  Existing autosave/recovery behaviour remains intact. The preview has more viewport
  height, compact device/refresh controls and a muted amber legacy warning.
- Existing duplicate-native-block prevention remains intact. The warning clears
  when legacy source is removed. No new Shopify/product/image downloads are added.

## Safety

Live automation delivery, publication, enrollment-bound checkout resolution,
recovery/customer checks and 95 KB validation are unchanged. Send Test still makes
its existing fresh checkout verification and disables recovery links. Preview
latest/sample context cannot enter live delivery. No schema, worker or transport
changes were made. The shared section component receives an Automation-only debounce
argument; its Campaign default remains unchanged. The shared size module adds a
separate automation function, leaving Campaign polling/render behaviour intact.

## Local evidence

- Combined Python regression suite: **179 passed, zero skipped**, with loopback
  PostgreSQL and mocked providers. Covers native automation/send isolation, checkout
  fallbacks, persistence, campaign send flow, tracking, sections, size and first paint.
- Six focused stability tests include stable digests, hydration reuse, render/size
  reuse, expired context reuse during editing and Automation-only debounce/polling.
- Synthetic 60-second TTL comparison: old polling path makes two checkout lookups
  including initial load; new idle path makes one. This is simulated timing, not
  measured Shopify latency.
- Local browser: 60 idle seconds produced **zero preview replacements, iframe loads
  or scroll resets**. Twenty continuously typed characters produced **one** preview
  update. Desktop/mobile changes produced no HTML replacement. Shopify fixture count
  remained **one** after initial lookup, idle, typing and saving.
- Browser tests cover a delayed real checkout lookup and a provider-failure sample,
  retained sections, resolved size, absent Live Preview action and viewport controls.
  OS widths: 1920, 1600, 1440, 1366, 1280, 1024, 768, 390, 320. Email widths:
  600, 430, 390, 375, 360, 320. Screenshots are synthetic fixture data only.
- Python compilation, JavaScript syntax checks and `git diff --check` passed.

There is no controlled before/after production initial-load benchmark or live
Shopify latency measurement. No live test email, production change, commit, push or
deployment was performed.

## Files

Runtime: `crm_abandoned_checkout.py`, `crm_abandoned_checkout_ui.py`,
`crm_automation_store.py`, `crm_automation_ui.py`, `crm_automation_preview_cache.py`,
`crm_email_size_ui.py`, `crm_section_ui.py`, `components/crm_sections/composer.js`,
`components/crm_automation_preview/index.html`, `components/crm_automation_preview/preview.js`.

Tests/evidence: `tests/test_crm_automation_preview_stability.py`,
`tests/test_crm_abandoned_checkout.py`, `tests/test_crm_checkout_preview_fallback_ui.cjs`,
`tests/fixtures/crm_automation_preview.py`,
`docs/performance-evidence/checkout-fallback-real.png`,
`docs/performance-evidence/checkout-fallback-sample.png`.
