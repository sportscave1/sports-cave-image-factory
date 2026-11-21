# Sports Cave Marketplace launch

Task: `20261120-4f30e264` · Owner: `codex-marketplace-01a1f6fa-20261120`.

The public marketplace is `/marketplace` on the canonical Sports Cave OS service.
The administrator menu includes **Marketplace**, with Listings, Enquiries and
Website & publish. The public header and footer link to the existing shop.

Seller submissions include actual item photographs, condition, seller type,
asking price, tracked postage and provenance. They stay private until an
administrator reviews and publishes them. Contact information and enquiries
are never included in public responses. Withdrawal also withdraws photo access.

This is the founding seller and enquiry release. Checkout, reservations, seller
identity verification, automated seller messages, payment collection, payouts,
refunds and disputes remain to be implemented with the chosen payment provider.
The planned 5% fee is labelled indicative; this release charges nothing.
No sample listings are installed in production. No Shopify theme or navigation
mutation is part of this release. The public URL can be added to the shop menu.
No marketplace custom domain or DNS record is configured by this release.

## Website publishing

Website settings are tracked in `static/marketplace/site.json`. The OS editor
keeps private drafts and publishes just that allowlisted file to GitHub `main`
using the existing `PROMPTS_GITHUB_TOKEN` connection. The existing Render service
auto-deploys the commit. Publication receipts distinguish a GitHub update from
the new website release actually running in OS. Durable attempt IDs allow an
interrupted request to be reconciled before another publication. Concurrent
website changes fail closed. All code changes use the ordinary isolated task,
review, focused tests and explicit release authorization workflow.

## Storage and deployment

Marketplace records use a separate `marketplace:v1:` namespace in the existing
private `crm_runtime_state` table. Writes and moderation revisions are
transactional. Images are bounded, re-encoded WebP with metadata removed; no
arbitrary uploads or external image URLs are exposed. No schema migration,
infrastructure change or additional Render service is required.

`sports_cave_server.py` registers standalone Starlette routes. Public pages use
server-rendered HTML, one small stylesheet and script, the existing logo and
Montserrat fonts. Catalogue/item pages include canonical URLs, social metadata,
JSON-LD and a sitemap. Filtered search pages are noindex. Public assets use
validators; private responses and photos use no-store.

## Verification

Run with the project's existing Python environment:

```text
python -B scripts/test_marketplace.py
python -B scripts/check_marketplace_layout.py
python scripts/validate_render_topology.py
node --check static/marketplace/marketplace.js
```

The focused runner uses an allowlisted environment with no production
credentials. Browser checks route requests into an in-process synthetic ASGI
fixture, block external network requests and start no application server or
worker. They cover desktop/tablet/mobile overflow, seller submission, buyer
enquiries and JavaScript errors. Screenshots and results are local ignored
artifacts under `.tmp-marketplace-layout/`. Full production OS startup is not
used as a development preview.

The optional `python -B scripts/test_marketplace.py --legacy` run also checks
the wider account and install-branding suites. Its eight failures were
reproduced against unchanged baseline `ae5505f28a539ac58e8ee81a824c0e22e2882fc9`:
six existing account/UI expectations and two old install-branding source
assertions. They are not marketplace regressions. The default runner keeps the
focused marketplace, navigation and prompt-publication checks together.

The user explicitly authorised pushing this marketplace release to Git and the
existing Render application. Other unfinished original-workspace changes are
excluded. Keep this task branch/worktree for review after release.
