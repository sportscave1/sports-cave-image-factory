# Production unsubscribe — local implementation

## Flow and endpoints

The existing FastAPI CRM router is already mounted by `webhook_server.py`, served by the existing **sports-cave-os-webhooks** service. No service, routing topology or Render configuration changed.

- `GET /crm/unsubscribe?token=<signed-token>` displays the existing confirmation form; GET never mutates subscriptions, protecting recipients from email link scanners.
- `POST /crm/unsubscribe?token=<signed-token>` validates the signature and stored production receipt, commits local suppression and audit, then attempts Shopify synchronization. Browser confirmation and RFC 8058 one-click POST use the same path; no login is required. Marketing OFF does not disable either route.
- `GET` / `POST /crm/unsubscribe/test` displays a branded no-op test confirmation, without touching storage or Shopify.
- Success: “You've been unsubscribed. You won't receive marketing emails from Sports Cave.”

## Token and required configuration

Reuses **CRM_UNSUBSCRIBE_SECRET**, at least 32 random characters, identical on the sending worker and webhook service. Keep this stable and backed up: rotating/removing it invalidates old links. No expiration is imposed. The token is a random send receipt UUID plus HMAC-SHA256 over `crm-marketing-opt-out/v1:<UUID>`, verified with constant-time comparison. Earlier legacy signatures remain accepted. The URL contains neither a plain email nor Shopify customer ID. Test receipt IDs cannot unsubscribe anyone.

Set **CRM_PUBLIC_BASE_URL** to the HTTPS origin of the existing webhook service; the existing **SPORTS_CAVE_WEBHOOK_BASE_URL** fallback remains supported. Do not point it at the Streamlit app. Preview/test rendering uses only `/crm/unsubscribe/test` when this origin is configured; otherwise the existing inactive test text remains. No new credentials/authentication scheme was added.

The existing Shopify connection still reads **SHOPIFY_API_VERSION** and existing app credentials through `shopify_sync`. No API version override was introduced. Repository fixtures and the installed schema validator use **2026-04**; validation passed against that schema. The local process/dotenv does not specify the runtime API version, so the deployed value was not independently verified or changed.

## Storage, ordering, idempotency and retries

No migration is required. Reuses `crm_suppressions`, its existing `shopify_sync_state`, `shopify_sync_attempts`, `shopify_sync_error`, `shopify_sync_checked_at`, `crm_marketing_events`, and the existing runtime cache revision.

`Store.record_unsubscribe` commits suppression, existing active-enrollment stopping, a receipt-keyed `email.unsubscribed` audit event, and a cache revision together. Only after that transaction commits may Shopify client initialization or network I/O occur. An unavailable Shopify configuration cannot stop the local opt-out.

The only new Shopify write is `customerEmailMarketingConsentUpdate(input: { customerId, emailMarketingConsent: { marketingState: UNSUBSCRIBED } })`. It uses the existing GraphQL transport and checks user errors, returned identity and acknowledged state. It never subscribes customers. The schema validator confirms `write_customers` and `read_customers`, matching the installed scopes the user confirmed. No live mutation/scope probe was performed. Shopify currently deprecates the returned `emailMarketingConsent` field; it remains valid in the validated schema and matches the existing CRM customer model.

Failures retain active local suppression and durable PENDING / `writer_unavailable` state, with only exception class logged. An atomic five-minute claim/backoff prevents concurrent clicks/workers from duplicating the write. Successful rows become SYNCED; repeat clicks return success without another mutation. Ambiguous failures can safely retry the unsubscribe-only state assignment. The existing CRM worker processes up to five due opt-outs per cycle even with marketing OFF, independently of Resend credentials. **Background retries require that existing worker command to be running**; no worker deployment was performed. A repeated confirmed click can also retry after the interval. Local suppression is never cleared by sync or a later Shopify SUBSCRIBED state.

## Rendering and audiences

Existing canonical production rendering resolves the required footer token to the signed recipient URL. A removed/unlinked unsubscribe token blocks production rendering; no second visual footer is appended. Existing Resend `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers remain intact. Legacy queued tests now also receive only a no-op URL, never a production token.

AU, USA (internal US), UK and GLOBAL already use shared consent/suppression eligibility. Final send preparation and delivery continue checking that authority. Displayed market counts now invalidate their short cache on the suppression revision, so a subsequent rerun/refresh recalculates immediately. Database outages show unavailable counts and preserve the editor, rather than falsely showing eligible totals.

## Files changed

- `crm_webhooks.py`: local-first unsubscribe orchestration.
- `crm_store.py`: atomic suppression/audit/cache revision.
- `crm_consent_sync.py`: durable claimed retry implementation.
- `crm_shopify.py`: narrow shared-connection consent mutation.
- `crm_engine.py`: pending opt-out reconciliation and safe legacy test URLs.
- `crm_http.py`: lazy Shopify initialization, branded success and no-op test page.
- `crm_resend.py`: token-input hardening and safe test URL helper.
- `crm_campaign_footer.py`, `crm_campaign_content.py`: no-op preview/test links.
- `crm_campaign_controls.py`: suppression-aware count cache.
- `tests/test_crm_production_unsubscribe.py`: 14 focused regressions.
- `tests/test_crm_boundaries.py`, `tests/test_crm_workspace.py`: update existing contract/backoff expectations.
- This report.

## Verification and safety

All database tests use disposable loopback PostgreSQL/PGlite. Shopify and email transports are mocked; no customer data, consent, emails, or production environment were changed. HTTP confirmation/no-op/one-click routes are exercised locally through FastAPI TestClient. No browser screenshot or live Shopify test is claimed.

CRM_MARKETING_ENABLED remains false by default locally; no environment or production configuration was edited. Nothing was committed, pushed or deployed by this task. Existing production readiness gates remain unchanged. Safe for local review; later approved deployment must configure the shared secret and correct webhook origin, verify the deployed API version and run a controlled consent test before enabling marketing.

### Results

| Check | Result |
| --- | --- |
| CRM/Campaign suite (includes 14 new unsubscribe tests) | 256 passed |
| Email regression suite | 144 run: 143 passed, 1 existing skip |
| Support Email regression suite | 212 passed |
| Navigation/performance/sidebar suite | 35 run: 34 passed, 1 existing skip |
| Startup scope regressions | 6 passed |
| Webhook health/responsiveness | 6 passed |
| Python compilation | 13 affected Python files passed |
| Shopify GraphQL validation | Valid against bundled 2026-04 schema; returned consent field deprecation noted |
| git diff --check | Passed |
