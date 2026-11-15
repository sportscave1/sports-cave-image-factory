# Meta Review live data path

This supersedes the live-screen data flow described in
`META_REVIEW_IMPLEMENTATION.md`. The previous screen loaded Supabase reporting
even when its explicit sync failed, so old Ads Intelligence campaigns appeared
in the primary review interface. The database schema repair did not change that
source-of-truth problem.

## Current flow

Opening/importing Meta Review performs no Meta or database reads. The existing
account configuration is displayed without claiming a verified connection.
Refresh From Meta enables live reads for this Streamlit session. Account or
credential changes reset that opt-in and isolate cached responses.

The existing `meta_ads_client._request` supplies credentials, API version
(default v26.0), safe errors and GET transport. No new token or client is created.

1. `/{configured_account}`: account ID/name/currency/timezone; identity is checked.
2. `/{configured_account}/campaigns`: campaign metadata, status and schedule.
   Date range is sent using `time_range` (or `date_preset=maximum`), and status
   using `effective_status`; completed requests additionally set `is_completed`.
   These parameters are exposed by Meta's official SDK:
   https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/adaccount.py
3. Only after campaign selection: `/{campaign_id}/ads` with nested creatives,
   `/{campaign_id}/adsets` for names/target markets, and
   `/{campaign_id}/insights` with `level=ad`, selected date range and
   `use_unified_attribution_setting=true`.

Campaign search filters the complete returned list locally. Each edge follows
cursors through the original Graph path, never a token-bearing `paging.next`
URL. Bounds are 100 rows/page, 50 pages/edge and a 90-second read deadline plus
at most one in-flight request (existing 30-second timeout). An incomplete,
malformed or conflicting result fails explicitly instead of silently presenting
a partial list. No creatives are fetched for unselected campaigns.

The session cache keeps at most 24 responses, for two minutes each, scoped by
account, token fingerprint, API version, resource, campaign, date range and status
where relevant. Errors have the same cooldown to avoid rerun storms. Refresh
invalidates only this account's live entries, retaining a prior successful
response strictly as a labelled `STALE CACHED META` fallback. A different date
range/account never inherits that fallback. No Supabase history is substituted.

## Metrics and evidence

Insights uses a single range report per ad, retaining range reach/frequency;
unique reach is never summed across ads. Exact reported CTR/CPC/link rates are
preserved for each ad, with count-derived rates where needed. Absent actions and
ROAS remain unavailable (`—`); explicit zeros remain zero. Ecommerce actions use
one canonical alias (purchase/add_to_cart/initiate_checkout first, then pixel,
onsite-web and omni fallbacks); aliases are never added together.

Creative extraction retains original link_data message/name/CTA/link, image URL
and hash, with thumbnail and asset_feed_spec fallbacks. Dynamic/carousel assets
remain separate candidates; ad-level performance does not establish a served
component winner.

The existing commercial winner/confidence gate is preserved. Below that gate,
the board separately identifies lower-funnel signals (purchase, ROAS, CPA,
checkout, ATC) and click signals. The IA-style regression gives IA1 the stronger
commercial-intent signal and IA3 the stronger click signal, with low confidence
and no automatic overall winner.

## Persistence boundary and release

Optional Supabase reads load only saved decisions/handoffs and product mappings.
Storage failure warns without blocking live review. Saving selections and the
existing image-archive/handoff workflow still require durable storage; failure
does not navigate with an unsaved reference. Creative Refresh, its generator,
POST NOW and Posting implementation are unchanged. Existing reporting tables,
snapshot sync helpers and migrations remain intact for historical use.

No migration is required. This change is local only pending review; no deploy,
push, production sync, Meta mutation or new credential is part of this change.
Live API responses were exercised using fixtures, including the user's IA-style
values, rather than requesting or modifying production advertising.
