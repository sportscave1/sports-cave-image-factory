# Frame-synced email banner — implementation and verification

Template: **See It In Your Cave — Frame-Synced Banner**. Available in the
existing Campaigns and Automations shared Templates library. Insertion uses the
existing independent middle-section copies, IDs, ordering and draft persistence.
The existing Abandoned Checkout and simpler Wall Preview sources are unchanged.

## Verified Shopify source (8 October 2026)

Read-only inspection of the main theme `189389340979`, Sports Cave - On-Demand
Wall Preview, covered:

- `sections/sc-wall-preview-banner.liquid` (retired launcher)
- `sections/sc-wall-preview.liquid`
- `snippets/sc-wall-visualizer-v1.liquid`, `sc-wall-lifestyle.liquid`,
  `sc-wall-preview-button.liquid`
- `assets/sports-cave-wall-artwork.js`, `sports-cave-wall-banner.js`,
  `sports-cave-wall-banner.css`, `sports-cave-wall-lifestyle.css`,
  `sports-cave-wall-preview-loader.js`, `sports-cave-wall-preview.js/css`

The renderer requests a center-cropped square CDN source, nominally 2000px,
then maps these rectangles from a 1000-unit coordinate system:

| Frame | x | y | width | height |
|---|---:|---:|---:|---:|
| Black | 30 | 151 | 930 | 692 |
| Oak | 27 | 148 | 938 | 696 |
| White | 31 | 148 | 934 | 696 |
| Unframed | 85 | 208 | 822 | 581 |

The passive website room banner always uses XL, irrespective of selected size.
This email therefore uses the permitted **clean artwork fallback**, not a claim
to reproduce the room composite or its physical scale. Actual variant/size text
remains visible. No frame, shadow, transform, canvas or JavaScript is added to
the email. The server emits a 1200px JPEG with preserved crop proportions.

Public product verification covered Six Laps Ahead Peter Brock Wall Art and
Jack Brabham — Built To Win 1966 Wall Art: 32 variants, Black/Oak/White/Unframed,
S/M/L/XL. All 24 framed variant images matched their theme sources. The eight
unframed variant images differed: Shopify's visualizer uses the Black image's
interior. The email intentionally retains the original unframed checkout image.
These are public variant-image comparisons, not reads of real customer carts.
Runtime matching uses the actual resolved checkout image before applying crops.

The store's `/cdn/shop/files/` URLs and its verified
`cdn.shopify.com/s/files/1/0722/2332/6515/files/` namespace are aliases. Matching
requires the same filename and image revision. Unknown frame, source mismatch,
non-square source, failed mapping or failed public storage preserves the verified
original image. Invalid/unavailable images produce a text-only section. No valid
product destination means no CTA. Generic campaigns render the neutral section
without inventing customer/product data; administrators can edit their inserted
copy and explicitly configure static content and a product URL.

## Data and delivery boundaries

- Resolve only a rendered copy; never write checkout data into saved templates.
- Select the first eligible public artwork product. Leave all original cart rows
  and the protected checkout insertion marker unchanged.
- Abandoned automation dispatch still verifies the bound checkout/customer ID.
- CTA reuses the deployed `variant=…&sc_wall_preview=1` deep-link contract.
  Original query strings/fragments are discarded; no recovery token is exposed.
- Image fetching accepts only public Shopify image paths, bounded response sizes
  and bounded timeouts, without redirects. Decoding and pixel limits are checked.
- Bounded ten-minute process caches avoid repeat mapping/image work. Asset names
  hash only public product, variant, source revision, crop and template revision.
- No schema migrations, workers, scheduler changes or new dependencies.

## Configuration / rollout

Use the existing R2 assets bucket and credentials. Set
`CRM_EMAIL_ASSET_PUBLIC_BASE_URL` to the durable HTTPS public root corresponding
to `R2_BUCKET_ASSETS`. Keep `email/frame-banner/` objects available indefinitely;
do not apply a short expiry/lifecycle policy to already emailed assets. Do not
make unrelated private certificate buckets public. Signed expiring URLs are not
used. Uploads reuse the existing R2 service and require a successful public HTTP
read-back before the generated URL is returned.

That public base is **not configured in this development environment**. Actual
R2 writes were mocked, not performed. Without configuration or during failure,
verified original images remain the fallback. Configure the app and existing
email worker consistently during the normal deployment workflow. No deployment,
theme modification, publishing action, customer send or live automation edit was
performed. No new flow is automatically enabled.

## Tests and evidence

- 54 focused unittest checks passed, including disposable PostgreSQL campaign
  and automation save/reopen/duplicate tests, original templates, rendering,
  all frame/size combinations, mismatch/fallback handling, image verification,
  storage confirmation, recipient binding, hidden sections and protected markers.
- Local Chrome: eight comparisons against the captured **unmodified Shopify
  canvas renderer**. Maximum mean RGB difference 2.40/255 after JPEG encoding and
  browser/server resampling. Crop geometry matches. Unframed comparisons are
  explicitly labelled reference-only; they are not substituted into emails.
- Desktop (1000px) and mobile (375px) screenshots passed overflow/link checks,
  with no JavaScript errors. Visually inspected frame boundaries and mobile HTML.
- Python compile checks and `git diff --check` passed. This Python/Streamlit
  change has no separate frontend production build or configured type checker.
- The broader existing preview-stability suite has one unrelated source-text
  assertion failure: it expects `not any(s['type']==BLOCK` in `crm_section_ui.py`.
  The same text is absent in the unchanged HEAD version. It was not rewritten
  to mask the pre-existing failure.
- The bundled Shopify theme validator could not load its missing
  `@shopify/theme-check-common` dependency; no theme source was changed.
- Gmail/Outlook mailbox delivery was not tested; no internal or customer test
  email was sent. Public durable storage still needs deployment verification.

Reproduce read-only visual evidence:

```
.venv\Scripts\python.exe scripts/verify_frame_banner.py
node tests/test_crm_frame_banner_visual.cjs
```

The latter uses installed Chrome and the available Playwright runtime. Local
evidence lives in `artifacts/frame-banner/` (git-ignored): product comparison
JSON, source/crop images, desktop/mobile screenshots and `shopify-vs-server.png`.
Captured theme fixtures are test-only; never upload them as theme changes.

## Changed files for this feature

New runtime files: `crm_frame_banner_template.py`, `crm_frame_banner_assets.py`,
`templates/frame_synced_banner.html`.

Integration: `crm_campaign_library.py`, `crm_campaign_content.py`,
`crm_middle_sections.py`, `crm_abandoned_checkout.py`, `crm_checkout_preview.py`,
`crm_automation_runtime.py`, `crm_automation_store.py`.

Verification: `tests/test_crm_frame_banner.py`,
`tests/test_crm_frame_banner_visual.cjs`, `scripts/verify_frame_banner.py`,
`tests/fixtures/wall_banner/sports-cave-wall-artwork.js`,
`tests/fixtures/wall_banner/sc-wall-visualizer-v1.liquid`, this document and the
local-artifact exclusion in `.gitignore`. Existing Edition Ops changes in the
working tree were preserved and are not part of this feature.
