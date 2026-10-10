# Design Studio V3 — Sales & Design Intelligence

Implemented locally on 10 October 2026 (Australia/Sydney). No commit, push, merge,
deployment, production synchronization or production data mutation was performed.

## Release outcome and boundaries

This safe first version connects **Design Studio Research** and **Design Schedule
Generate Ideas** to one read-only preflight over existing synchronized operational
tables. Both receive the same reporting window, source-quality rules, product
matching, aggregate calculations, cache and product-linked artwork inspection brief.
The release is deliberately honest about incomplete operational data.

**Verified:** local fixtures, actual SQL in an isolated local PostgreSQL instance,
creative/CSV regressions, desktop/mobile Chrome and Edge interactions, and an
isolated release assembled without unrelated working-tree changes.

**Not verified:** live Sports Cave sales totals, complete historical ingestion,
live source freshness, product-to-ad mapping coverage, live GA4 quality or actual
winning artwork pixels. No fixture result below describes real commercial results.

**Visual capability:** the app prepares product-ID-bound image references and a
structured Winning Design DNA inspection brief. Its existing workflow creates
prompts for a downstream chat; it has no vision-model execution service. Actual
pixel inspection occurs in that chat if it can access the image. The app itself
does not claim automatic visual analysis, invent findings or classify an image as
original artwork from its title/URL. Every initial DNA record explicitly says
`pixels_inspected=false`, has empty observations, and warns about lifestyle mockups.

## 1. Architecture audit and preservation

- `design_studio_page.py::render_design_studio_v2` renders the schedule, style
  selection, task details and five prompt cards. It does not execute an LLM.
- `design_studio_styles.py::build_prompt_bundle` constructs separate Research,
  Find Images, generation, signature-placement and harsh-review prompts.
- All nine registered styles remain: Ultimate Moment, Rivalry Face-Off,
  Legends Jersey Display, Nostalgic Tribute, Motorsport Driver + Car,
  Minimalist Hero, Championship Achievement, Vintage Restoration and Update Existing.
- Research contracts retain the athlete/moment hierarchy, subject locks, real-photo
  requirements, collector narrative, signatures, branding and composition rules.
- `prompt_store.py`, saved Supabase overrides, `design_studio_prompts/`, the style
  registry and original prompt constants were not edited. Legacy prompt-editor
  and upgrade/regeneration code is unchanged. V2's original builder does not itself
  resolve legacy editable overrides; this release does not change that behavior.
- `design_schedule.py` owns idea controls; `sports_cave_dashboard.py` owns the pure
  brief builder, style weights, exact CSV schema and import validation.
- Design Tracking's existing read helper can discover/create rows. The new adapter
  deliberately uses SELECT projections instead of calling that helper.
- Existing Meta and GA4 integrations save operational reporting tables. The new
  layer reads those records; it never triggers a sync, token refresh or external API.

## 2. Changed files

Production additions:

- `design_studio_intelligence_store.py`: bounded read-only SQL projections.
- `design_studio_sales_intelligence.py`: aggregation, scoped evidence, cache,
  artwork inspection records, prompt preflight and conservative style suggestions.
- `design_studio_intelligence_ui.py`: compact collapsible status and preparation.

Production edits:

- `design_studio_page.py`: wraps the Research card after the original bundle is built.
- `design_schedule.py`: prepares evidence for briefs and explicit Suggest Best Mix;
  clears a prepared brief when its sport, count, mix or options change.
- `sports_cave_dashboard.py`: accepts an optional aggregate snapshot in the pure
  idea prompt builder. Existing CSV columns and style identifiers are untouched.

Verification/release additions:

- `tests/test_design_studio_sales_intelligence.py`
- `tests/test_design_intelligence_postgres.py`
- `tests/fixtures/design_v3_preview.py`
- `tests/check_design_v3_ui.py`
- `scripts/test_design_v3.py`
- `scripts/benchmark_design_v3.py`
- `scripts/deploy_design_studio_v3.ps1`
- This report and `docs/design-studio-v3-release/{changes.patch,manifest.json}`.

The release patch contains only this task's hunks. In particular, it excludes the
pre-existing shared-table styling edits in `design_schedule.py` and all other
concurrent work. Temporary databases, screenshots and logs are not release assets.

## 3. Sources, accounting and coverage

The adapter reuses `supabase_backend.connect()` and existing tables:

| Source | Tables | Treatment |
|---|---|---|
| Shopify catalog | `shopify_products` | Exact product IDs, handles, public image references, tags/collections, status, known publication date |
| Shopify sales | `shopify_orders`, `shopify_order_lines` | Completed/partially or fully refunded order cohorts; excludes tests, unknown test status, cancellations, unpaid, invalid and duplicate lines |
| Meta | `meta_ad_insights_daily`, `ads_product_mapping`, `meta_ad_accounts` | Explicit handle mapping; non-breakdown rows only; grouped separately by currency |
| GA4 | `seo_ga4_daily_landing_pages`, `seo_google_connections` | Current selected property; complete saved landing-page rows; exact product path match |
| Design Tracking | `edition_products`, `edition_design_tracking` | Creation date, active/sold-out state, edition total; no discovery, changes or allocation |

The reporting interval is the previous **calendar 12 months**, ending before the
current incomplete Sydney day. On the implementation date it is 10 October 2025
inclusive to 10 October 2026 exclusive. Leap-day handling is tested. Meta/GA4 dates
retain their source reporting-day semantics; cross-system timezone alignment is
not assumed exact.

Gross units and distinct order counts are separate. Gross merchandise sales are
price × original quantity. Discounts use line allocations where present, otherwise
the recorded line discount. Item refund subtotals reduce merchandise revenue;
returned quantities reduce net units. Tax/shipping are not included. Refunds are
attached to the original order cohort using latest stored state, not refund-date
accounting. Cancelled orders are excluded entirely. Unallocated adjustments suppress
financial conclusions rather than being spread arbitrarily across products.

Unknown prices, discounts or refunds yield null financial measures and no financial
ranking. The existing GraphQL order sync does not request line prices/refunds, while
webhook records may retain them in `raw_payload`. The new layer uses those retained
fields when present; it does not expand Shopify scopes or alter the sync.

Publication is used only when known and consistent with observed sales. Otherwise,
velocity uses **first observed sale**, explicitly labelled as an incomplete selling-
time proxy. Publication is not inferred from product creation or Design Tracking.
Stockout history is unavailable. First-sale dates refer to the window, not lifetime.

Results retain product/market/currency cohorts. Raw units, revenue by currency,
velocity and recent 30-day rankings remain separate; there is no invented overall
score. Monthly units, purchase-day frequency, peak-month share, variant quantities,
recent/prior 30-day units and small-sample warnings support human comparison.
Market cohorts are not silently summed into an all-market product rank.

No source certifies complete 12-month ingestion, so a populated snapshot is labelled
**Partial data**. Empty/unavailable snapshots say **Analytics unavailable**. Source
timestamps are distinct from preparation time; stale/unknown stored sales are
explicitly flagged. Oversized or unavailable sources do not produce truncated rankings.

## 4. Meta, GA4 and commercial reasoning

Meta evidence includes mapped spend, impressions, clicks, derived CTR/CPC, ATC,
checkouts, attributed purchases/value, CPA and reported ROAS. It is labelled as
advertising evidence across markets, never verified Shopify revenue. No Meta/GA4
revenue is added to Shopify revenue. A missing ad mapping does not prove organic sales.
Current mapping history and creative-level winners are not certified by this adapter.

GA4 provides saved landing-session breakdowns by country, device and channel,
engagement, attributed transactions and threshold flags. These records may cover
organic traffic only. They are not product-view denominators: no product conversion,
add-to-cart rate or checkout rate is fabricated. Missing matches are explicitly reported.

The prompt requires sourced facts, plausible interpretations and unverified
hypotheses to stay distinct. Athlete popularity, pricing, availability, events,
gifting periods, advertising and organic discovery remain possible confounders.
It asks the downstream research to compare original opportunities and justified
experiments, rather than simply reproduce the biggest seller.

## 5. Winning Design DNA and originality

Each relevant product has an exact Shopify ID, image reference and up to three
additional public Shopify CDN candidates. URLs with credentials or non-approved
hosts are not forwarded. Query strings are stripped. The record never associates
artwork by fuzzy title matching.

Downstream instructions require actual pixel inspection, artwork-versus-mockup
classification and observable findings for subject, hero placement, supporting
photography, typography, colour, era, signature/plaque treatment and thumbnail
readability. Emotional interpretation remains a hypothesis. If image access fails,
the downstream model must preserve the explicit uninspected status.

The bounded existing-product inventory accompanies the evidence. Original duplicate-
prevention rules stay in place, including same-athlete/same-story and renamed concepts.
Catalog truncation is flagged; a truncated inventory cannot prove an empty collection
gap. This is prompt-level prevention, consistent with the existing workflow; there is
no autonomous generated-CSV verifier or guarantee about an external model's output.

## 6. Research and Generate Ideas integration

The existing page had prompt cards rather than a model-running Research button.
**Prepare Research** now retrieves the cached preflight and adds it before the intact
Research prompt. Opening the page builds the original usable prompt plus an honest
not-prepared notice without reading analytics. Authorized prompt editors can refresh
the shared snapshot from the collapsed summary. Refresh changes only intelligence
state, not tasks, selected subjects, moment locks, photographs or saved details.

Find Images does not rerun the preflight. Its existing preceding-Research authority
remains intact. The commercial instructions say to carry only approved creative
conclusions into generation/review. All downstream prompt strings are unchanged.

**Prepare Design Brief** retrieves the same snapshot automatically. Its pure builder
still performs no database/API calls. Commercial reasoning is assigned to existing
`notes`, `priority` and `design_description`; exact row count, sport, style mix,
maximum two principal people and CSV header/order remain unchanged.

Only **Suggest Best Mix** may change a manual allocation. It retains the original
sport-based defaults unless at least two styles each have two mapped products,
20 orders and adequate selling time. A qualifying suggestion is limited to one slot,
preserves total count and keeps unsupported/unselected styles at zero. It explicitly
states that exposure is not controlled. The current catalog adapter does **not**
invent style labels from product titles, so live suggestions normally retain the
sport-based mix until a reliable product-to-style mapping becomes available. The
evidence path and exact-total behavior are fixture-tested, not claimed live-verified.

## 7. Fixture examples — not live sales or model-generated recommendations

Baseball fixture: “The Baseball Memory” records 8 gross units in 2 orders, one
returned unit, AUD 800 gross merchandise sales, AUD 20 discounts and AUD 90 item
refunds: **7 net units and AUD 690 net merchandise revenue**. Meta separately reports
AUD 400 spend and AUD 600 attributed value. That attributed value is not added to 690.
“Baseball Newcomer” sells 3 units over 9 observed days: 10 gross units per 30 observed
days. It leads velocity but not raw units, and carries a small-sample warning.

A supported Baseball opportunity brief would compare these products' actual images
if accessible, state that composition is not yet inspected, investigate timing and
exposure, exclude near-duplicate stories, and preserve the requested style counts.
It cannot conclude that nostalgic composition caused these fixture purchases.

NFL fixture: “The Catch” has 2 gross/net units in one order and AUD 190 net merchandise
revenue. Meta and GA4 matching evidence is unavailable. A Joe Montana/The Catch
Research task remains locked to that subject/event; unrelated baseball performance
is not inserted as proof of NFL demand. The full Ultimate Moment contract follows.

No-history Golf gets no invented bestsellers. A no-history motorsport discipline may
use explicitly labelled comparable motorsport catalog evidence; NBA is not substituted.

## 8. Performance and verification

No analytics I/O occurs on page opening. Preparation reads bounded synchronized
records only: at most 5,000 products, 50,000 lines, 5,000 Meta groups, 10,000 GA4 groups
and 5,000 tracking rows. Exceeding a bound makes that source unavailable. SQL has a
four-second statement timeout; the existing connection has an eight-second timeout.
Optional source failures are isolated by savepoints in a READ ONLY transaction.

The server cache retains aggregates only for 30 minutes, with at most four reporting-
window/loader entries. Sport, market and product scope are applied to cached
aggregates. Returned snapshots include a revision hash and source timestamps.
Refresh bypasses cache; a failed refresh never labels the prior snapshot as current.
No full order datasets or customer histories enter session state or generated prompts.

Local fixture benchmark (not a production latency promise):

| Check | Result |
|---|---|
| Aggregate 20,000 lines, 5 samples | median 392.445 ms; max 434.852 ms |
| Cached scoped read, 50 samples | median 0.070 ms; max 0.123 ms |
| 51 reads over one reporting window | one source load |
| Benchmark commercial context | 6,061 characters |

Validation results:

- **216 applicable Python regressions passed** on an isolated archive of local HEAD
  `b526c1d0dc3735599ee0b3ad6410f4f1ba1017e8` plus only this upgrade.
- **One real PostgreSQL integration test passed** against a disposable local cluster:
  all five projections execute; item refunds match; optional sources join; customer
  fields stay excluded; a write is rejected by the read-only transaction.
- **Chrome and Edge passed at 1440px and 390px** using real production controls and
  fixture-backed sources. No page analytics read, preparation, refresh, moment
  preservation, manual-mix preservation, Baseball evidence, stale-brief clearing,
  outage fallback and horizontal-overflow checks passed; no JS page errors.
- **Render topology validator passed.** `render.yaml` is unchanged; no Blueprint sync
  is performed or required by this code-only release.
- In the mixed working tree, an older test expects literal `row_height=34`; the
  pre-task baseline already uses `TABLE_ROW_HEIGHT`. That unrelated change is preserved
  locally and excluded from this release. The isolated release passes that test too.
- Initial combined test execution encountered sandbox temporary-directory problems
  and shared Streamlit test context contamination. Final suites run in separate
  processes with a writable local temp directory; these errors did not recur.

Reproduce unit/creative/CSV tests with `python scripts/test_design_v3.py`; benchmark
with `python scripts/benchmark_design_v3.py`. The optional PostgreSQL test requires
`DESIGN_V3_TEST_DATABASE_URL` pointing at a disposable loopback database. The browser
fixture is `tests/fixtures/design_v3_preview.py`; the browser runner reads
`DESIGN_V3_FIXTURE_URL` (default `http://127.0.0.1:8904`). All browser external requests
are blocked. No live sales or customer access is required by these tests.

## 9. Privacy, limitations and deployment readiness

The implementation contains no Shopify, Meta or GA4 API writes, schema additions,
product/price changes, publication, allocation, certificate edits, email sending,
prompt-store changes or Design Tracking writes. SQL uses explicit projections and
never retrieves customer names, addresses, emails or raw order JSON. Editable
tracking `first_order` text and creator names are excluded. Individual order IDs
exist only transiently for counting/deduplication and do not enter snapshots.
Database exception text is not exposed to users or prompts. Public product metadata
is treated as untrusted data, not instructions.

Remaining improvements depend on real source coverage and additional integration work:

1. Certify full historical synchronization and consistently retain prices, discount
   allocations, refunds and product publication dates. Existing operational records
   cannot support complete financial reporting when those fields were never saved.
2. Establish verified product-to-design-style and original-artwork asset mappings.
   No new schema or fuzzy association is introduced by this release.
3. Add an explicitly integrated pixel-analysis service if automatic in-app visual
   findings are required. Today the existing downstream chat performs inspection.
4. Add product-level GA4 ecommerce denominators and coverage/freshness certification;
   reconcile advertising mappings and market/timezone coverage before stronger
   exposure-adjusted or organic-success claims.
5. Repeat-purchase analysis, historical stockouts and causal conclusions are not
   implemented. No customer-level dataset is collected to approximate them.

The code and fixtures are locally verified. Live commercial accuracy is not certified.
The release command below verifies hashes, clones GitHub `main` into an isolated
directory, applies only this task's patch/assets, reruns the release regressions and
topology validation, commits and performs a normal fast-forward push. It stops on
conflicts, changed assets, failed checks or a concurrent remote update. It does not
stash, reset, stage or overwrite the original working tree or index. Existing Render
auto-deployment from `main` then handles the canonical `sports-cave-os` service
(`srv-d8kl4on7f7vs73dvavv0`). No primary service is created, renamed or replaced.

## One manual VS Code PowerShell deployment command

Run this single command in VS Code when ready. It has **not** been executed here.

```powershell
& { Set-Location -LiteralPath 'C:\Users\hello\Documents\sports-cave-image-factory'; & '.\scripts\deploy_design_studio_v3.ps1' }
```
