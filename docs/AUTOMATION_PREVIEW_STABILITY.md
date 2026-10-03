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
  when resolved. Completion stays inside the preview fragment; the size report is
  delivered through the existing scoped browser event. No background refresh starts solely because the cache TTL expires.
- Editor entry creates a dedicated session pin and fetches once; backend TTL expiry
  cannot replace that pin. The async checkout read
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


## Follow-up: pinned context and rerun dimming (2026-10-03)

A controlled browser run of the previous implementation stayed stable for 90 idle
seconds: zero additional checkout requests, inner iframe loads or replacements.
A two-second full app rerun did reproduce dimming: effective iframe opacity fell
from 1 to 0.33. Streamlit marks retained element containers `data-stale=true` and
applies its built-in fading transition, independently of inner iframe loading.
No production periodic trigger was measured; do not interpret the local result as
proof of which production background event initiates reruns.

There was also a full app rerun on async checkout completion and a single-entry
hydration/output cache shared by the size meter and canvas. Their distinct document
representations evicted one another. Local instrumentation measured hydration
counts advancing 5 → 7 → 9 on successive full reruns. The bounded four-entry caches
now retain both representations: 2 → 2 → 2. Final HTML SHA-256, rather than the input
cache token, controls iframe replacement. Unchanged HTML stays mounted even if
nonvisual input changes require a fresh validation/render.

The dedicated `_automation_checkout_pin` is isolated from other preview lookups
and Send Test. Its completed future, last-good context and load timestamp persist
until manual refresh, editor reopen or scope change (automation/step/trigger/shop).
Approved navigation away clears the editor scope; blocked unsaved navigation does
not. Failed refresh retains last-good data. This is preview state only, never a
live enrollment context. Namespace selection and existing shared lookup defaults
remain backwards compatible.

Only the two automation preview surfaces opt out of Streamlit stale opacity, via
an exact selector for their retained preview component. This is paired with pinned
data, bounded memoization and removal of the completion app rerun; it does not
hide fetch errors or change unrelated app loading indicators. Settled previews
have no timer. The existing one-second bridge runs only while an explicit lookup
is pending. Top-bar notification/planner status work remains unchanged; the planner
app-refresh bridge is restricted to Dashboard/Reporting/Weekly Review, not this
editor. Campaign polling, Inbox checks and Orders loaders remain unchanged.

Focused tests: editor pin survives 900 simulated seconds; failed refresh keeps the
pin; Send Test cannot replace it; navigation invalidation waits for approval;
identical HTML retains its digest; alternate representations reuse bounded caches.
Combined automation/email/Campaign/size/tracking regression suite: 138 passed,
zero skipped, using loopback PostgreSQL and mocked external providers.


Changed in this follow-up:
- Runtime: `crm_abandoned_checkout.py`, `crm_abandoned_checkout_ui.py`,
  `crm_automation_preview_cache.py`, `crm_automation_store.py`, `crm_automation_ui.py`.
- Shared navigation metadata: `crm_navigation.py`, only the successful departure
  from CRM Automations branch, to permit a fresh pin when returning. Other routing
  decisions and unsaved-draft protections are unchanged.
- Tests: `tests/test_crm_automation_preview_stability.py`,
  `tests/test_crm_automation_pinned_preview_ui.cjs`,
  `tests/test_crm_checkout_preview_fallback_ui.cjs`,
  `tests/fixtures/crm_automation_preview.py`.
- This document and regenerated real/sample synthetic preview screenshots.

The existing fallback browser test compares actual initial scroll position rather
than assuming every rendered email permits a 200px scroll. No new live data or
external provider calls are permitted by the fixtures.


Final browser verification (loopback fixture / mocked Shopify):
- 90 seconds idle plus a two-second global rerun: zero additional Shopify queries,
  zero iframe remounts/loads/HTML replacements, zero additional image requests,
  zero hydrations after settling. Effective preview opacity remained 1 throughout.
- Save/device changes reuse the pin. A newer checkout does not replace it until
  refresh. Each manual refresh makes one fixture lookup: changed product updates
  once, identical result makes no replacement, failure retains last-good preview.
- Existing real/sample fallback browser suite passes: 60-second idle stability,
  scroll retention, 20 typed characters → one update, device reuse, visible size,
  retained legacy surrounding HTML, editor/email viewport coverage.
- Python: 138 regression tests passed; final focused rerun 20 passed. Compilation,
  JavaScript syntax and diff whitespace checks passed. No live send, commit, push,
  deployment or production data modification.

Baseline 90-second idle also had zero extra queries/remounts/loads; baseline idle
hydration was not independently instrumented. The measured improvements are
rerun opacity (0.33 → 1) and repeated full-rerun hydration (+2 → 0), rather than a
claimed reduction in production idle Shopify latency or an unobserved timer.
