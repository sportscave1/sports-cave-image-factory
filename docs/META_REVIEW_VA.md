# VA Meta Review

Default campaigns: Campaign, Status, Spend, Sales, ROAS, CPA, CTR, ATC, Checkout,
Last Sale, Action. Sort options: Newest, ROAS, Sales. Sales uses the existing
purchase sort. The benchmark engine and full Graph metrics are retained internally.
Only ROAS/CPA where benchmarked, Last Sale and Action receive semantic colours.

The popup summary contains Spend, Sales, ROAS, CPA, Last Sale and Action. Its
creative table contains thumbnail, ad, Sales, ROAS, CPA, CTR, ATC, Checkout,
Last Sale and Action. Selecting one row also selects that complete-ad winner.
Full creative details show original image/copy/CTA/destination and identities,
without another primary-metrics table. Collapsed Advanced metrics contains only
metrics absent from the default comparison. Best Components and legacy saved
selection controls remain under collapsed Advanced winner options.

## Supplemental Last Sale

`meta_review_recency.load` uses the existing GET-only Reader on the account or
selected campaign Insights edge. Parameters: level=campaign/ad,
fields=campaign_id/ad_id,date_start,date_stop,actions;
breakdowns=hourly_stats_aggregated_by_advertiser_time_zone; time_increment=1;
action_report_time=conversion; use_unified_attribution_setting=true. Date range
starts three account-local calendar days ago and includes today. The account
timezone is used (Sports Cave: Australia/Sydney). The breakdown name is never a field.

Only canonical `purchase` actions identify a purchase bucket. Aliases never sum
or move the latest bucket forward. This is Meta-attributed conversion-hour
evidence, not an exact Shopify order timestamp. Display uses approximate hour
ranges. A bucket straddling 24 or 48 hours is neutral until it can be classified
without inventing a precise timestamp. Malformed, ambiguous DST, future-hour,
unsupported, failed or stale evidence is unavailable. No primary query or primary
metric is modified. Pagination must complete; partial evidence is never used.

For ACTIVE rows: <24 hours is green; 24–48 hours is amber/CONSIDER unless an
existing rule is stricter; >48 hours is red/STOP CAMPAIGN. Recent sale signals do
not turn poor performance into a winner. No-sale rows require zero canonical
purchases plus a timezone-aware start_time to show age-based Learning/Consider/
Stop. Created time is not substituted for activation. Start time is campaign age,
not proof of uninterrupted delivery since then. Without a known start time,
no-sale age is unavailable. Existing sale-producing objects with a complete recent
window but no recent purchases display >48h, not a fabricated old timestamp.
PAUSED/ARCHIVED actions remain PAUSED/ARCHIVED. Every action is advice only.

The supplemental reads use the existing brief cache, separate from primary
reporting; Refresh From Meta invalidates both. Child reads happen only inside
the selected campaign popup. A Last Sale failure never makes primary reporting
unavailable. No new attribution system or Shopify fallback was added.

Hourly enumeration exists in Meta's official SDK and official example collection:
[SDK](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py),
[Meta example](https://www.postman.com/meta/facebook-marketing-api/request/hysc4bm/reportidbreakdowngenerate).
The exact live purchase/breakdown combination was NOT verified in this checkout:
the existing configuration reports configured=False. Automated validation uses
fixtures. Unsupported combinations degrade to Last Sale: Unavailable.

## Apply to Creative Refresh

Automatic Best Ad uses the existing winner algorithm. Insufficient data disables
Apply until a VA explicitly chooses an ad. Complete-ad references use image,
primary text and headline from that same ad. Multi-asset ads require an explicit
reference choice when a single asset cannot be established.

APPLY TO CREATIVE REFRESH calls the existing archive_image → save_media →
save_selection path. An opaque random 128-bit handoff token is stored in the
existing ads_action_log JSON context; no schema change is needed. Only after
successful archive and package persistence does OPEN CREATIVE REFRESH appear.
The Streamlit link button opens a new tab, preserving the source tab. A changed
winner/reference cannot reuse the previous winner's displayed link.

The URL contains page=creative_refresh and handoff_id only. The existing authenticated
Creative Refresh render hook loads the handoff by token, action type and configured
account, then calls existing hydrate. This survives fresh Streamlit session state.
The package carries campaign/ad/creative IDs/names, image digest, exact primary
text/headline, description, CTA, destination, format, market, performance and
recommendation context. The permanent image appears through the existing source
panel; the prompt workflow's manual attachment behavior is unchanged. No browser
file input is artificially populated.

Creative Refresh prompts, generation/refinement, siblings, POST NOW and Posting
are untouched. Only its existing Meta Review source hook gains URL-based loading.

## Validation

227 Python tests passed across Meta Review, recency, simplified UI, benchmark
engine, image handoff, Creative Refresh, winner refinement and Posting handoffs.
Isolated PGlite tests verify actual save/lookup SQL, account isolation and durable
image/copy references after restart, plus the existing persistence regressions.
No production writes, Meta mutations, push or deployment were performed.
