# Product Upload V2 + Campaigns V8 — local readiness review

11 October 2026. **Implemented locally; not deployed.** No commit, push, live
product write, campaign send, consent modification, flow activation or production
database migration was performed. Main remains at
`2af257694032fb6a9aaaca4ebced7c364d4440d7`. This report does not claim a new live release.

## Delivered

- The existing three upload prompts retain their original bodies, pricing/copy,
  variants, media, collection/publication and Edition Ops behavior. Only the shared
  appended tagging policy is extended. The tagging-only webhook adds and verifies
  missing tags, preserves existing tags, retries safely and requires review for
  contradictory evidence.
- Motocross, Rally, Motorcycle Road Racing, Rally Raid and IndyCar join the four
  original motorsport disciplines. All nine receive their exact child tag and
  Motorsport parent. Dakar and Isle of Man TT are classified by depicted event,
  not a rider's unrelated career. All 28 tag mappings are covered.
- Existing Campaign Settings now has Location followed by a searchable, removable,
  clearable multi-selection of Shopify buyer segments. New campaigns start with
  All subscribers and no segments. Saved geography and selections are preserved.
- All 28 real Shopify segment IDs/definitions were discovered read-only. Runtime
  discovery is per store; no IDs are invented or copied into runtime configuration.
- Authoritative membership synchronization uses the existing worker, paginated
  Shopify adapter and server-only runtime storage. Background cache/projection is
  store scoped, atomic and explicitly dated. No new migration or service is added.
- Location AND segment union is resolved from saved Shopify definitions. Existing
  historical tag clauses remain intact. Consent, suppression, identity/email
  deduplication, native unsubscribe links, frozen dispatch and idempotency remain.
  Selected-segment dispatch rechecks current membership and consent before submission.

## Verification

| Check | Result |
|---|---|
| Product Upload focused suite | **69 passed, 0 skipped**; original 67 plus two new test methods, including all nine real webhook discipline/retry cases |
| Product Upload broader suite | **207 run; 13 failing assertions; 16 existing skips** |
| Deployed-source pricing/copy baseline | **181 run; identical 13 failing assertions and 16 skips** |
| Campaigns + selected-segment integration + existing lifecycle suite | **152 passed, 0 skipped** |
| Browser | Edge, synthetic real Settings controls at **1440 / 768 / 390 / 320px**; multiple selections retained, no horizontal overflow |
| Live Shopify read-only definition discovery | All **28** expected buyer segments present; no segment mutations |
| Live read-only composed query check | Australia AND (Cricket OR Motorsport) accepted; **354 members**, not a verified sendable total |

The four pre-existing Product Upload test methods and their pricing/copy issues are
listed in the Product Upload report. No new broad-suite assertion failure was found.
These are not presented as a fully passing product regression suite.

The tests use synthetic Shopify and a fake mail transport. SQL integration runs
against disposable loopback PGlite, including actual projection locking, cache
persistence, renaming, queueing and scheduled dispatch. No production credentials
are passed to the test child. External socket connections are blocked. Unrelated
thumbnail generation is mocked. Streamlit background executors are terminated with
the disposable test child **after** test teardown and the actual result is flushed;
failed tests still return a failing exit status.

Early test attempts included obsolete Segment-label assertions, fixture mock
leakage, a test indentation error and browser fragment-mock lifecycle errors; these
were corrected and rerun. Earlier overlapping local runners were stopped only after
their exact command lines proved ownership. No unrelated process/work was stopped.

## Measured performance

Final synthetic Edge navigation samples, 12 per version, cached fixture data:

| Controls visible | Before | After |
|---|---:|---:|
| p50 | 316.3ms | 211.2ms |
| p95 | 1098.9ms | 296.7ms |

These include browser navigation and Streamlit delivery, not just a cache lookup.
The **under-200ms target was not achieved** in this local fixture. Small sample size
and sequential phases (including a cold first baseline navigation) limit causal
conclusions; do not treat this as production
performance. Raw samples and screenshots: `buyer-segments-v8-evidence/`.
No synchronous membership retrieval is added to normal Settings rendering. The
new selected-segment dispatch checks intentionally add Shopify reads; production
throughput and the cold all-28 membership synchronization are not benchmarked.

## Release prerequisites / remaining attention

1. Review the existing 13 pricing/copy baseline failures before approving a broad
   release. They were not repaired by rewriting the protected original prompts.
2. Verify the deployed app token has `read_customers` and protected customer-data
   access, plus product `read_products` / `write_products` for the tag hook. The
   connected Shopify tool's read access does not prove application-token access.
3. Verify existing authenticated product create/update webhook subscriptions and
   the continuously running **existing** CRM worker. This change starts no live
   worker and changes no Render service. Check independent-worker lease/concurrency
   configuration at release; do not add a duplicate primary service.
4. Verify already-required CRM workspace/preparation/runtime/dispatch migrations
   are applied. **This upgrade has no new migration; none was applied here.**
5. The existing member adapter caps an audience at 20,000 and fails closed on
   incomplete/changing pages. Shopify queries requiring asynchronous query jobs
   are not newly supported; an async-required response blocks that audience.
6. The under-200ms browser target and production throughput remain unverified.
7. Review selected changes through an isolated source patch. Main intentionally
   still contains unrelated unfinished Inbox, collector-template and other work.
   Do not run an unrestricted full deployment or approve whole shared files.

## Change isolation and files

Product files: `product_sport_tags.py`, `product_sport_tag_sync.py`; Product Upload
finalizer hunks in `app.py`; product-hook hunks in `supabase_backend.py` and
`webhook_server.py`; `tests/test_product_sport_tags.py`,
`tests/test_product_sport_tag_integration.py`, `tests/test_product_upload_prompts.py`,
`tests/test_product_activation_sync.py`, `tests/test_product_webhook_restoration.py`,
`tests/test_shopify_sync.py`.

Campaign files: `crm_buyer_segments.py`, `crm_campaign_controls.py`,
`crm_campaign_page.py`, buyer-field validation hunks in `crm_campaign_content.py`,
`crm_campaign_audience_prepare.py`, `crm_campaign_send.py`,
`crm_campaign_dispatch.py`, `crm_campaign_store.py`, `crm_worker.py`.

New campaign verification files: `tests/test_campaign_buyer_segments.py`,
`tests/test_campaign_buyer_dispatch.py`, `tests/test_campaign_buyer_ui.py`,
`tests/fixtures/campaign_buyer_segments_preview.py`, `tests/run_buyer_segments_local.py`,
`tests/serve_campaign_buyer_preview.py`, `tests/check_campaign_buyer_browser.py`.
Existing UI fixture expectations updated in `tests/test_crm_campaign_v2.py` and
`tests/test_crm_segment_performance.py`.

Documentation/evidence: this report, `PRODUCT_UPLOAD_AUTOMATIC_SPORT_TAGGING_V2.md`,
`EMAIL_CAMPAIGNS_LOCATION_SEGMENTS_V8.md`, `shopify-buyer-segments-observed.json`,
`buyer-segments-v8-evidence/`. The review-only source patch and file/hash manifest
are under `.tmp-product-sport-tags-v2/combined-release/`.

`app.py` also contains active Inbox changes. `crm_campaign_content.py` also contains
the separate collector-template task's imports/render hooks. Those unrelated hunks
are excluded from the review patch, preserved in the main working directory.
No collector modules, account-extension changes, Inbox files, deployment manifests,
temporary worktrees or unrelated task changes are part of this release selection.

## Deployment / rollback plan

After review and fresh authorization, prepare an isolated approved release against
the current GitHub base, apply only the selected patch/hunks, rerun checks, then use
the existing manual PowerShell deployment workflow. The helper itself was not
changed in this task. Verify Render's actual expected commit and health separately
from Git push. Deploy primary/webhook/worker code consistently without new services.

Before a rollback, pause buyer-targeted queued campaigns for review so older code
cannot broaden their audience. Preserve draft IDs and membership projections;
do not remove sport tags or historical customer data. Reverting application code
does not reverse additive Shopify tags already written after a future deployment.

Welcome, Post Purchase and Win Back remain outside this change, Draft and
activation-locked. The lifecycle regression suite verifies those protections;
no live flow state was mutated. No marketing emails were sent.
