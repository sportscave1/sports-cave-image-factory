# Lifestyle image sections

Three built-in inserts in the existing Templates library:

| Name | Token | Product gallery position |
| --- | --- | --- |
| Lifestyle Image 1 | SC_LIFESTYLE_IMAGE_2_URL | 2 |
| Lifestyle Image 2 | SC_LIFESTYLE_IMAGE_3_URL | 3 |
| Lifestyle Image 3 | SC_LIFESTYLE_IMAGE_4_URL | 4 |

Use **Templates → Use** to append an independent editable HTML section. Existing
sections and the protected checkout marker are retained. The same tokens work
when pasted into existing HTML. Normal section ordering, names, visibility,
deletion, saving and duplication remain available.

## Data and rendering

`crm_lifestyle_images.py` selects the leading product from the existing checkout
context, matching the existing featured-product convention. It does not use the
selected variant image or switch to another checkout line when data is missing.
The existing `Shopify.campaign_images` adapter uses product media POSITION order,
excludes non-image media and reuses its shop-scoped 60-second query cache. Pages
are bounded; only the first four images are retained. Invalid image URLs keep
their positions rather than shifting later images forward.

The existing proportional email image URL is used without cropping or generation.
Resolution happens on copies at preview/test/recipient rendering time. Drafts and
published snapshots retain tokens. Missing, unsafe or unavailable images remove
the entire corresponding img element. No fallback image or customer-facing
explanation is inserted. The editor explains when no checkout context exists.
Recipient ownership checks remain in the existing automation dispatch path.

Shopify reference: [Product media](https://shopify.dev/docs/api/admin-graphql/2026-04/objects/Product)
and [POSITION ordering](https://shopify.dev/docs/api/admin-graphql/2026-04/enums/ProductMediaSortKeys).

## Changed files

- `crm_lifestyle_images.py`, `templates/lifestyle_image.html`: snippets and resolver.
- `crm_campaign_library.py`: three built-in insertable library entries.
- `crm_abandoned_checkout.py`, `crm_checkout_preview.py`: render-copy hydration.
- `crm_automation_runtime.py`, `crm_automation_store.py`: recipient, editor and test contexts.
- `crm_campaign_content.py`, `crm_middle_sections.py`: safe omission without context.
- `crm_campaign_html.py`: valid image-only HTML counts as content; existing URL/alt validation remains.
- `crm_html_workspace.py`: editor-only missing-context explanation.
- `tests/test_crm_lifestyle_images.py`, `tests/test_crm_lifestyle_images_ui.cjs`,
  `tests/fixtures/crm_automation_preview.py`: mocked gallery, persistence and browser checks.

## Verification

- 38 tests passed across lifestyle, wall preview, simple editor and frame banner suites,
  including real SQL against the disposable localhost database.
- Wider checkout/section/flow regression suite: 68 passed, one existing failure in
  `SectionPersistenceTests.test_ui_defaults_rerun_and_edits_persist_without_hidden_conversions`.
  It expects no `html_sections` after an existing save normalization; reproduced
  unchanged using HEAD modules in memory. No unrelated behavior was changed.
- Chrome browser: three inserts, correct mocked gallery URLs, original checkout
  retained, saved draft reopening, unchanged subject, no JS/Streamlit exceptions.
- Responsive geometry checked at 320, 375, 600 and 1200px; width never exceeds 520px.
- Modified Python modules compile; `git diff --check` passes.

Tests block external browser requests and use synthetic checkout/gallery records.
Native Outlook, Apple Mail and Gmail clients were not available; inline table
markup is email-safe, but client-specific rendering was not independently certified.
External schema validation was blocked by automatic approval review because the
helper may transmit repository code/task text. The existing GraphQL query was
not changed; its adapter behavior was tested locally.

## Rollout

No database migration, new service or configuration is required. Deploy the
updated app and existing email worker together through the normal workflow.
The entries appear automatically; insert them only into the drafts desired.
Existing published automations are not edited or republished by this change.
No deployment or real email send was performed during implementation.
