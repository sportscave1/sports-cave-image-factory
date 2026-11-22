# Supplier tracking and certificate reconciliation

The old submission worker reconciled one allocation per tick alongside new
submissions and PDF uploads. Completed certificates stopped being polled.
#SC3522 eventually completed: production was recognised at 04:32:47 UTC and its
certificate was saved at 04:33:07 UTC. Its hosted PDF returned application/pdf
with a valid PDF signature during read-only verification.

The server now runs a separate 15-second status clock, independent of artwork
processing and Edge. Each pass leases at most 20 distinct existing supplier
orders, with at most four concurrent GETs, sharing one read across numbered
units. Submitted/held orders are due every 15 seconds, production/shipping every
60 seconds. Failed requests retain the last good state and back off 60 seconds.
Terminal supplier states stop passive polling. These are polling targets, not
delivery guarantees; supplier latency and API availability still apply.
Passive tracking transactions have a one-second lock timeout and three-second
statement timeout so database contention causes a bounded retry instead of a
long-running tracking transaction. These limits do not change other workers.

The order ID and merchant reference must match the pinned QA receipt. Actual
production still runs the existing exact product/artwork/quantity/manifest
validation before scheduling a certificate. PDF work uses the existing durable
submission lease and retries independently. A confirmed saved certificate URL
is reused, never regenerated merely because shipping status changed.

Certificate remains Complete. Fulfilment shows supplier-reported In production,
Partially shipped, Shipped, Completed, On hold, Cancelled or Failed. No Delivered
claim is inferred from Shipped or Completed. The visible Orders table reads only
a batched local status snapshot every 10 seconds, including certificate-complete
units, and continues to preserve selection and scroll.

This change adds no supplier writes, payment actions, preference changes,
countdown inspection, webhooks, schema migration, service or browser permission.
It uses the existing canonical sports-cave-os deployment and existing API key.
