# Shopify Singapore edge-protection investigation

Date: 2026-08-19 (Australia/Sydney)

Status: investigation and proposal only. No DNS, nameserver, Shopify, WAF,
firewall, bot, rate-limit, theme, or production-data change was made.

## Production path

Read-only DNS and HTTP checks found:

| Item | Observed value |
| --- | --- |
| Authoritative nameservers | `ns1.nameserver.net.au`, `ns2.nameserver.net.au`, `ns3.nameserver.net.au` |
| DNS infrastructure | Synergy Wholesale / VIPControl nameserver infrastructure; the reseller/account owner is not public DNS data |
| Apex A | `23.227.38.65` (Shopify) |
| Apex AAAA | No record returned |
| `www` CNAME | `shops.myshopify.com` |
| Current `www` CNAME IPv4 | `23.227.38.74` |
| Current `www` CNAME IPv6 | `2620:127:f00f:e::` |
| Apex HTTPS | Shopify-generated `301` to `https://www.sportscaveshop.com/` |
| `www` HTTPS | Shopify storefront `200` |
| Edge headers | `server: cloudflare`, `cf-ray`, `powered-by: Shopify`, Shopify request/session headers |

The request path is:

```text
Visitor
  -> Synergy Wholesale / VIPControl authoritative DNS
  -> apex Shopify A record or www CNAME to shops.myshopify.com
  -> Shopify-managed Cloudflare WAF/CDN
  -> Shopify storefront
```

There is no merchant-controlled Cloudflare zone, reverse proxy, or WAF in the
public request path. The Cloudflare response headers belong to Shopify's edge.
A read-only `HEAD` request to `www` returned Shopify analytics/session cookies,
which demonstrates why a theme or JavaScript block is too late.

The current `robots.txt` is Shopify-generated, permits normal public catalog
crawling, and advertises the canonical sitemap. It is not a security boundary.

## Safe blocking layer

Shopify documents that all Online Store requests pass its Cloudflare WAF, but
does not expose merchant custom country rules. Shopify also explicitly documents
customer-managed Cloudflare and similar proxy configurations as unsupported.
Adding an orange-cloud proxy could interfere with certificates, resilience and
Shopify bot detection, so it is not a production-safe recommendation.

The only presently supported layer capable of rejecting the request before
Shopify storefront rendering/session creation is Shopify's own edge. The first
action is therefore a Shopify Support escalation asking its edge security team
to apply or approve the proposed SG mitigation and confirm analytics ordering.

Shopify Markets is not a substitute. Removing Singapore from active markets
prevents checkout, but Shopify documents that unmatched visitors can still
browse the storefront using the backup-region experience. A theme country-block
app is also not a substitute because the request has already reached Shopify.

## Proposed Shopify-edge rule

Provider-equivalent expression:

```text
(http.host in {"www.sportscaveshop.com" "sportscaveshop.com"}
 and ip.src.country eq "SG"
 and not (
   cf.bot_management.verified_bot
   and cf.verified_bot_category eq "Search Engine Crawler"
 ))
```

Action: provider-native Block with a minimal HTTP 403 response.

The exception depends on provider verification, not the User-Agent. A normal
client sending `User-Agent: Googlebot` remains blocked. Before activation,
Shopify must confirm the verified classification used for Googlebot,
GoogleOther, Bingbot, Storebot-Google and AdsBot-Google so Search, Merchant
Center, Shopping and the Google & YouTube channel are not impaired. Do not add
a broad User-Agent, ASN, or generic `known bot` exception.

The rule must run on both hosts before Shopify's apex-to-www canonical redirect.
It targets the public custom domains only. Shopify Admin API calls use the
store's authenticated `.myshopify.com/admin/api/...` endpoint and are outside
the host condition. Webhook delivery to Sports Cave OS is also outside it.

## Moving-country scraper protection

A second rule is prepared only as a disabled pilot. It proposes a managed
challenge after 120 `GET`/`HEAD` requests to product, collection, or search
routes from one source IP within five minutes, with a ten-minute mitigation
window and a verified search-crawler exception.

This threshold has not been validated against edge logs. Shopify should first
run it in log/simulate mode, inspect human request distributions, and use its
bot score/detection and TLS fingerprint signals where available. It must not be
activated solely from this proposed number, and an ASN must not be blocked
without strong event evidence.

## August attribution limit

The current DNS provider has no HTTP request path and therefore no visitor logs.
The Shopify-managed Cloudflare logs are not merchant-accessible. Shopify's
merchant analytics expose sessions, geography, referrer and human/bot
classification, but not the source IP, ASN, TLS fingerprint or raw edge request
log needed to name a provider or bot family.

The available evidence supports an external automated catalog traversal, but it
does not identify one IP range, ASN, proxy network, provider, or named crawler.
Any more specific attribution would be speculation. Shopify Support must query
its edge logs for 2026-08-18.

## Shopify Support request

Request escalation to the Online Store edge/security team with these questions:

1. For 2026-08-18, provide privacy-safe aggregates for SG requests to both
   custom hosts: source ASN/provider, unique source counts, methods, top paths,
   peak requests/minute, cookie reuse, bot classification and verified bot name.
2. Confirm whether an SG country block can be applied at Shopify's Cloudflare
   edge before storefront rendering and Online Store session creation.
3. Apply the proposed host + SG block with only provider-verified search crawler
   exceptions, or provide Shopify's supported equivalent.
4. Confirm classifications for Googlebot, GoogleOther, Storebot-Google,
   AdsBot-Google and Bingbot, then test them before enforcement.
5. Run the product-enumeration rate rule in log/simulate mode and recommend a
   threshold based on observed legitimate traffic.
6. Expose daily block, verified-crawler bypass, top path, ASN and rate-limit
   aggregates in existing provider analytics where possible.
7. State any Shopify plan requirement, fee, duration or limitation for the
   mitigation.

## Pre-activation test matrix

Use independent AU, US, UK, CA, NZ and SG egress probes. For each test save only
status, headers, response size, country and timestamp; do not retain unnecessary
IP history.

| Test | Required result |
| --- | --- |
| SG `/`, a live `/products/...`, a live `/collections/...` | Edge 403, minimal body, no Shopify HTML/session cookie |
| SG apex | Edge 403 before redirect; no apex bypass |
| AU, US, UK, CA, NZ same URLs | Existing 200/redirect behavior unchanged |
| Verified Googlebot/GoogleOther/Bingbot | Accessible and logged as provider-verified bypass |
| Fake `User-Agent: Googlebot` from SG | Blocked |
| Google Merchant/Storebot/AdsBot | Accessible after verified identity/classification is confirmed |
| Checkout from target markets | Operational |
| Shopify Admin API and Sports Cave OS sync | Operational on authenticated `.myshopify.com` API host |
| Webhooks and Shopify apps/channels | Operational |

After activation, compare Shopify SG sessions with WAF block counts. A genuine
edge block should greatly reduce or eliminate new SG storefront sessions. Do
not use an analytics country filter as the remediation.
