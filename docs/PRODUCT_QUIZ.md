# Find Your Edition — local implementation handoff

Implemented 17 October 2026 in Studio task `20261016-dc6e78ee`, owned by
`codex/quiz-20261017-7f070a2b`. Worktree/branch retained, uncommitted. No deployment,
production data change, Shopify installation, email, theme edit or new Render service.

## Management and customer experience

All controls are in **Developer → Product Quiz**, one registered admin-only child
using the existing sidebar disclosure, history, active-state and responsive styling.
There is no Marketing entry. Questions/answers, order/enabling, rules, canonical
aliases, classifications/exclusions, featured preference, appearance, preview,
publish/revert, reporting and installation are tabs on that route.

The customer component has two placements: a manually launched native modal and
an inline page. Its shadow DOM isolates all styles. Native dialog keyboard/focus
containment, Escape, launch-button focus restoration, Back, restart, responsive
cards, searchable long option lists and progress are implemented. Neither placement
asks for email. The component is not an iframe or an admin page.

Only questions that distinguish eligible product sets are asked. Choices come from
the refreshed catalogue; answer overrides rename or suppress real values. Changing
an earlier answer clears later answers. Explicit sport and athlete/team selections
are mandatory matching constraints. Up to three distinct results are returned;
featured preference orders relevant matches only. Optional-preference relaxation
is labelled honestly and never crosses an explicitly selected identity.

## Preview

Generate the standalone synthetic harness, without starting/importing the OS:

```powershell
python -B tests/fixtures/product_quiz_preview.py
```

Open `tmp/product-quiz-preview/index.html` directly in a browser. It contains both
placements and embedded code/artwork, synthetic prices and no tracking/network
requests. `tests/product_quiz_browser.cjs` produces `desktop.png` and `mobile.png`
in the same directory. The live OS editor also has a draft preview with explicitly
synthetic commerce facts, never a purchase or production checkout.

## Data, eligibility and refresh

Stable Shopify IDs join `shopify_products` to the existing edition ledger (both
legacy numeric IDs and GIDs). Ambiguous ledger identities are flagged. Shopify
publication, online-store URLs and public CDN images are authoritative. The
edition ledger excludes closed/exhausted editions. An hourly read-only catalogue
reconciliation also checks tracked inventory **and** `CONTINUE`/`DENY` policy;
untracked or continue-selling editions are not excluded just for zero quantity.
Unknown selling policies or truncated unavailable variant lists need review.

Structured custom sport, athlete, team, moment, era and style fields, existing
audited sport/subject collection mappings and curated exact full identities enrich
classification. Rivalry and multi-athlete arrays are supported. Weak/contradictory
classifications are flagged. The existing PSD mapping store was inspected: it maps
Shopify IDs to private file identity/path, not authoritative subject/era/style
fields. No PSD scan, mapping approval gate or private file URL enters the quiz.

When explicitly enabled, the existing worker runs a quiz reconciliation thread:
it consumes the existing mirror changes every 60 seconds and does a complete,
paginated, read-only Shopify reconciliation hourly to recover missed events and
deleted/unpublished products. The complete-list ID snapshot is updated only after
a successful listing; new products can take up to the next hourly reconciliation
to appear after an earlier complete-list snapshot. No allocation, counters,
certificate, fulfilment or Shopify metafield mutation is called by this work.

Draft/published settings and catalogue snapshots are separate. Classification
overrides survive refreshes. Hash-addressed sport shards are uploaded only when
their contents change. Catalogue changes require no question publication and no
snippet replacement. Per-object payloads are capped at 250 KB; a larger sport
shard fails reconciliation visibly and preserves the previous catalogue.

Before showing results, Shopify's locale-aware Ajax Product API checks identity,
available variants and their minimum purchasable price. Requests retain same-origin
market cookies, and currency comes from the locale-aware cart endpoint. A failed
market/availability read never turns stale catalogue prices into purchasable cards.
Inventory quantity alone is never used to determine customer availability.

## Public delivery and publication

Reuse the existing R2 assets bucket through its public CDN/custom domain; no new
primary service. Set, in a separately approved release:

- Existing R2 connection variables and `R2_BUCKET_ASSETS`.
- `PRODUCT_QUIZ_ASSET_BASE`: the public HTTPS bucket base, **without** `/product-quiz`.
- `PRODUCT_QUIZ_ENABLED=true` on the existing main app and worker only when ready.
- Optional `PRODUCT_QUIZ_ANALYTICS_URL`: the deployed app's `/api/product-quiz/events`.
- `PRODUCT_QUIZ_ALLOWED_ORIGINS`: exact HTTPS storefront origins, comma-separated;
  defaults are the bare and www Sports Cave shop domains.
- Public R2 GET access and CORS for JSON fetches from both storefront origins.

`product-quiz/loader.js` is the stable deferred loader. Button placement makes no
configuration/catalogue/runtime request before the customer launches it. Inline
placement waits until visible. The loader resolves immutable runtime/config URLs
from `manifest.json`; only the selected sport shard is downloaded. Initialization
is idempotent across repeated scripts, multiple mounts and Shopify section reloads.

Publishing validates a saved draft revision, verifies collection context against
actual mirrored mappings, writes immutable dependencies and durable version history,
then switches one R2 object atomically. Earlier upload failures leave the old
pointer intact. A timeout on the final pointer write is reported as unconfirmed;
the pointer will refer to a complete old or new version. Revert switches back to
the previous configuration; catalogue availability stays independently current.
Concurrent OS publishers/reconcilers use one Postgres advisory lock.

The public assets/config/catalogue are served from R2 independently of the OS
process. A temporary OS outage does not require the OS to serve those files.
For safe edition availability, a catalogue older than two hours fails closed to
the browse fallback. Shopify itself and R2/CDN must still be reachable. Analytics
failure never blocks the quiz.

## Exact installation snippets and Shopify placement

**Public endpoints are not deployed or verified in this task. There are no working
production installation snippets to paste yet.** The Install tab deliberately
withholds snippets until its explicit public-delivery verification succeeds.
It checks the published pointer, config, runtime, loader, catalogue and CORS without
credentials. No placeholder URL is described as a working installation.

After approved release and successful publication, **Developer → Product Quiz →
Install → Verify public installation assets** provides the exact copyable
collection-button and inline-page snippets. Each contains only a mounting element,
optional verified collection context, browse fallback and deferred stable loader.

1. Open **Online Store → Themes → Customize** in Shopify. On the collection
   template, add a **Custom Liquid** block and paste the collection-button snippet.
2. Manually create a page **Find Your Edition**, handle `find-your-edition`, for
   `/pages/find-your-edition`. Give it a dedicated template if necessary.
3. Add a **Custom Liquid** block to that page template and paste the inline snippet.
   Custom HTML works only when that block permits scripts.
4. Save/publish those placements yourself. No automated theme edit, app installation,
   page creation or email change is performed here. Future OS updates keep the
   snippet unchanged.

## Analytics and limitations

Anonymous starts, question views/answers, completions, closes and product clicks use
random session/event IDs and immutable quiz version IDs. Events are allowed only
when Shopify's existing privacy API explicitly permits analytics processing.
No consent API/permission means no event. Source is a small enum: collection,
page or tagged campaign. No raw URL, campaign text, answers, email, customer ID or
private artwork is collected. Quiz participation changes no subscription.

Namespaced records reuse the existing private, RLS-enabled, server-only
`crm_runtime_state` table; no migration or public database access is introduced.
Event insert conflicts are ignored; reports group distinct sessions by question,
source and version over 30 days. Retention is 90 days. These are browser-measured
interactions, not trusted purchase evidence. This modest first version uses the
runtime-state table; higher-volume reporting would warrant a dedicated event table.

Add-to-cart, purchases, attributed revenue and customer association are unavailable.
The displayed intended purchase window is seven days, inactive until trustworthy
attribution is implemented. There is no incremental-revenue claim. Existing wall
preview/CRM tracking and paid-order handling are preserved.

The public catalogue request encountered the storefront verification screen.
Existing catalogue fixtures were inspected, but a current live classification count
has not been established. The Catalogue tab identifies exact products needing
details after the first approved reconciliation; no zero-missing-products claim is
made. Full OS startup, live R2 publication, real-store market checks and final manual
Shopify installation remain release acceptance steps.

## Local verification

- Python quiz contracts: classification across sports/rivalries, exclusions,
  aliases, selling-policy edge cases, private-data projection, incremental shards,
  draft/publication/revert and injected publication failures, context validation,
  analytics input validation, admin navigation, and isolated editor draft save.
- Existing sidebar, top-bar and worker regressions.
- Fully intercepted browser harness: desktop/mobile rendering, dialog keyboard and
  focus, deterministic matching, repeated/multiple/section initialization,
  lazy loading, current market currency, cheapest **available** variant,
  consent/deduplication, no-match/unavailability and loading fallback.
- JavaScript syntax, Python AST, diff whitespace and Render topology checks.
- Shopify Admin selling-policy query validated against the project's `2026-04`
  schema. Required scopes: `read_products`, `read_inventory`.
- The bundled Liquid validator could not run because its plugin lacks
  `@shopify/theme-check-common`. Both minimal snippets were exercised in the
  mocked browser; no claim of Shopify theme-validator approval is made.

References checked: [Ajax product/market pricing](https://shopify.dev/docs/api/ajax/reference/product),
[customer privacy](https://shopify.dev/docs/api/customer-privacy),
[inventory selling policy](https://shopify.dev/docs/api/admin-graphql/2026-04/enums/ProductVariantInventoryPolicy),
[deferred loading](https://shopify.dev/docs/storefronts/themes/best-practices/performance/defer-non-critical-resources).
