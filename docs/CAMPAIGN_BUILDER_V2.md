# Campaign builder V2 — local implementation and verification

Implemented locally on 29 September 2026. No commit, push, deployment, customer email,
Shopify product update or Edition Ops write was performed. Marketing configuration,
audience rules, normal Inbox and staff/admin signatures are unchanged.

## Existing architecture and compatibility

The existing Streamlit Campaign workspace, template controls, renderer, JSONB draft
document, version history and internal-test service remain in use. There is no new
database, table or migration.

An old `custom_html` Body is interpreted as HTML Section 1 without altering its
source or writing a draft on page load. An optional `middle_sections` array is
persisted on editing/saving. Each entry has a stable ID, type and visibility. HTML
entries also have an HTML number and exact source. Catalogue entries contain ordered
product snapshots and display settings. Array order is display order; no competing
position field is maintained. `custom_html` mirrors HTML Section 1 for compatibility
and is validated for consistency. The duplicate mirror is excluded from the document
size calculation so it does not halve the existing authored HTML allowance.

Old full-document campaigns retain their existing rendering path. Existing Header /
Footer templates, compliance validation and unsubscribe behaviour are unchanged.
Dormant block capabilities remain. Template save/load and duplication preserve the
new section structure. Automations execution/trigger/timing code is untouched.

## Editing

- Header and Footer remain outside the sortable component, with checked labels and
  their existing template selectors/editors. Neither has hide, remove or drag controls.
- HTML Section 1 starts open and blank for new campaigns. It cannot be removed but
  can be hidden. Additional HTML sections retain their numbers when reordered.
- A small Add section menu directly above Footer adds HTML or Catalogue. No Catalogue
  exists by default. Multiple catalogue blocks are supported.
- Middle sections have compact visibility checkboxes, drag handles and accordions.
  Hidden sections retain all data but are excluded from HTML, plaintext and tests.
- Drag only starts from the handle. Alt+Up/Down provides keyboard ordering. Product
  rows inside a Catalogue have the same ordering mechanism and individual removal.
  Removing an entire extra section requires confirmation.
- UI updates use the existing Streamlit component bridge and a Campaign fragment,
  rather than rerunning the whole OS shell. Accordion state and textarea focus are
  retained. Explicit event acknowledgements, event IDs and queued edits prevent
  repeated or unchanged actions from leaving controls pending indefinitely.

Bounds: 20 middle sections, 12 products per Catalogue and 50 unique products per
campaign. Existing HTML/render size safeguards still apply.

## Read-only product and edition sources

**Browsing:** the existing synced `shopify_products` table, searched by title/handle,
with an Active filter and 12-row pages. It is read in a read-only transaction with a
bounded statement timeout. The picker does not render the full catalogue or start a
Shopify product sync.

**Current product facts:** the existing `crm_shopify.Shopify.query` service performs
a batched Admin GraphQL `nodes` query for the selected IDs. It reads title, handle,
status, `onlineStoreUrl`, featured image, and
`contextualPricing(context: country).minVariantPricing` price/compare-at values.
No prices are hardcoded. AU/US/UK preview markets use their respective country
context; the existing Global market uses AU. Image transforms request JPEG; existing
safe image handling is retained.

**Edition facts:** `supabase_backend.list_edition_products_read_only`, the same
Edition Ops query over `edition_products`, active `edition_runs` and
`edition_orders` integrity checks. The only shared backend change is optional exact
product-ID/handle filters on this read query. Its existing callers behave unchanged.
No schema provisioning, edition allocation, counter reset, run creation or update
is called.

Matching prioritises Shopify product IDs (numeric/GID normalised). A unique handle
match is accepted only for a legacy row without a product ID. Conflicting,
ambiguous, blocked, inactive or missing mappings never fabricate an edition number.
The editor reports unavailable edition data; customer output omits those lines.
Wording is “Next available #037 / 100”, never “Your edition”.

Opening a blank Campaign makes no catalogue call. Opening the picker loads one page.
Only selected visible products are resolved on opening a saved draft, changing
market/selection, or explicitly refreshing facts. Viewport changes reuse the existing
content-hash render cache and do not query Shopify or Edition Ops. Cached display
data does not become edition truth.

## Rendering, validation and send snapshots

The canonical renderer assembles Header + visible middle sections + Footer. Cards
use escaped data, presentation tables, safe links/images and the existing sanitizer.
One-column feature cards and a default two-column grid are available. The existing
600px wrapper and responsive `sc-stack` media rule stack cards on mobile. Only that
known responsive TD class is newly allowlisted; executable markup remains blocked.
Desktop/Mobile preview controls and backend widths 600/430/390/375/320 remain intact.

Missing required product title, active status, HTTPS URL, enabled image or enabled
price produces an editor/preflight error. Optional edition mapping failures do not
break a valid product. Unsafe or credential-bearing URLs are excluded. Snapshots
store only whitelisted public product facts. Plaintext includes product names,
edition wording, prices and destination URLs through the same rendering pipeline.

Before a new internal-test operation, visible catalogue facts are read fresh. If they
differ from the saved preview, the test stops with a refresh/review/save instruction;
it does not silently send different content. If facts cannot be verified, sending
stops with a safe error. Once valid, exact rendered HTML/plaintext, product facts,
edition values, order, render hash and operation ID are recorded as
`campaign_test_snapshot` in existing campaign history **before** provider I/O.
Later counter changes do not mutate the snapshot. Existing admin, allowlist,
confirmation, preflight, marketing-off and duplicate-operation safeguards remain.
No production sending path is enabled.

## Files changed

Production additions:

- `crm_middle_sections.py`: section model, event validation, compatibility and assembly.
- `crm_catalogue.py`: paginated index, current Shopify/Edition reads, safe cards.
- `crm_section_ui.py`: component bridge, compact product picker, acknowledgements.
- `components/crm_sections/index.html`, `composer.js`, `style.css`: small dependency-free composer.

Existing production files extended:

- `crm_campaign_page.py`: fragment boundary, template state, passes shared Shopify service.
- `crm_html_workspace.py`: fixed Header/Footer around the modular middle editor.
- `crm_campaign_content.py`: validation and canonical rendering integration.
- `crm_campaign_sections.py`: ordered middle assembly within existing Header/Footer.
- `crm_campaign_html.py`: safe responsive TD class preservation.
- `crm_preview_cache.py`: includes middle sections in the content hash.
- `crm_campaign_store.py`: content history and durable verified outbound snapshots.
- `crm_workspace_store.py`: saved designs retain middle sections.
- `supabase_backend.py`: optional read-only edition lookup filters only.

Tests and evidence:

- Added `tests/test_crm_modular_catalogue.py` (19 focused tests).
- Added `tests/test_crm_sections_component.cjs` (13 checks).
- Updated `tests/test_crm_campaign_sections.py`, `tests/test_crm_html_workspace.py`
  and `tests/test_email_navigation.py`
  to exercise the new component state rather than the removed Body textarea.
- Added `tests/catalogue_preview_app.py` and `tests/catalogue_drag_preview.py` for
  repeatable isolated browser verification.
- This report and four images in `docs/campaign-builder-v2-evidence/`.

## Validation results

| Check | Result |
| --- | --- |
| CRM discovery with disposable PostgreSQL enabled | 201 passed |
| Email regression discovery | 355 passed, 1 SQL-gated test skipped; covered by SQL-enabled navigation run |
| Navigation suite with disposable PostgreSQL | 6 passed |
| Startup scope suite | 6 passed |
| Edition catalogue/stability/allocation-integrity suites | 29 passed |
| New section JavaScript tests | 13 checks passed |
| Existing CRM pixel and 6 Email component suites | Passed |
| Python compilation | 18 changed/added Python files passed |
| JavaScript syntax | Passed |
| `git diff --check` | Passed |

Navigation and startup were run in separate processes: their combined test invocation
exposes an existing Streamlit mock/context interference. Each passes independently.
No application workaround or unrelated permission change was made for that test issue.

Focused tests cover legacy content, fixed ends, numbering, visibility, ordering,
removal confirmation, product mapping/escaping/validation, lazy loading, read-only
queries, render-cache invalidation, picker cancellation/selection, JSON persistence,
templates, duplicate drafts, exact pre-send snapshots, changing facts, safe failures
and duplicate-send prevention. Existing responsive, template, compliance, Flow and
mailbox tests remain in the regression suites.

## Browser verification

Used the actual OS/Campaign UI with fake Shopify/edition facts and disposable local
SQL. The fixture blocks production HTTP/SMTP/IMAP/database I/O. Screenshots intentionally
use the public Sports Cave logo for synthetic artwork thumbnails; they are not evidence
of live catalogue contents.

- 1920×1080: compact section controls and large desktop preview.
- 1440×900: usable catalogue/editor, internal scrolling, no horizontal overflow.
- 1366×768: usable controls and vertically stacked 390px Mobile email preview.
- Verified optional Catalogue creation, search, selection, cancellation, product
  removal, keyboard reordering, hide/show, HTML edits, save and recent-draft reload.
- Mouse dragging sections and products was verified in the standalone host of the
  exact component. The browser driver cannot drag through Streamlit iframe boundaries;
  keyboard ordering and persistence were verified in the full app.

Evidence: [1920 desktop](campaign-builder-v2-evidence/desktop-1920.jpg),
[1440 desktop](campaign-builder-v2-evidence/desktop-1440.jpg),
[1366 mobile preview](campaign-builder-v2-evidence/mobile-1366.jpg),
[product picker](campaign-builder-v2-evidence/picker.jpg).

Ready for Nathan's local acceptance testing. The live Shopify permission/catalogue
coverage and live Edition Ops mappings have not been exercised by these isolated
tests. A read-only acceptance check against those configured sources remains before
deployment approval. No migration is required. Nothing has been deployed or sent.
