# Marketplace photo delivery repair

Owned task 20261123-47000a89, codex-speed-20261124-marketplace.
Baseline/current main: 333d9a9d481bb96c0c84fb42bbfa80a8a7f26d35.

## Evidence and selection

Fresh route/source/history review ranks Marketplace ahead of Orders (active owner
QA/recent recovery), onboarding audit growth (not proven redundant), newly released
Website/collection performance, unchanged SEO storage, and historical cold enqueue.
Companion/status is completed and on cooldown. Full ranking is retained in the
automation selection ledger. The approved Studio base now matches current main;
this run did not change that registry pointer.

The populated baseline uses actual Marketplace routes, PostgreSQL and sandboxed
Chromium in the reviewed network-isolated Docker preview. There are 24 synthetic
listings, four generated photographs each, and a deliberately controlled 120ms
Dropbox download delay. All twelve browse cards become usable before opening the
first item and selecting its second photo. Baseline three cold samples:
783.289/698.840/638.928ms; warm:617.115/599.897/677.611ms. Every pass performs 16
provider reads and 18 DB connections. Eight concurrent identical image requests
perform eight provider reads. Provider service time sums ~1922ms per workflow,
overlapping across requests; DB connection cost is separately instrumented.
These are synthetic timings, not measured live Dropbox latency. Browser work,
loopback transport, rendering, SQL and verification remain in total workflow time.

Root cause: each photo request re-downloads the same revision-pinned, SHA-verified
Dropbox bytes, including browse-to-detail and repeat visits. Browser no-store is
intentional: listing withdrawal must continue denying access immediately.

## Phases and acceptance

1. Completed: populated baseline, route/source/reference/ownership review and four
   desktop/mobile screenshots, search/sort/pagination/privacy/concurrent reads.
2. Implement a process-local bounded LRU for verified *public* photos only, keyed
   by listing/index and complete immutable receipt. Continue querying approval
   first on every request. Private moderation/manifest/video and legacy DB images
   retain their existing paths. No public URLs, disk writes, data retention changes
   or browser cache introduced. Cap retained bytes8MiB, entries64, in-flight8;
   coalesce identical loads, propagate failures, bound waits, never cache errors.
3. Repeat >=3 cold/warm browser samples. Acceptance: warm median >=20% faster,
   zero warm provider reads for the same populated workflow, no cold regression
   beyond15%, eight concurrent same-photo reads -> one provider read. Exact bytes,
   desktop/mobile screenshot hashes, search/sort/page, anonymous/private access,
   withdrawal, pending, DB failure, revision changes, corrupt data, eviction,
   provider timeout/retry and bounded concurrency must pass. UI remains unchanged.
   Photo delivery has no pause/resume job or mount watcher; test cancellation at
   the coalesced wait boundary and navigation/revisit instead.
4. Focused Python/Node tests and code review; exact committed candidate preview,
   current-main fence, normal speed_release validation/push and live read-only
   GitHub/Render/route verification. Preserve supporting services/suspended cron.

## Second measured implementation phase

The cache-only draft removed all warm provider reads but did not meet the20%
workflow target (candidate3 warm median465.027ms vs533.928ms baseline5). Provider
work was no longer the remaining critical path: public reads opened18 fresh DB
connections per workflow; measured connection acquisition/service time varied
40–488ms in the1CPU preview. The final implementation additionally reuses the
existing database_read_pool for public listing/catalogue/photo reads only. Its
existing3connections/8waiters/8second timeout and no-record-caching semantics are
unchanged. Private moderation/transactions still use their existing connection
path. No dependency, pool configuration or shared module changed.

Harness corrections were applied equally to baseline and candidate: wait for all
required images, drain late lazy requests between samples, leave ordinary browser
static-asset caching enabled. Baseline reconstructs the exact pre-repair store
from its Git object; manifest and harness hashes identify both sources. Initial
unsuccessful fixtures and below-budget draft runs remain local evidence and do
not establish release readiness.

Final draft candidate4 vsbaseline6 (same harness): warm535.351->281.165ms median,
254.186ms/47.48% faster; cold559.740->500.718ms median. Warm photo provider reads
16->0 (36758->0 bytes), three tabs36->12, identical concurrent image8->1. Fresh
approval queries remain18per full workflow; final real pool served276 acquisitions
with3physical connections. All4 desktop/mobile PNG hashes match exactly;64-read
soak downloads0extra photos and leaves no in-flight loads. These numbers describe
synthetic workloads with controlled120ms provider delay, not a live latency claim.
Exact committed acceptance and release verification follow; the public live
catalogue is currently empty, so a populated production photo gain cannot yet be
measured without creating a real listing (not authorised as a test).

Rollback is reverting the two runtime files through the same release process;
process exit discards cached bytes. No schema or external writes need reversal.
No deletion is justified. Aggregate storage: Speed6reports/19229B, largest SEO
table254345216B unchanged; onboarding audit104415232B vs100737024B prior. Size
alone does not justify deleting operational audit/customer data. This repair
reduces provider reads without adding DB writes or persistent generated media.
