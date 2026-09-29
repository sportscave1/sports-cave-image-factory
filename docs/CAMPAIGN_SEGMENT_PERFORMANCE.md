# Campaign performance and Segment labels — local report

## Measured cause and result

The old synchronous `market_control` called `calculate` before rendering the Segment widget, send timing or preview. A cold session or expired two-minute session cache fetched every customer using a broad 50-record query including names, tags, spend and last-order fields. One scan already served all regions, but country normalization ran three times per profile and eligibility/deduplication ran four pipelines. Template defaults and recent campaign lists also retrieved full bodies unnecessarily.

Controlled server-side Streamlit AppTest profile: 1,000 synthetic customers; an injected 80 ms delay per Shopify response; disposable local PostgreSQL/PGlite. No live-store or browser timing is claimed. Timings include local test/framework overhead and are approximate, not production guarantees.

| Measurement | Before | After |
| --- | ---: | ---: |
| Initial Campaign route render | 2.574 s | 0.930 s |
| Subscriber calculation | 1.688 s, blocking | 0.387 s, background |
| Shopify scan calls | 20 × 50 records | 4 × 250 records |
| Shopify response time total | 1.620 s | 0.332 s |
| Country normalization | 3,000 calls / 1.51 ms | 1,000 calls / 0.78 ms |
| Eligibility/dedup | 4 pipelines / 9.83 ms | one grouped traversal; 1,000 shared eligibility calls / 3.22 ms |
| Suppression read | 46 ms | 30 ms |
| Preview renderer | 1.26 ms | 1.28 ms |
| Cached full rerender | not measured | 0.415 s; zero Shopify calls |
| Cached aggregate lookup | not measured | 0.018 ms |

After-profile brand-template metadata reads totaled 99 ms over four calls across initial and cached renders. Recent list metadata totaled 24 ms across two calls. A blank campaign made zero full-draft loads and zero HTML-library loads; default header/footer remain available. Exact raw profiles are in `tests/fixtures/segment-profile-before.json` and `segment-profile-after.json`; `tests/profile_campaign_segments.py` reproduces the after profile locally.

## Deferred counts and cache

`crm_segment_counts.py` supplies a bounded server-process cache of only four numeric counts, isolated by Shopify namespace, database connection factory and Smart Sending interval. It is shared across sessions in that process, not browser/session-only storage and not an audience/customer mirror.

- TTL: **600 seconds (10 minutes)**.
- One in-flight refresh per key; two background threads maximum and 32 cache entries maximum.
- Revision checks happen in the background at most every 10 seconds; local unsubscribe revision changes trigger refresh without waiting for TTL.
- An unsubscribe occurring during calculation prevents publishing the stale result as fresh.
- Failures retain last known counts; empty cache displays dashes. Safe exception-class logging and a 60-second retry backoff avoid repeated storms.
- The Segment control polls in its own two-second Streamlit fragment. It renders placeholders immediately and never awaits storage/Shopify. Hydration does not rerun the editor or preview. User segment changes retain the normal editor refresh for catalogue context.
- Separate server processes maintain separate display caches; there is no new infrastructure or database migration.

The narrow read-only Shopify query requests ID, email validity, consent state, country and existing scheduler timezone/province evidence. It uses the same Shopify connection/API configuration, bounded pagination, conflict checking and safety limits. Schema validation passed against the bundled 2026-04 schema; existing deprecated customer-email fields remain supported. Reference: https://shopify.dev/docs/api/admin-graphql/latest/queries/customers

## Eligibility and final send

The existing shared `eligibility` policy is evaluated once per profile after grouping normalized email hashes. Consent conflicts, local suppression by hash/customer ID, invalid addresses, Smart Sending and deduplication are preserved. A randomized regression compares the optimized result against the previous per-region pipeline, including cross-country duplicate profiles.

Visible options are exactly **AUSTRALIA**, **USA**, **UK**, **ALL SUBSCRIBERS**. Internal `AU`, `US`, `UK`, `Global` identifiers remain stable, with no draft/schema migration. Country filters remain AU/US/GB. All subscribers deduplicates eligible addresses worldwide, including other/unknown countries; it is not the sum of the three named countries. Existing country-specific duplicate handling is preserved.

Normal selector, recent-list and review labels use **Segment**. Final review and queue preparation continue calling fresh `calculate`, never the count cache. Send Test does not request subscriber counts. Production consent/suppression/queue gates and scheduling logic were not weakened.

## Template, list and preview loading

- HTML library is still deferred until requested; its list now returns only metadata. Selected HTML is loaded and its version checked before use/edit.
- Header/footer choices carry metadata plus a source fingerprint. Initial blank compose resolves only the chosen default bodies. Other HTML is fetched upon selection; a stale/unavailable selection preserves the existing source and reports an error.
- Recent campaigns return only list fields plus segment/timing metadata; opening a campaign still loads its full authoritative document. Older missing send-timing fields are handled safely.
- Pure HTML previews reuse cached safe output for a segment-only change. Catalogue snapshot/content changes still change the render key; legacy block output remains segment-aware. Count hydration never touches the preview fragment.

## Files changed for this task

Runtime: `crm_campaign_controls.py`, `crm_segment_counts.py` (new), `crm_campaign_markets.py`, `crm_shopify.py`, `crm_campaign_page.py`, `crm_campaign_store.py`, `crm_campaign_send_ui.py`, `crm_workspace_store.py`, `crm_campaign_library.py`, `crm_brand_templates.py`, `crm_brand_template_ui.py`, `crm_preview_cache.py`.

Tests/evidence: `tests/test_crm_segment_performance.py` (new), `tests/test_crm_campaign_v2.py`, `tests/test_crm_production_unsubscribe.py`, `tests/test_crm_ui.py`, `tests/crm_fixtures.py`, `tests/crm_db_fixture.py`, `tests/profile_campaign_segments.py`, both profiling JSON files, and this report. The SQL fixture now serializes whole transactions because its single embedded database connection is shared by UI/background test threads; production pooling is unchanged.

## Safety and Git state

No real emails, Shopify customer changes or production data changes occurred. CRM_MARKETING_ENABLED remains false/default-off; no environment flags were edited. No production deployment or infrastructure change was performed by this agent.

During implementation Git HEAD advanced externally from `c538dd2` to `849f0f9` ("Deploy CRM unsubscribe, test email, and campaign performance updates"), incorporating some work in progress. This agent did not commit, push or deploy. Remaining local fixes are uncommitted; the external commit/deployment state is not claimed as verified here.

## Final validation

- CRM suite: 270 tests passed.
- Final focused segment/template/campaign checks after defensive error handling: 39 passed.
- Email suite: 144 run, 143 passed, 1 skipped.
- Navigation suite: 35 run, 34 passed, 1 skipped.
- Startup scope suite: 6 passed.
- Python compilation of all affected modules/tests/profile script passed.
- `git diff --check` passed.
- Actual Streamlit AppTest verified editor interaction, tab switching and mocked Send Test while subscriber fetch was deliberately blocked. No browser viewport checks or live Shopify/mail requests were performed.

Ready for Nathan to test locally. Approval/deployment remains separate.
