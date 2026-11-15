# Supabase egress and repeated-read audit

Audit date: 2026-09-03 (Australia/Sydney)

This audit is based on repository inspection and local mocked tests. No production
database connection was made, so row counts and byte estimates are formulas or
upper bounds rather than Supabase billing measurements.

## Ranked read surface

| Priority | Area | Current read shape and trigger | Estimated waste | Safe action |
|---|---|---|---|---|
| P0 | Ads Intelligence | Every Streamlit rerun reads four insight datasets, each capped at 5,000 rows. The former `i.*` projection included each row's `raw` JSON. Product opportunities also repeated the same 500-row grouped mapping query already loaded by the page. | Potentially the largest per-render transfer: up to 20,000 insight rows. At an average raw JSON size of `R`, removing it saves up to `20,000 × R` bytes per full render. One grouped mapping query per render was redundant. | Implemented: preserve all typed columns but omit unused `raw`; reuse the already-loaded mapping rows. |
| P0 | SEO workspace editor routes | Keywords, opportunities, mapping and blog routes load one complete `seo_workspace_state.payload` JSON document. The process cache lasted only 5 seconds, so unrelated reruns after that interval transferred the whole document again. | Sixfold avoidable read frequency during an actively edited session when reruns are more than five seconds apart. Each avoided read saves one whole workspace JSON payload. | Implemented: 30-second process-local cache. Saves immediately refresh that cache. |
| P0 | Orders live visibility watcher | An open Orders page ran `orders_visibility_marker()` every 5 seconds. The query is bounded to the latest 50 orders and returns one marker row, but the frequency was 720 calls/hour or 518,400 calls/30-day month per continuously open tab. | Very high query/connection count; response egress is small because only one row returns. | Implemented: poll every 30 seconds. New rate is 120/hour or 86,400/month, an 83.3% reduction. |
| P0 | Top-bar order badge | Every open app tab requested order status every 30 seconds. The backend runs the expensive order-action aggregate and reads/consumes the user's new-order notification cursor. | 120 requests/hour or 86,400/month per continuously open tab. Multiple tabs multiply the aggregate. Count-result egress is small, but database work and connections are high. | Implemented: 60-second browser poll plus a 30-second process-local cache for the display-only aggregate. Notification consumption remains uncached. |
| P1 | Ads Intelligence status header | `ads_table_counts()` checks and counts ten tables, then makes two extra creative counts. With table-existence checks this can approach 23 small queries on every page rerun, in addition to sync status and latest-log reads. | High call count, low returned bytes. | Report only: consolidate into one read-model query or cache the display header for 30 seconds, with sync actions invalidating it. |
| P1 | Orders initial/reload snapshot | The main view is server-bounded to the latest 50 orders, but the joined result includes order and line `raw_json` plus allocation/certificate fields. It is loaded once per session/search or after a visibility change, not on every widget rerun. | Medium payload per actual reload; already bounded and state-reused. | Report only: instrument column usage before narrowing because fulfilment/allocation display semantics are sensitive. |
| P1 | Edition Ops | The complete `edition_products` catalogue is paged in batches of 1,000 and includes current allocator-derived values. It is cached for 180 seconds and hydrated into session state once. | Medium transfer when cache expires; low repeat rate due existing cache. | No change. Do not cache allocator decisions or weaken integrity reads. |
| P1 | Top-bar global search | First search focus per browser revision can read up to 300 tasks, 300 products, 300 orders, 300 accounts and 500 rows from each of five SEO JSON arrays: a 3,700-row upper bound. It projects allowlisted fields and is then reused in the browser. | Medium one-time payload; not polling. | Report only: add a short permission-scoped server cache or incremental search endpoint after measuring actual index size. |
| P1 | SEO import progress | The visible historical-import fragment polls combined Phase 3/4 status every 15 seconds. | 240 polls/hour while that fragment remains open; small rows, potentially repeated connection overhead. | Report only: poll only while a run is queued/running or back off when idle. |
| P1 | Auth revalidation | Every authenticated session revalidates at 30 seconds. The current path calls account preparation (which reads the first admin and permissions) and then the current user and permissions: normally four small reads. | Up to 120 cycles/hour, approximately 480 small reads/hour per continuously rerunning session. | Report only: security-sensitive. Refactor preparation out of periodic revalidation only with dedicated auth regression tests. |

## Other inspected areas

- Home already uses process caches: tasks 15 seconds, activity 20 seconds,
  calendar/product reference data 300 seconds, and daily execution 15 seconds.
- Analytics routes read saved, route-specific GA4 snapshots; they do not poll
  Google. Snapshot JSON is needed for the visible report, so no projection was
  changed.
- Reporting renders several read-only sections on every rerun. It is restricted
  to the reporting owner, but lazy expanders and a per-render request context are
  worthwhile future work.
- Social Media loads only the selected workspace view and most history queries
  are limited (normally 15, capped at 50). No global cache was added because
  staff collaboration freshness needs a dedicated policy.
- Fulfilment/Prodigi readers use bounded page/query helpers in the current UI.
  Allocation and dispatch reads were deliberately left unchanged.
- Product Uploads and Design Studio primarily use the local operational store and
  explicit actions; no always-on Supabase poll was found.
- Notifications load only when opened. Their audit query was narrowed from the
  complete audit row (`to_jsonb(activity)`) to the six fields the top bar uses.
- The planner status endpoint polls every 30 seconds and performs timer
  reconciliation before reading the active timer. Because reconciliation can
  write and enforces timing rules, it is classified high risk and was untouched.

## Storage

No Supabase Storage client, `storage/v1` download, signed Supabase URL, or bucket
access was found. Certificates/assets use Cloudflare R2. Supabase database rows
store R2 references, so the large PDF/image bytes are not Supabase Storage egress.

## Cache policy implemented

| Cache | Location | TTL | Invalidation/freshness | Why stale display is safe |
|---|---|---:|---|---|
| Top-bar order aggregate | Web-process memory | 30 seconds | Explicit clear helper plus natural TTL; operational writes do not use this value | It only paints a badge. Allocation and fulfilment decisions query their authoritative paths. |
| SEO workspace state | Existing `PostgresSEOStore` process cache | 30 seconds | Every `save()` replaces the cache immediately; other workers converge within 30 seconds | It supplies editor display state, not transaction/allocation decisions. |
| Orders marker | Browser/Streamlit fragment interval | 30 seconds | Next marker poll detects source changes | It only decides when to refresh the visible table. Writes and sync actions are unchanged. |

## Deferred, higher-risk opportunities

1. Replace the Ads status header's table-by-table count loop with one reviewed SQL
   statement or a small precomputed read model.
2. Add one per-render read context to Reporting so sections reuse identical daily
   sheet/history reads; then lazy-load archive and delivery detail expanders.
3. Instrument Orders joined-row serialized size before removing any `raw_json`
   field. Do not guess because current display fallbacks use JSON attributes.
4. Make SEO progress polling state-aware (fast while active, stopped/backed off
   while idle).
5. Review auth revalidation separately; do not trade account revocation safety for
   lower query counts.
6. Consider database indexes only in a migration review. No index was created by
   this audit.
