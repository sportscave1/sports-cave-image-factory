# Abandoned checkout publication diagnostic

The publish gate remains fail closed. `AutomationStore.publish()` requires a
diagnostic less than ten minutes old whose `triggers.abandoned` is `AVAILABLE`.
Enrollment and dispatch retain their existing capability checks.

Required evidence: canonical installed app identity, `read_customers`,
`read_orders`, configured webhook HMAC secret (not an Admin API token), valid
HTTPS callback configuration, and subscriptions for `CHECKOUTS_CREATE`,
`CHECKOUTS_UPDATE`, `ORDERS_CREATE`, `ORDERS_PAID`, all using API version
`2026-04` and the configured CRM callback. `ORDERS_PAID` may alternatively use
the existing orders-paid callback. Configuration does not prove that a real
production webhook signature has been accepted.

Expected callbacks come from `crm_tracking_health.callbacks()`: the
`SPORTS_CAVE_WEBHOOK_BASE_URL`, falling back to `CRM_PUBLIC_BASE_URL`, followed
by `/webhooks/shopify/crm` or `/webhooks/shopify/orders-paid`. Verify the actual
webhook host rather than substituting the primary UI host.

Web Pixel installation, customer-event verification and pixel scopes are
separate. They do not block the abandoned server trigger.

## Runtime and admin operation

The five-minute refresh already existed in `Engine.tick()` and executes after
acquiring the worker lease, before processing source events. `crm_worker.py`
calls tick every 30 seconds. This change tests that schedule, handles future
timestamps safely and refreshes at the five-minute boundary. It does not start,
deploy or enable a worker. A missing or unhealthy production worker still needs
operational attention.

Admins can open **Shopify trigger diagnostic** in the automation editor and click
**Run diagnostic**. This explicitly calls the existing verification and persists
its result. It never publishes, enrolls, backfills, registers subscriptions or
activates a pixel. Ordinary editor renders make no diagnostic Shopify call.
The summary displays each requirement, freshness, and callback/version evidence
for mismatched subscriptions. Errors contain classes rather than provider bodies.

## Connected-environment procedure

1. Run `python scripts/shopify_automation_diagnostics.py` to verify and persist
   the current result. `--inspect-only` reports without updating storage.
2. Inspect `python scripts/register_crm_webhooks.py --automation-only` before any
   repair. This tool requires `SPORTS_CAVE_WEBHOOK_BASE_URL` explicitly.
3. For proven missing topics only, verify the deployed endpoint exists and use
   the existing `--automation-only --apply` workflow. Existing different callbacks
   or versions require review; the tool does not duplicate them.
4. Rerun the diagnostic, confirm `AVAILABLE`, then publish explicitly in the UI.
5. Confirm the leased CRM worker keeps `checked_at` fresh beyond ten minutes.

This checkout has no Shopify app credentials, callback-base configuration,
webhook HMAC secret or database credentials. Inspection locally returned
`UNVERIFIED` with those exact missing/unavailable checks. Production persisted
state, actual scopes/subscriptions and the production worker cannot be assessed
from that result. No live subscription repair or production publication occurred.
