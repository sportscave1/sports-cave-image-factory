# Shopify storefront request investigation

Investigation date: 2026-08-19 (Australia/Sydney)

## Outcome

The former Technical SEO implementation was an unsafe stateless crawler, but the repository and Render evidence available for 18 August does **not** show that production executed it. The production worker and cron commands invoke `run_daily_analytics_refresh()`, whose stage list contains API imports and saved-data refreshes only. The only application caller of `run_background_audit()` was `run_daily_growth_pipeline()`, and no configured production command called that function after the audit was introduced.

Therefore:

- the crawler defect is real and is fixed by this change;
- the defect alone is not proof that Sports Cave OS caused the 7,401-session spike;
- approximately 50 maximum-sized old audits would be needed to emit about 7,401 stateless application-level storefront requests;
- the checked Render services are in Oregon, not Singapore, so Render configuration does not explain the Singapore concentration;
- identifying the actual spike actor requires Shopify-side request/session evidence (timestamp, user-agent and source IP/ASN). The old audit did not log runs or request totals, and local database credentials were unavailable for a read-only historical-run query.

## Production timeline and execution trace

- Commit `be7e25b` (`Rebuild Analytics SEO and automated Blog workspaces`) introduced `seo_technical_audit.py` and the `technical_audit` growth stage on 2026-08-17 19:06 AEST. It deployed shortly afterward, one day before the reported spike.
- The canonical Render service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`), worker `sports-cave-seo-worker` (`srv-d9ujm9navr4c73amurgg`) and cron `sports-cave-seo-daily-sync` (`crn-d9ujqvvqj5pc73fpe0ag`) are all configured in Oregon.
- Worker command: `python google_seo_import.py worker --poll-seconds 15`.
- Cron command: `python google_seo_import.py daily`, schedule `30 18 * * *` UTC.
- Both commands resolve to `seo_growth_intelligence.run_daily_analytics_refresh()`, not `run_daily_growth_pipeline()`.
- Analytics Refresh, GSC, GA4, Shopify Admin sync and saved reporting stages do not call the public storefront.
- The SEO UI rendered saved technical findings. Its recheck action queued a database row; it did not fetch a URL.
- The UI “Run daily pipeline now” action only queued a growth row. The former mode-agnostic worker claim could claim that row, but the worker still executed the Analytics-only callbacks.
- Render log searches found the worker and cron commands but no Technical Audit marker. The former audit emitted no run log, so this is supporting evidence rather than proof of non-execution.
- A suspended duplicate web service existed briefly on 18 August, also in Oregon. Its command was `python sports_cave_server.py`; it did not add a Technical Audit execution path.

## Old audit request count

For one old default run:

| Request class | Limit | HTTP behavior |
| --- | ---: | --- |
| Top-level pages from `priority_urls()` | 100 | One bare `requests.get()` per page, redirects followed, full HTML downloaded |
| Unique internal link status checks | 50 | One bare `requests.get()` per checked link, redirects followed, full response downloaded |
| GSC sitemap list | 1 | Google API GET; not a storefront request |
| GSC URL Inspection | 20 | Google API POST; not a storefront request |

The old storefront total was therefore up to **150 application-issued GET calls per audit**, plus one additional on-wire HTTP transaction for every redirect hop. Requests' default redirect ceiling could make an abnormal redirect chain larger, but ordinary canonical 200 responses would remain close to 150. There was no explicit retry loop around storefront calls.

Each call used the module-level `requests.get`, which creates and closes an independent `requests.Session` for that call. Shopify cookies were not retained between pages. That makes each request stateless and eligible to be treated as a new visitor/session. Shopify's proprietary attribution cannot be verified from this repository, so “one request equals one Shopify session” should be treated as a plausible mechanism, not a proven equality.

The internal-link cache avoided repeat checks of the exact string within one run, but it did not normalize URL variants, did not share status with top-level page fetches, and did not persist between runs. Link discovery was bounded and not recursive: checked pages did not add more pages to the crawl queue.

## Complete outbound request map

### Components that can intentionally request public storefront HTML

| File / function | Trigger and frequency | Requests per run | Redirects / body | Session, user-agent, recursion, retries |
| --- | --- | ---: | --- | --- |
| `seo_technical_audit.py` — former `run_background_audit()` and `broken_internal_link_findings()` | Only when `run_daily_growth_pipeline()` was directly invoked; no configured production caller found | Up to 100 page GETs + 50 link GETs | Redirects followed; full body for both page and link checks | New implicit session per call; Requests default UA; no recursive queue; no storefront retry loop |
| `seo_technical_audit.py` — controlled `run_background_audit()` | Explicit `python seo_technical_audit.py daily` maintenance command, or explicit caller; `full` mode is separate | Daily: 20 eligible pages + 20 link targets, hard ceiling 60 on-wire requests. Full: 500 pages + 20 links, hard ceiling 1,200 | Manual maximum 5 redirects; full HTML only for page audits; HEAD-first streaming status checks with GET fallback | One persistent session and cookies; `SportsCaveOSTechnicalSEOAudit/1.0`; normalized per-run page/status caches; no recursive queue; at most 2 attempts and always within hard request ceiling |

### Other server-side network paths reviewed

| File / function | Destination and trigger | Can create Shopify storefront sessions? |
| --- | --- | --- |
| `google_seo_phase4.ShopifySEOClient` → `shopify_sync.graphql_request()` | Shopify Admin GraphQL `https://{shop}.myshopify.com/admin/api/{version}/graphql.json`; page/product/order jobs | No public page GET. POSTs use the authenticated Admin API. Pagination can create multiple API POSTs, but not storefront sessions. |
| `shopify_sync.get_shopify_access_token_details()` | Shopify Admin OAuth token endpoint | No public page GET. One token POST when a cached/static token is unavailable. |
| `google_seo.py`, `google_seo_import.GoogleSEOReportingClient` | Google OAuth, Search Console/Webmasters APIs and GA4 Data API; Analytics refresh and daily worker | No. GSC retries transient failures up to two times, but only against Google APIs. The sitemap function lists submitted sitemaps through GSC; it does not download a live sitemap. URL Inspection is a Google API POST. |
| `app.request_edition_log_endpoint()` / `request_google_sheet_csv_export()` | Configured Apps Script JSON endpoint and Google Sheets CSV; Streamlit cache TTL 60 seconds | Expected destinations are Google. It can technically request any misconfigured `EDITION_LOG_JSON_URL`: one full GET, an optional Apps Script-format retry, then optional Sheets fallback. Bare Requests client, Image Factory UA, redirects followed, no recursive crawl. No evidence tied this setting to the storefront. |
| `collector_vault.lookup_judgeme_product()` | Judge.me API, user review prompt/submission, cached | No. One Judge.me API GET per uncached product lookup. |
| `collector_vault_api.collector_vault_asset()` | R2 presigned URL or a saved certificate asset URL when a user requests an asset | Not a page crawler. One streaming GET, redirects allowed by Requests, no crawl or retry loop. A wrongly stored asset URL could be fetched once. |
| `meta_ads_client` | Meta Graph API, user/report refresh | No. Bounded API pagination only. |
| `planning_ai`, `seo_growth_intelligence.generate_openai_report`, `ads_final_review` | OpenAI API on explicit generation | No. |
| `email_service.ResendEmailProvider` | Resend API on explicit email delivery | No. Persistent provider session; bounded retries, unrelated to Shopify. |
| Dropbox/Drive/R2 helpers and maintenance scripts | Their named APIs or explicitly supplied asset URLs; user/admin/maintenance actions | No product-page discovery or storefront crawl found. |
| `app.build_shopify_product_url_from_handle()` and Streamlit `link_button`/Markdown links | Constructs browser links for a human to open | No server-side request. A user's browser navigation is genuine interactive traffic. |
| Render and webhook health checks | Sports Cave OS `/_stcore/health` and webhook `/healthz` | No Shopify request. |

Repository-wide searches found no Selenium, webdriver, Playwright, `urllib.request`, live `robots.txt` fetcher, live sitemap downloader, or other recursive page crawler.

## Implemented controls

- Persistent `requests.Session` for the complete run, including optional Google evidence calls.
- Central honest User-Agent and headers.
- Deterministic one-request-per-second default throttle.
- Hard on-wire request budgets that include redirects, retries and HEAD fallbacks.
- HTTPS/host/trailing-slash/fragment/tracking-parameter URL normalization and per-run deduplication.
- Page and status caches shared across top-level pages and internal-link checks.
- HEAD-first link status checks with a streaming GET fallback for servers that reject HEAD.
- Daily selection restricted to queued rechecks, new/changed URLs and records whose next eligible time has elapsed; default page limit reduced from 100 to 20.
- Explicit `full` mode for infrequent maintenance; it is not wired to Analytics, Streamlit rendering, the worker or the daily cron.
- Persistent page state: last audit time/status, SHA-256 content fingerprint, findings and next eligible time.
- PostgreSQL expiring lease plus an in-process fallback lock for test/non-database stores.
- Saved run observability: run ID/timestamps/trigger/mode/scheduled/fetched/HEAD/GET/cache/dedup/redirect/failure/request-total/runtime/lease state.
- Analytics and growth-reporting pipelines no longer contain a Technical Audit stage. Pipeline claims are mode-scoped.
- SEO Health renders saved findings and saved audit-run metrics only.

No OAuth state, historical Analytics/SEO data, Shopify theme code, customer data or production resource was changed.
