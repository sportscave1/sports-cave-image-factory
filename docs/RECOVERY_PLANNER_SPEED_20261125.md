# Recovery planner performance, 25 November

Daily claim: a9285637-29a5-479e-8dc2-8f78b6a65d1e.
Repair task 20261124-80cbb2c4, owner codex-speed-20261125-audit.
Integration task 20261124-d4976ef6, owner codex-speed-20261125-release.
Approved Studio base 333d9a9d; unchanged registry. Integration fast-forwarded
current GitHub main c3b0e773, then repair task fast-forwarded that integration.
Canonical Render live at diagnosis: 8aa51daa, primary dep-dc2mmvgae00c73du80lg.
The newer main commit records evidence only; inspect selected blob parity before release.

## Ranking and selection

1. Onboarding audit history: aggregate grew 104415232 to 107700224 bytes,
   estimated 28144 to 29145 rows. Code inspection found 200 prior-checkpoint
   subqueries per diagnostic request although at most 50 rows survive filtering.
   Select this independent read path for populated profiling; growth alone is
   not proof of redundant writes or grounds for deletion.
2. Orders: high staff impact, but fresh performance release plus parallel CSS
   correction and an active Prodigi QA owner. No independent new failure observed.
3. Website/Reviews: public customer impact, significant new media and list code;
   current source already includes same-day targeted performance work and evidence.
   Avoid duplicating that owner's work absent a new regression.
4. Upload queue cold enqueue: historical first-use lead remains unproven across
   independent cold processes; lower evidence confidence than repeated audit work.
5. SEO reporting storage: largest details table remains 254345216 bytes;
   snapshot remains 81428480 bytes. No proven duplicate write or safe cleanup.
6. Marketplace: yesterday's populated photo/read transport repair completed;
   cooldown until 1 December. New review dependencies inspected as distinct work.
7. Companion/status response monitoring: released 22 November; cooldown to
   29 November. Diagnostic-history SQL is a distinct unmodified read path.

Fresh discovery used speed_review.py plus recursive Git file listing, current
main history, nested component/API definitions and targeted Studio registry
inspection. This covers OS routes and background queue dependencies rather than
assuming static top-level discovery is comprehensive. Existing Marketplace
routes and public Website/Shopify theme sources remain in this repository;
no guessed external domain or provider mutation is needed for this repair.

## Phases and budgets

1. Profile actual diagnostic read model/API and populated browser interaction
   in reviewed network-none Docker with real synthetic PostgreSQL. Compare
   baseline c3b0e773 and candidate in the same container, three or more samples.
   Distinguish DB/backend from browser rendering and connection overhead. Fixture
   history is synthetic and concentrated; do not label it production distribution.
2. If justified, defer previous-checkpoint enrichment until filtering/page limit.
   Keep scan cap 200, page cap 50, cursor progression, all filters, exact audit-id
   checkpoint fence and forensic history. No cache, schema, indexes, UI or writes.
   Acceptance: repeated backend reduction and browser improvement, identical
   outputs and desktop/mobile diagnostic screenshots. Retain small/empty history
   checks to identify the extra round-trip tradeoff.
3. Verify API administrator/invalid-query denial, timeout/recovery, pagination,
   read concurrency, no durable changes, and focused existing worker-health tests.
   Status/companion lifecycle code is unchanged; no real companion is activated.
4. Commit only the focused candidate under standing scoped release authority;
   exact-commit preview, Studio and normal speed_release checks, current-main
   fence, existing Render auto-deploy and read-only live workflow verification.
   Revert selected change through normal reviewed release if behaviour regresses.

No completion or speed gain is claimed until executed evidence passes. Missing
populated live data will be stated separately from synthetic workflow evidence.


## Populated diagnosis and selected repair

The diagnostic enrichment hypothesis was REJECTED. Actual Chromium + 29,025-row
PostgreSQL history produced identical desktop/mobile diagnostic panels, but median
backend time increased about 8.3 to 10.0ms. Browser median 61.632 to 61.467ms is
noise, not a justified gain. worker_health.py is restored byte-for-byte; the
rejected scripts/evidence are retained only under ignored output, not released.

Further profiling found repeated shared-fix source reads/hashing for every
product in recovery.plan. Selected bounded source-hash reuse within EACH scan:
ContextVar isolates concurrent scans; finally releases the at-most-128 digests.
There is no cross-scan decision/hash cache. File metadata changes during the scan
invalidate a cached digest; a source changing while read aborts the scan. Every
new scan reads source bytes again, even if file mtime was restored. No full source
bytes are retained. Policy, backoff, queue admission, pause, leases, provider
verification, rows/order, fingerprints and journal remain unchanged.

Crucially, the exact performance-only recovery file hash translates to its exact
pre-change hash. Existing persisted retry budgets MUST NOT reset on this release.
Any subsequent semantic recovery edit has different bytes and hashes normally;
a regression test pins the allowed pair, requiring explicit review to change it.
The dependency source lists are unchanged. No Companion package/local install
change is required; only the server planner's hash I/O changes.

Initial populated actual native PostgreSQL evidence: 334 blocked synthetic
products and 29,003 retained audit records, five full plans before/after. Baseline
[121.390,117.515,116.916,114.758,117.345]ms; candidate
[90.108,92.831,90.167,92.936,92.005]ms: median117.345->92.005ms,
25.340ms/21.59% faster. Source reads5010->15 and bytes155650680->466485 across
five scans. This is a synthetic background planning workload, not Photoshop,
provider transfer, browser readiness or measured production distribution.

Final acceptance budget: at least15% full-plan median improvement,99% fewer
source reads, unchanged query count, exact decisions/fingerprints/order including
persisted retry exhaustion, three concurrent equal plans and five-scan soak.
Tests cover fresh-scan mutation with restored mtime, bounded caches, interrupted
reads and exception cleanup. No frontend file/asset changes. Earlier diagnostic
browser evidence is coverage of the rejected hypothesis, not visual evidence of
a new interface. Runtime UI byte parity is enforced by the focused two-module
runtime diff and existing Worker Health/queue/browser tests.

Executed initial focused checks:47 Worker Health/queue tests passed with PGlite
(no skips);59 recovery/cache tests passed before the additional sixth cache
regression. One earlier cache draft failed restored-mtime validation on Windows
and was replaced with scan-local lifetime; failures retained, not waived.
A baseline fixture initially stripped a source trailing newline and correctly
failed retry identity equality; raw git-object bytes fixed the fixture.
Final committed checks and release/live evidence remain to be recorded locally.
