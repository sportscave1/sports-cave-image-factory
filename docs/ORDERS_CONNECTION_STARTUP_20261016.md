# Orders connections and startup — 16 October 2026

Based on production `5c9755441a3a7fafea6c150e5f359173e432d22a`, including the
concurrent V18 release. Deployment is explicitly authorised in this task.

## Measured cause

Read-only production profiling on 560 orders (latest 50: 126 joined records,
64 displayed units) reproduced browser reloads of 11.118, 11.344 and 11.915 s.
Backend medians over 10 samples: latest 50 2860 ms, search 2001 ms, visibility
marker 1276 ms, badge aggregate 1361 ms, PSD revision lookup 1284 ms, parallel
display preparation 1280 ms. Account validation separately measured a median
998 ms (10 samples). Queries themselves were already optimised in the preceding
release; fresh transport setup still cost roughly one second per operation.
Startup logs show imports/sidebar setup in milliseconds, rather than a large
import bottleneck. Browser totals also include network, Streamlit result polling
and rendering; backend timings alone do not represent a full page load.

## Targeted changes

- Reuse connections exclusively per read operation through bounded Psycopg pools.
  Each configuration retains one warm transport, grows to at most three, permits
  at most eight waiters, and rotates transports after five minutes. Orders and
  account validation retain separate timeout configurations. No row, identity,
  permission or order-status cache is added.
- Autocommit SELECTs avoid redundant BEGIN/ROLLBACK network round trips. Existing
  write/schema/edition connections and transaction boundaries remain unchanged.
- Preserve request cancellation and the single stale-transport retry; discard
  timed-out/broken transports. Watchdogs capture their own lease and finish or
  discard it before reuse, preventing cancellation of a subsequent borrower.
  Account reads use the same bounded mechanism with their four-second deadline.
- Start transport creation in background pool workers during established server
  startup, after existing migrations/readiness work. No user/order lookup or new
  recurring poll is added. Optional warming cannot fail app startup.
- PSD revision checks still run on every read and reload mappings on revision
  changes. Only the read transport changes; attachment/audit writes are untouched.

No production Orders UI, refund projection, webhook/reconciliation policy,
fulfilment rules, edition allocation/history/numbering, certificate records or
Shopify metafield write paths are changed. The V18 release is preserved.

## Verification

118 focused read-pool, authentication, Orders, refund, badge, search/bounded-reader,
deadline and PSD checks pass. Webhook health checks pass separately. The broader
account UI suite has five pre-existing UI/source-contract failures unrelated to
the modified read path; focused security freshness/revocation checks pass.
The PSD AST-only fixture now injects the display-resource helper added by the
previous release, preserving its original one-lookup/multiple-product assertions.

Production baseline, post-deployment measurements, exact revision and protected
record digests are retained in the task's external Studio release evidence.
The read-only profiler rejects write SQL and external HTTP calls. Its account
phase bypasses schema creation only inside the benchmark, never normal auth.
