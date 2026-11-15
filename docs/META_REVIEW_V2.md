# Meta Review V2 decision support

Performance comes only from live Graph range reports. Supabase remains optional
for saved selections and product mapping; those two keys are explicitly allowlisted.
Its historical performance cannot replace Graph metrics or benchmark results.
Creative Refresh, Posting, authentication, status filters and winner controls are unchanged.

## Live queries

The existing account campaigns and selected-campaign ads/adsets reads remain.
Account Insights uses `level=campaign`; selected campaign Insights uses `level=ad`.
Both keep unified attribution and the selected available-history period. Existing
cursor pagination, limits, error handling and 120-second session cache remain.
Each aggregate read now has a separate `breakdowns=country` request containing
only the entity ID and spend in `fields`; country is returned by the breakdown,
never requested as a field. Country rows never replace aggregate metrics.
Unsupported country/breakdown combinations (Meta code 100) are logged and yield
UNKNOWN market without blocking primary reporting. Any partially read country
pages are discarded. Primary failures, authentication, permissions and unrelated
API errors remain visible.

Aggregate fields: date_start, date_stop, campaign_id/name, adset_id/name, ad_id/name,
spend, impressions, reach, frequency, clicks, ctr, cpc, cpm, inline_link_clicks,
inline_link_click_ctr, cost_per_inline_link_click, outbound_clicks,
outbound_clicks_ctr, cost_per_outbound_click, actions, action_values,
cost_per_action_type, purchase_roas, website_purchase_roas. Campaign requests omit
ad/adset identifiers. The configured API version and account are unchanged.

The additional outbound field and country breakdown are listed in Meta's official
[SDK schema](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py).

## Evidence and precision

`meta_review_benchmarks.graph_metrics` picks exactly purchase, add_to_cart,
initiate_checkout and landing_page_view; aliases never fall back or sum.
Omitted actions are zero only when a performance row exists. No report stays
unavailable. Missing purchase value with purchases remains unavailable. ROAS uses
Graph purchase_roas omni_purchase, falling back to purchase, without deriving ROAS
from revenue. Raw reported rates/costs are retained; funnel ratios use unrounded
counts. Zero denominators produce unavailable costs/rates, never infinity.

IE identification uses a Facebook canvas/Instant Experience destination or explicit
canvas/Instant Experience ID. Carousel identification uses multiple child attachments
or asset_feed_spec CAROUSEL format. IE takes precedence over an embedded carousel.
Names are never evidence. Everything else is UNKNOWN.

Exactly one country with positive delivery spend supplies the market. Any positive
spend in multiple countries is MIXED (deliberately conservative); no country is
UNKNOWN. AU/US locked costs require AUD account currency. GB and MIXED costs stay
neutral. Campaign format is UNKNOWN until lazy child inspection establishes a
single known format; that evidence enriches only the brief live overview cache.
Mixed/unknown campaigns still have Graph metrics and sale-based decision support.

## Scores and recommendations

All supplied constants live in `meta_review_benchmarks.py`. Higher-is-better red
scores interpolate 1–3, amber 4–6, green 7–9 (9 at twice the green entry).
Lower-is-better scores run 9–7 below the green maximum, 6–4 across amber,
and 3–1 above the amber maximum (1 at twice that maximum). Scores are bounded.
Unrounded values between the printed hundredths remain amber until green entry.

No-sale diagnostics use the supplied relative weights, renormalized across only
valid benchmarked metrics. Learning zero downstream rates are neutral. Mature
zero ATCs AND zero checkouts cap an available diagnostic score at 3.9, making the
specified low-intent-traffic example actionable rather than allowing cheap clicks
to dominate. No denominators or infinite costs are invented for that cap.

For sale-producing rows, the score equally weights available purchase CVR, ROAS,
checkout-to-purchase and eligible CPA benchmarks. This is an explicit composition
choice because purchase-score weights were not specified; top-funnel diagnostics
have no weight in that sales score. Recommendations follow the supplied maturity
gates and sale-first rules. Missing ROAS with sales results in WATCH, not a fabricated
profitability verdict. A high-intent mature no-sale funnel recommends checking the
store/checkout before blaming the creative. Recommendations never mutate Meta.

Display-only: Carousel link/outbound CTR; AU IE cost/ATC; US Carousel cost/ATC and
cost/checkout; GB monetary costs; all unsupported markets/currencies; CPM, frequency,
reach and impressions. AU Carousel cost/ATC has its locked cell colour but zero
overall weight, as requested. UNKNOWN format has no format-specific score.

## Presentation and testing

The existing compact tables gain funnel metrics, Format, Market, Score and
Recommendation. Semantic colour is cell-level, not row-level. Formula header help,
a small legend, and Oldest/Lowest Score/Highest Score/Highest Spend sorts are added.
Ad details show independent recommendations. The existing winner selection and
handoff paths remain separate decision controls and are not automatically changed.

Local tests cover canonical extraction, precise formulas, every rate/cost boundary,
neutral exclusions, market/format detection, maturity boundaries, recommendations,
independent campaign/ad scores, styling, sort order, preference isolation, live
pagination/cache, and existing Creative Refresh/Posting handoffs. No migration or
production operation is needed. Live endpoint validation remains a manual local
read-only test using the configured account; automated validation uses fixtures.
