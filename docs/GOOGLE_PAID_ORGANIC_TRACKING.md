# Google paid and organic attribution

The shared Shopify Merchant feed link contains `google / product_sync / sag_organic` and is eligible for both free listings and Shopping ads. Those defaults alone cannot identify paid versus unpaid traffic.

Paid final URL suffix policy is defined in `google_tracking_contract.py`. Keep auto-tagging on. The account fallback uses campaign ID; PM021126 retains its readable campaign name. A paid-only `utm_term=sc_google_paid_{campaignid}` is carried in a standard Shopify journey field, with `sc_channel=google_paid` and network for URL diagnostics. The term is reserved for paid ad destinations; do not copy it into free listings, internal links, email or SEO links. Campaign/ad/asset suffix overrides must be checked when launching or editing campaigns. Do not replace the native Google & YouTube pixel or add duplicate purchase tags.

The order ledger prefers recorded Shopify visit evidence. A dedicated valid paid marker can resolve shared feed defaults even when the landing query contains both feed and paid UTM values. Explicit organic, other-channel or contradictory marker evidence stays unresolved. Missing click IDs never prove organic.

Only feed-only Shopify ambiguity can use a consistent Google paid or Google organic session on an exact GA4 purchase transaction ID. Contradictory, missing, referral-only or non-Google observations do not qualify. Explicit Shopify organic visits are not rewritten merely because GA4 attributes a session to paid. Raw Shopify, GA4 session and Ads platform counts remain separately labelled. No historical provider events are edited and no synthetic conversions are uploaded. Organic may include free Shopping listings; it does not by itself prove a classic search-result SEO click.

The Ads API reports allowlisted tracking-health checks for account auto-tagging and the effective PM021126 campaign/account suffix. Home warns on drift; Google Ads > Tracking shows the checks. This is scoped configuration evidence, not a guarantee of ad/asset overrides or future event delivery. Reports cache for up to 15 minutes. Refresh after settings edits. No credentials, raw suffix URLs, transaction IDs or customer journeys are added to saved Home snapshots.

## Native audit, 21 November 2026

- Ads account 6581121605: auto-tagging enabled. PM021126 is the delivering campaign, A$20/day. Paid marker saved at campaign level and account fallback.
- Merchant Center 705475729: active AU Shopify API source uses the same feed landing link for free listings and Shopping ads. Feed URLs were not relabelled as paid.
- Shopify Google & YouTube: linked to Ads 6581121605, Merchant 705475729 and GA4 G-J89Q2E80VQ / property 355333982; conversion measurement and enhanced conversions were already on. Checkout completed maps to Google Shopping App Purchase.
- Existing Google tag reports active data and excellent container quality. Cross-domain linking published as version 2, limited to Sports Cave domains (sportscaveshop.com and sportscave.com.au including subdomains; exact sportscave-nb.myshopify.com). Existing tags and consent settings retained.
- A malformed campaign-level final URL suffix in the paused 280936 NRL DEM GEN campaign contained a pasted chat URL. Replaced with the paid suffix policy; campaign remains paused.
- Public HTTP URL checks returned 200 and retained paid markers through the old-domain redirect. These checks do not generate purchase events or verify a real ad click.

## Verification after a real purchase

Use the consented real landing URL, paid marker/click ID, Shopify journey and exact GA4 transaction ID. Check the same date window and timezone. Compare Ads attributed conversions separately: ad interaction dates, attribution windows, cross-device/modelled credit and reporting delays can differ from order-date totals. Never force totals to agree or classify missing evidence as SEO. Consent refusals, blockers and cross-device gaps can still leave orders unresolved.
