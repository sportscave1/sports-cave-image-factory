# Daily SEO Companion execution

Studio task 20261121-2252092d, owner codex-seo-companion-20261121-01a1fc45.
Continuation of the authorized SEO refresh and live release, following the
request to start the Peter Brock link audit and return proposals/results to SEO.

Companion → SEO queue controls a persistent opt-in setting. Starting it queues
today's published daily report. Future SEO report publications enqueue the next
date in the same SQL transaction. A reconciliation poll also recovers a missing
queue entry from the latest current-day report. Each date has one immutable job
identity; retries do not overwrite another day's work or repeat completed audits.

The executor runs on its own thread in daily_brief_worker within the existing
sports-cave-seo-worker service. It does not require the desktop browser, a new
Render service, a migration, or model/API credits. It checks the current owner's
SEO and Companion access before opening a network session. Claims use locks and
a unique lease; stale workers cannot overwrite a newer attempt. Interrupted jobs
retry up to three times. Pause prevents new starts; active read-only work finishes.

The first audit targets the URLs in the published report, including the retired
Peter Brock edition. It enumerates collection, editorial, blog and static-page
sitemaps and follows eligible public HTML navigation. It records source URL,
anchor, original href, resolved destination, response and technical findings.
The crawler allows only GET/HEAD to the public Sports Cave storefront, excludes
account/admin/cart/checkout paths, respects scoped robots rules and wildcard
specificity, uses the existing throttled crawler, and caps discovery, HTTP
requests, page bodies, page count, result size and elapsed time. Redirects do not
grant access to an external host. Coverage limits and failures stay explicit.

SEO displays audit progress, checked pages, target responses, matching links,
coverage gaps, downloadable evidence and proposed fixes. Review decisions are
bound to the result revision. Approval records a decision; it does not publish
edits. No Shopify/theme/redirect/outreach writes are implemented in this executor.
Keyword research and copy/outreach drafting remain in the daily ChatGPT report;
admin availability checks and live implementation remain review work.

An absence of observed links applies only to checked public server-rendered HTML.
JavaScript-only links, private content, product recommendation panels on other
product pages, external backlinks, inventory and AU checkout are outside scope.
An absent retired page is not automatically redirected to an unrelated category.
