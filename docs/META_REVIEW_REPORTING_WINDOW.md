# Live Meta reporting alignment

The previous page set `since=None`; `date_params` translated this to
`date_preset=maximum`. Refresh time was displayed but did not describe that
reporting window. The compact CTR and CPC columns selected all-click `ctr` and
`cpc`. These explain the supplied lifetime-spend and click-definition mismatches.
Campaign totals came directly from Graph, not Supabase. Selected campaign reads
also use a single aggregate Graph report; saved preferences do not replace metrics.

The reporting control now defaults to yesterday through today, inclusive, in
Australia/Sydney (Sports Cave's configured account timezone). Both dates are sent
as `time_range` to campaign and selected-ad Insights, with
`use_unified_attribution_setting=true`. Country context uses the same dates.
Cache and selection identities include the dates. Reporting period and account
currency are displayed separately from the refresh timestamp. No custom attribution
window or action-report-time override is introduced.

Live column mappings:

| Column | Graph source |
| --- | --- |
| Spend | spend |
| Impressions | impressions |
| Link clicks | inline_link_clicks |
| CTR | inline_link_click_ctr |
| CPC | cost_per_inline_link_click |
| ATC | actions: offsite_conversion.fb_pixel_add_to_cart |
| Checkout | actions: offsite_conversion.fb_pixel_initiate_checkout |
| Sales | actions: offsite_conversion.fb_pixel_purchase |
| Purchase value | action_values: offsite_conversion.fb_pixel_purchase |
| ROAS | purchase_roas: omni_purchase, then purchase if absent |
| CPA | cost_per_action_type: offsite_conversion.fb_pixel_purchase; otherwise spend / the same website purchase count |

Website actions are selected once; generic, omni, app and offline action counts
are not added or substituted. The hourly Last Sale context now selects the same
website purchase action. That supplemental recent window remains separate from
the performance table's selected window. Missing link rates remain unavailable.
Purchase ROAS deliberately follows the requested Meta Purchase ROAS column, not
Website Purchase ROAS, and is never synthesized from a different purchase value.

Benchmark formulas/thresholds/weights remain unchanged. Live campaign and ad
benchmark inputs receive selected-window website conversions and direct Graph
link rates. Separate all-click diagnostics retain their original meaning and
benchmark thresholds; Advanced metrics labels explicitly identify all clicks.
Historical helper callers retain their existing normalization contract.

Validation uses mocked Graph fixtures, including the supplied four campaign
spends and 4.34%/$0.59 link metrics. Local Meta configuration reports unavailable,
so no live account response or side-by-side Ads Manager comparison was possible.
Meta's official SDK field schema was inspected:
https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adsinsights.py

For a production comparison, select the same inclusive dates, account, currency,
website conversion columns and attribution settings in Ads Manager. Refresh both
views closely together: reporting updates and attribution/restatements may differ
between read times. No live changes, migration, commit, push or deployment was made.
