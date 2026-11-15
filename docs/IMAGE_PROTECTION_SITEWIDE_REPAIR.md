# Site-wide image protection — 2026-10-07.1

This repairs the existing OS policy and runtime. It does not introduce another security service.

## Causes

- The Shopify CDN runtime was older than the local/Render asset and still emitted a warning toast.
- A selector allowlist covered named gallery classes but missed secondary, newly injected and unfamiliar media.
- A custom Liquid PDP protection script operated independently of the OS policy, set inline handlers/draggable attributes and rescanned the DOM on every mutation. It also blocked DevTools shortcuts.
- The `disable-right-click` app embed independently cancelled document context-menu events. Its handler was identified in a real browser stack at the extension's `protector.js`. Turning off the OS module could not override that other listener.

## Single source of truth

Keep `storefront_image_protection` and the existing `/api/storefront-protection/config` endpoint. No policy migration or database setting write is required. Startup fails open when policy cannot be read; the script never assumes protection is permanently enabled.

The shared `shopify_theme/assets/sports-cave-image-protection.js` is also served by the existing Render `/storefront-protection-runtime.js` route. The compatibility loader and route architecture stay intact. Update Shopify's installed CDN assets as well as Render: deploying only one leaves another installation stale.

`window.SportsCaveImageProtection` exposes `disable()`, `update(policy)`, `refresh()` and `enable()` (refreshes the authoritative policy). Repeated installation is a no-op. `update` requires an explicit boolean `enabled`; enabling/disabling aborts old listeners, disconnects the optional watermark observer and removes owned styles/watermarks. A late config response cannot undo a subsequent disable.

Context-menu cancellation is now global and capture-phase, including text and background-image surfaces. Individual scope switches still control media-specific drag, selection, print and watermark treatment. Existing right-click/save action switches remain honored. Ctrl/Cmd+S is cancelled globally except editable controls. Text copying in inputs and ordinary document text remains usable. There are no DevTools-blocking shortcuts.

Image/media drag and selection are delegated through composed event paths, covering dynamic DOM and observable shadow-root media. CSS uses generic media and image-link selectors rather than product-specific classes. Touch callout/user dragging are disabled without cancelling touch/pointer events, so click, swipe and preview dragging remain available. No polling; only the optional watermark mode uses a MutationObserver.

Existing OS notice preferences remain readable for compatibility but are ignored by the runtime. The obsolete notice checkbox is removed; saving stores false. No warning/toast/alert is emitted.

## Shopify deployment changes

Starting live theme: `189360570675` (Sports Cave - App Glass Review 2026-10-07).
Protection-only review duplicate: `189361619251` (Sports Cave - Sitewide Image Protection 2026-10-07).

Only four installed theme files change:

1. `assets/sports-cave-image-protection.js` — shared runtime.
2. `assets/sports-cave-image-protection.css` — generic media selectors, reversible root flags.
3. `templates/product.json` — replace only the obsolete `custom_liquid_U9NT9N.settings.code` with a Liquid comment pointing to the central module; retain section ID, order and all other settings.
4. `config/settings_data.json` — set `current.blocks.18411043321589999057.disabled=true` for `shopify://apps/disable-right-click/blocks/app-embed/1a6da957-7246-46b1-9660-2fac7e573a37`. No other app embeds change.

This release deliberately excludes the separate product-page reorder audit. Source theme files and before/after evidence are saved locally under `.tmp-protection/`. The former live theme remains the rollback copy when the reviewed duplicate is published.

## Validation

- `tests/test_storefront_protection.cjs`: capture semantics, plain/dynamic/dialog/shadow media, no messaging, editable fields, click/swipe behavior, policy off/on, stylesheet cleanup, optional watermark cleanup, duplicate installation and request bounds. Run with Chrome and `SC_BROWSER=msedge`.
- `tests/image_protection_silent_scale.cjs`: existing 12 upload/camera/scale/close Wall Preview journeys with protection enabled.
- `tests/image_protection_wall_camera.cjs`: protected camera, shutter and purchase eligibility using a fake camera.
- `tests/test_image_protection.py` and `tests/test_image_protection_sidebar.py`: policy, API, permissions and existing OS screen.
- `tests/image_protection_storefront.cjs`: real Shohei Ohtani, Kobe/Jordan, collections/all and homepage. Defaults to Chrome 1920×1080, Edge 1440×900, iPhone-style Chromium 390×844 and Android-style Chromium 430×932. `SC_THEME_ID` selects the draft; absent selects live. `SC_PROTECTION_CART=1` permits isolated empty-session cart tests with item cleanup, never checkout submission. No persistent OS policy writes occur.

The mobile browser personas are emulation, not physical Safari testing. Native iOS long-press suppression still needs a real-device check. This is browser-side deterrence, not prevention of screenshots, DevTools access or determined downloads. Cross-origin frames and browser/OS-owned UI are outside document listener control.

Use the existing primary `sports-cave-os` service `srv-d8kl4on7f7vs73dvavv0`; do not create or rename services or sync a Blueprint. Run the topology validator and deploy the isolated repair commit through the established main-branch workflow. Check Render deploy status and the served runtime version, then verify the published storefront. Preserve rollback evidence and report any unrelated storefront errors separately.
