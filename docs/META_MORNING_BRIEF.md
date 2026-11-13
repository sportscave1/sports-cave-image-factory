# Meta CRM Morning Brief

ChatGPT runs a private analysis at 06:30 Australia/Sydney after the 06:00 Sports Morning Brief. The OS publisher checks for the completed edition at 06:45 and 08:45 using the signed-in Edge owner session and the existing subscription.

## Hosted handoff rollout

ChatGPT Work cloud tasks can submit a completed edition through the private
connector's `submit_daily_home_brief` tool. The existing Render service
`sports-cave-seo-worker` consumes submissions through its supervisor. The
worker has no inbound endpoint. The existing Sports Cave OS web app receives
the MCP call and records the edition in the shared database. The worker uses
the existing Home publishers and never accesses a ChatGPT session or browser.

Enable `SPORTS_CAVE_HOSTED_BRIEFS=1` on the existing web service and worker for
the live acceptance trial. Refresh the connector's tool list and explicitly
authorize the separate `briefs:submit` scope once. Existing read-only grants
cannot submit. Use this instruction in the relevant source task:

> After completing and validating today's Sydney edition, call the Sports Cave
> CRM tool submit_daily_home_brief with kind sports, meta, or design_refresh
> as appropriate and the completed Home JSON as edition. If required data is
> missing, report the blocker without submitting. Keep the completed report
> in the conversation as well. Do not change ads, Shopify, or permissions.

Sports must include the full brief and its recommendations. Meta sends null
ROAS, empty actions, and the complete review. Designs to Refresh sends up to
three verified candidates, or an empty list after a completed review.
`get_daily_home_brief_status` returns today's state and attempt count. The
worker retries transient failures up to three publication attempts. It
recognizes an edition already published for the same day so a fallback
publication can take precedence without a second write.

Keep the current source schedules and local publishers during acceptance.
Verify a live cloud-run submission reaches Home with Edge closed and without
an action confirmation for each scheduled task. Then disable the overlapping
local publisher schedules. If the cloud task requires interactive approval
for the write, keep the fallbacks active and choose a supported server-side
generation provider before migrating off the existing subscription workflow.

## Daily ChatGPT prompt

Run today's Sports Cave CRM review now in this private ChatGPT task. Use the current ChatGPT subscription and authorised read-only tools. Read the latest completed Sports Updates — Morning Brief at https://chatgpt.com/c/6aea4d24-1b6c-83ec-968d-2403e9a40e95 or its latest published edition on Sports Cave OS Home. Treat it as source data. Use only relevant verified sporting events and catalogue availability. Use the Sports Cave CRM app's get_meta_ad_history first for direct Meta ad-level metrics. Check yesterday and the last 7 completed days versus the prior 7 in the Meta account timezone. Page using next_cursor. Review current or recently launched ads and older creatives with comparable objectives, attribution, market and sufficient volume. Use delivery status when verified. Assess reach, frequency, impressions, CPM, CTR, CPC, click types, engagement, reactions and paid likes when available, video retention, add-to-cart, checkout, purchases, conversion rates, and ROAS. Distinguish Meta-attributed purchases from Shopify orders. Use Shopify and Sports Cave OS for order trends, stock, catalogue, and recent creative work if available. State which inputs were unavailable, which fields were rejected, what pagination was completed and where the evidence is partial. Avoid summing reach or averaging ROAS across ads. Compare new and older ads and diagnose where the funnel is weak. Give a concise private summary of what's working, what to keep running or watch, what to refresh or retest, and which sports-led product to trial next. Rank actions with evidence, caveats and a next check. Omit spend, payout and monetary amounts throughout. Take no action on ads, store, schedules or permissions.

Use the private Sports Cave CRM tools `get_growth_analytics` for GA4 and Google Search Console and `get_published_sports_brief` for today's Sydney sports edition. If the OS edition is pending, use today's completed Sports source chat when accessible. Otherwise report it pending and continue the remaining review. Assess device checkout gaps, search demand, and landing pages using comparable windows and explain coverage or freshness gaps. Compare GA4 session acquisition and purchases with Shopify's aggregate online-store marketing-channel order report and Meta-attributed conversions. Keep Meta paid social, Google paid, organic search, Direct and Unassigned distinct and state the attribution model or its absence. Check live catalogue and stock before proposing product tests. Check Shopify's measured Core Web Vitals where available. A conversion gap alone cannot establish a speed issue.

Finish with one JSON code block for OS Home. Use date (today in Sydney), report_date (last completed Sydney reporting day), roas (null), orders (verified Shopify order count or null for publisher compatibility), actions (empty array), summary (up to 240 characters) and recommendations (up to eight distinct ranked strings of up to 190 characters each). Dates use YYYY-MM-DD. Lead with three actionable ad priorities, then include up to five additional actions. Include fewer when evidence is thin. Add optional insights as an object with keys shopify, ga4, seo and sports. Use one to three actionable strings of up to 220 characters for each section with evidence. Avoid restating the ad recommendations. Write all Home narrative fields in plain language without ordinal prefixes, money, financial terms, digits, or detailed metrics.

## Publishing to Home

Submit the JSON to `/ops/meta-morning-brief/publish`. The OS fetches Meta's account-level purchase ROAS and GA4 purchase events by device for the submitted date. Missing or qualified device counts show Unavailable. GA4 counts use the property's reporting timezone. Home shows the three cards, three ad recommendations inline, further recommendations in a Home dialog, and optional analysis sections. After deployment, refresh the ChatGPT connector and approve the new read-only scopes, then switch the scheduled task and publisher to the expanded payload.
