# Orders speed — Phase 3, 22 November 2026

## Changes

Companion 1.7.35 opens a paired notification channel to the existing canonical OS service. It is a level-triggered long poll, not a supplier-action endpoint. A single aggregate over committed order mirrors, allocations, Ready JPG jobs and actionable preparation states produces an opaque SHA256 cursor. No raw order, artwork, customer data or supplier URL is returned.

All listeners share a snapshot for two seconds, normally detecting committed readiness within roughly two seconds plus network/scheduling time. Requests wait at most 20 seconds, with no database connection held during the wait; the extension aborts at 25 seconds to stay below the browser's 30-second fetch limit. At most two listeners and one short snapshot read are admitted per process. The read-only production EXPLAIN ANALYZE took 3.685 ms on 22 November; this is query execution time, not total order preparation time.

The cursor derives from durable application tables, so it survives server restarts and includes changes committed while the browser was asleep. Companion stores it only after the guarded queue handles the hint. Failed HTTP requests/ticks leave it replayable. Reconnects back off; malformed notifications, revoked pairing, disabled service and duplicate listeners cannot issue native actions. Pair rotation clears the cursor and old credentials cannot acknowledge new pairing work.

The notification loop defers during native work and shares the existing Orders running guard. Heartbeats and Preparing JPG progress writes are excluded from readiness, preventing self-triggering loops while rendering. The independent 30-second alarm, persisted uncertain-Save receipt and all existing permits, exact mappings, QA, grouped submission and countdown settings are unchanged. No new permissions, schema, service, webhook subscription or production credentials are required.

## Verification

Synthetic tests cover committed arrivals/allocation/JPG readiness/Reset, rollback, cache reuse, no open transaction while waiting, cursor restart/replay, authentication, invalid instructions/cursors, listener bounds, deadline/cancellation, concurrent native stages, credential rotation, disabled service and retry backoff. Extension distribution includes the new imported script. Server health, notification requests and companion reload must be checked after deployment. No existing submitted customer order should be reset or paid for to manufacture acceptance.

## Remaining scope

This reduces idle pickup delay after state has committed. It does not remove rendering time, supplier response time or existing admission gates, and is not a promise of instantaneous end-to-end fulfilment. The next phase is an incremental feed for new Orders rows that preserves table search, selection and scroll. Initial JPG preparation and separate-order merge coordinator fencing remain unchanged as documented in Phase 2.
