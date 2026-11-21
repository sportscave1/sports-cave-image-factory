# SEO daily review refresh

Authorized by the 21 November request to implement the consolidated SEO workspace,
schedule ChatGPT at 04:00 Sydney daily, and push/deploy to existing Git/Render.
Studio task: 20261121-92189705; owner: codex-seo-20261121-01a1fc45.

- One visible SEO destination; review, strategy, source evidence, planning,
  content approval, manual tools, report archive and activity are available here.
  Old routes and their permission checks are retained. Companion stays separate.
- The SEO page polls its saved report every 30 seconds. Home reads the same
  edition through its existing background display snapshot. Its compact SEO
  card occupies the former SEO insight area; legacy insights remain until a
  dedicated report is available.
- The existing hosted brief worker accepts SEO editions, rechecks owner/SEO
  access, validates bounded content and storefront targets, archives by date,
  prevents conflicting same-date editions and verifies durable publication.
  No schema migration, new Render service or Blueprint sync is required.
- The connector exposes comparable 28-day GSC query/page and GA4 Google-organic
  landing-page evidence for AU/US/UK. Output is bounded to 100 rows per source,
  period and market, with explicit truncation and source limitations. Installed
  connector catalogs can use get_growth_analytics.seo_daily_context and
  seo_publication; kind=meta with edition.destination=seo routes publication to
  SEO without replacing the Meta brief.
- ChatGPT cloud Scheduled task: Sports Cave SEO — Daily Review, daily at 04:00
  Australia/Sydney. It prepares up to three evidenced opportunities and one
  Companion instruction, publishes through the existing connector and checks
  publication status. Unavailable sources produce gaps instead of invented data.
- This release does not supply a new automatic Shopify SEO executor. Approved
  task instructions are reviewed on SEO and execution remains in Companion.
  Reporting publication is separate from storefront publication and outreach.

Validation uses synthetic reports and disposable local PGlite only. No production
credentials or customer data are used in development. Focused tests cover the
single-page plan/review flow, market/date windows, serialization, URL validation,
HTML escaping, SQL persistence, same-day conflicts, readback and retry recovery.
The existing unrelated design-prompt assertion in
test_full_edition_and_selected_story_design_prompt fails against unchanged
design code; it is excluded from the focused release run.

Render topology validator passes. render.yaml is unchanged; existing primary
sports-cave-os and supporting sports-cave-seo-worker retain their identities.
