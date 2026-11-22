# Orders responsiveness and sequential item preparation — 2026-11-22

## Incident evidence

SC3532 Shopify triggered 05:24:38.333Z; signed paid webhook received 05:24:40.099Z (1.77s). Subsequent receipt/CRM persistence reported Supabase transaction pool checkout timeouts; Shopify retried the same event. Keep the existing fast signed receiver and the already-deployed bounded companion transactions (cb6df049). Do not weaken durable acknowledgements, change subscriptions, or bypass CRM conversion protection.

Both SC3532 jobs retained the exact same artwork output and allocation. Production read-only resolve comparison showed only `shipping` changed: a display address suffix after `|` disappeared. Source matching now ignores only that redundant suffix; full recipient, service, mapping, artwork bytes/job, edition and all other snapshot fields remain pinned. Existing fingerprints are still validated against their stored snapshots.

## Phase 1

- Product selection commits directly to Awaiting browser upload. Upload claims precede another product selection. One worker-owned exact-order tab is reused.
- A sequential-capable companion checks the saved item immediately, before the next item. Successful item QA waits for the rest of the order. A final fresh combined QA batch and the existing one-order submission fence are still required.
- Bounded chains of up to six successful stages remove the alarm gap between actions. Any review/error stops the chain. No parallel native writes or blind Save retries.
- New JPG admission also runs independently of long package/catalogue work when the companion polls. Background loop admission precedes package draining.
- Fulfilment admission throttle: 60s to 15s. Orders' existing read-only changed-marker check: 30s to 5s. Reload rows only on actual marker changes; row progress remains incremental.
- Countdown preferences, payment and production settings are untouched.

## Next phases

1. Durable arrival-to-companion notification with replay/fallback polling, rather than relying on the idle 30s browser alarm. Measure event receipt → mirror → allocation → JPG → native pickup.
2. Isolate short ingress DB work from long external jobs and monitor pool checkout/lock duration. A durable inbox must commit before acknowledging Shopify; do not merely return 200 early.
3. Serve new Orders rows as cursor-based deltas using the same authenticated feed; preserve search, selection, drawer and scrolling, and avoid full Streamlit reruns.

Do not claim zero-delay or guaranteed supplier success. Quality/identity mismatches and uncertain writes must remain visible and stop submission.
