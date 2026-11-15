# Shopify receiver readiness repair — 5 October 2026

Read-only production inspection, local code changes only. No Render environment,
Shopify subscription, send, allocation, schema or deployment changes.

## Confirmed incident

Production `GET https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/readiness`
returned HTTP 500, `text/plain; charset=utf-8`, body `Internal Server Error`.
Receiver logs at 2026-10-05T02:41:01.786452Z identify `webhook_server.py:180`:
`routes = {route.path for route in app.routes}` raised
`AttributeError: '_IncludedRouter' object has no attribute 'path'`.

The local FastAPI 0.136.3 fixture flattened included routes, hiding this production
compatibility defect. Readiness now uses public `app.url_path_for()` to resolve the
two named handlers through either flattened or included router containers, checking
their resolved paths. It does not skip router containers or assume they are missing.

The OS/client `crm_shopify_webhook_config.receiver_readiness()` then raised
`ValueError('Receiver readiness unavailable')` in its non-200 response branch;
`crm_automation_capabilities.verify()` reduced that to the exception class name.
The original problem was route inspection, not URL/JSON parsing, timeout or secrets.

## Contract

HTTP 200, application/json, Cache-Control no-store, X-Content-Type-Options nosniff:

```json
{
  "service": "sports-cave-os-webhooks",
  "receiver_reachable": true,
  "base_url": "https://sports-cave-os-webhooks.onrender.com",
  "callbacks": {
    "crm": "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/crm",
    "paid": "https://sports-cave-os-webhooks.onrender.com/webhooks/shopify/orders-paid"
  },
  "api_version": "2026-04",
  "routes_ready": true,
  "hmac_status": "CONFIGURED"
}
```

`CONFIGURED` means an eligible signing candidate exists under the existing shape
classification; it does not prove the secret is correct. `VERIFIED` additionally
means this running receiver accepted a real HMAC-verified request. Restart resets
that proof. Other values are `MISSING` or
`MALFORMED — Admin API token is not a webhook secret`. Secret selection/verification
is unchanged. No secret names/values or customer payloads are returned.

Configuration failure still returns machine-readable HTTP 200: an invalid/missing
base is empty, a missing route sets routes_ready false, the configured API version
is reported and HMAC failures retain their status. The client distinguishes those
from an unavailable receiver and reports a safe specific configuration reason.
The optional receiver_reachable field keeps compatibility with the previous report
during rollout. No database or provider work occurs in the handler.

Transport remains HTTPS-only, redirects disabled, connect/read timeouts 3/5 seconds,
4096-byte response acceptance limit. Typed safe errors distinguish HTTP status,
timeout, unreachable receiver, excessive response, invalid JSON and malformed
contract. Diagnostic errors never echo response bodies, credentials or arbitrary
exception messages. All failure paths continue to block trigger readiness.

## Callbacks and remaining readiness

CHECKOUTS_CREATE, CHECKOUTS_UPDATE, ORDERS_CREATE use the crm callback above.
ORDERS_PAID uses the paid callback above; existing crm compatibility is preserved.

The production OS app's persisted, paginated Shopify GraphQL diagnostic checked at
2026-10-05T02:41:02.253945Z independently returned no CHECKOUTS_CREATE/UPDATE
subscriptions. ORDERS_CREATE and ORDERS_PAID returned the canonical URLs above,
both at 2026-04. Missing checkout registrations are real in that app's results,
not hidden by readiness failure. This is inspected production diagnostic evidence,
not a fresh direct Shopify request from local credentials.

After deployment and rerunning diagnostics, correct receiver configuration should
show HMAC CONFIGURED (or VERIFIED after a valid delivery), callback VERIFIED,
both order topics VERIFIED, both checkout topics still MISSING. Abandoned checkout
therefore remains NOT READY until separately approved registration. No Render
variable change is required to repair this route inspection exception.

Deployment verification, when approved: deploy receiver and primary OS/client code
(and the existing worker that runs the same diagnostic); GET readiness and validate
this contract; run the authenticated OS diagnostic; compare subscriptions read-only.
Do not invoke webhook registration or send emails as part of readiness verification.
