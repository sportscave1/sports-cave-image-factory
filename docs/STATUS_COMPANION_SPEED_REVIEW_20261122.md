# Ads, Uploads and Designs: status and companion speed review

22 November 2026, Australia/Sydney. Local audit; no deployment or provider writes.

## Phase 3 implementation — browser monitoring candidate

Profiled the actual extension composer in real Chromium with 100 earlier synthetic assistant turns and latest responses of 32,768 and 262,144 characters. Each size ran three matched trials, each with one cold observation followed by 100 repeated observations. Baseline source is the task's exact base commit `7869c2633854bff6f3a8fec58ded9c9b4e4122aa`; the exported candidate hash is in the evidence manifest. Browser timers were controlled so the experiment measures explicit progress reads, not background wall-clock scheduling or provider time.

| Latest response | Baseline samples: 100 repeated reads | Candidate samples | Median reduction |
|---|---|---|---:|
| 32,768 characters | 17 / 16 / 16 ms | 2 / 3 / 2 ms | 87.5% |
| 262,144 characters | 191 / 122 / 119 ms | 10 / 9 / 10 ms | 91.8% |

The changed path reuses only analysis of identical response text. Every observation still queries the latest assistant turn, reads its current rendered text, inspects the generation indicator and checks visible alerts. A changed response, generation state, alert or conversation URL invalidates the analysis immediately. The original blocker rules, truncated diagnostic output, activity hash and finished/pending distinctions are preserved. Results are copied before returning so callers cannot corrupt later observations.

The cache holds at most one response of up to 1,048,576 UTF-16 code units (roughly up to 2 MiB of text storage, excluding engine overhead), plus a bounded alert and small result. Larger responses are processed without retaining an analysis entry. No conversation history or DOM node is retained. Cold/changed text still gets a full analysis; the measured gain applies to repeated unchanged observations. At 262,144 characters, the final matched medians correspond to about 1.22 ms/read before and 0.10 ms/read after. This is a browser bookkeeping improvement, not faster image generation, transfer, publication or a guaranteed production CPU reduction.

Design/upload watchers now replace an existing watcher of the same type instead of accumulating intervals. Their interval, two-hour expiry and pagehide listener are removed together after the existing blocker handoff, expiry or actual navigation. Back/forward-cache pagehide events preserve monitoring for restoration. Hidden tabs remain monitored; there is no document-visibility pause. The existing 1.5-second design and 3.5-second upload cadences and two matching design observations remain unchanged. A normal finished response alone still does not imply verified delivery or trigger early shutdown.

The profile identified repeated regex/hash work as a safe optimisation target. A MutationObserver and faster DOM scan were deferred: this patch preserves live DOM reads and avoids new observer/debounce edge cases. No UI styles, controls, focus handling, scrolling, percentage semantics or accessible announcements were changed.

Validation: **44 Node checks passed, none skipped**, including differential baseline/candidate results for Uploads, Designs and Ads; streaming transitions; visible/hidden/replaced alerts; navigation; oversized responses; mutable caller results; single watcher replacement; hidden-tab blocker detection; two-observation gating; handoff/expiry teardown; and bfcache retention. Real Chromium baseline/candidate progress objects matched in all profiling trials. Earlier Phase 1/2 backend checks remain recorded separately; they were not rerun or claimed as fresh Phase 3 backend evidence because this phase changes only composer monitoring.

Final runtime/browser evidence: `output/status-speed-audit/sc-status-phase1-c8ce11a4e7/phase3-browser.json` and its `manifest.json`; Node output: `output/status-speed-audit/phase3-all-node.log`. Reproduce with the provisioned release interpreter and `-B scripts/verify_status_phase1.py --phase3-only`, plus the ten Node suites recorded in Studio evidence. Studio static/security, topology and diff checks passed. The code remains a local, uncommitted candidate. Actual installed-extension, long-duration memory and real provider/device acceptance remain required before any release.

## Phase 2 implementation — local candidate

Added a versioned header-only display representation and account-scoped conditional responses. The normal companion-page/status contract and all control/write endpoints retain their existing behaviour. The compact representation retains displayed labels, diagnostics, progress estimates, job/order identity, links, cancellation/restart/control flags, action revisions, online state, queue counts and freshness. Header-unused targeting, country/sport, file paths, prompts and creation timestamps are excluded. Underlying records and their full companion-page views are preserved.

The browser validates only an already accepted snapshot for the same account scope, UI revision and receipt URL. A matching response returns 304 without JSON decoding or DOM updates. Control actions invalidate the accepted-view marker and request a full representation; errors clear the validator so recovery restores disabled controls and stale indicators. An unexpected 304 without an accepted view is retryable. Authentication and exact-receipt access checks execute before every conditional response. Validators include account/session/permission scope and the complete compact representation, including freshness state and checked-at timestamp.

No TTL or polling cadence changed. Header snapshots use **2 seconds**, while the separate companion-page display cache uses **10 seconds**; the original audit conflated these paths. This candidate keeps both. Conditional responses can save bytes only while the full accepted snapshot, including checked-at time, is unchanged. A fresh verification timestamp produces a new body even if job labels match; no freshness is hidden. There is no claim of fewer requests, less source SQL or reduced provider work.

Matched browser fixture (same source baseline commit, five tabs, 35 reads per variant): baseline response bodies totalled **20,870 bytes**, candidate **11,035 bytes** (**47.1% fewer body bytes**), including 15 unchanged responses with empty bodies. Header screenshots matched exactly on all five pages. All three cards were asserted after each changed checkpoint. This is a deterministic synthetic cache-stability scenario, not a forecast of production hit rate; HTTP header overhead and transport compression are excluded.

The deliberately targeting-heavy fixture encoded **138,602 bytes before / 1,723 after** (98.8% smaller). Three initial encode samples were approximately 0.80–0.89 ms before and 0.036–0.055 ms for candidate projection plus encoding. This stress case repeats synthetic targeting records and does not establish normal production payload sizes. It shows that irrelevant targeting volume no longer determines header payload size.

Browser latency is **not claimed improved**. Preliminary matched runs showed warm medians around 12.61 ms baseline / 18.23 ms candidate, with maxima 35.67 / 43.89 ms. First-import costs in the routed Python fixture were subsequently excluded to match the actual route's already-loaded authentication/cache dependencies. The final matched run recorded warm medians **10.78 ms baseline / 10.91 ms candidate**, maxima **33.57/43.73 ms**, and cold medians **76.44/64.17 ms**. These variable samples do not establish a speedup or a release-ready absence of latency regression. Compare representative network/device workloads before release, especially where added validator header/hash overhead may outweigh very small body savings. Keep this as a local candidate until end-to-end latency and production hit-rate evidence support release.

Regression coverage now includes projection immutability and retained UI/action fields; unchanged/fresh/stale representations; account/session/permission validator separation; access denial before 304; hidden tabs; single flight; full action refresh; account switches; and invalid-304 recovery. The offline runner exports the three selected runtime files with per-file hashes, in addition to Phase 1 tests, and runs the matched browser comparison. No cross-tab leader coordination, freshness extension or speculative cache rewrite was introduced.

Final Phase 2 evidence: `output/status-speed-audit/sc-status-phase1-a7820f10a1/` (manifest, **190 passing Python tests plus two subtests, no skips**, browser comparison with five matching screenshot hashes, and queue baseline). Node: **39 passed, no skips**, in `output/status-speed-audit/phase2-all-node.log`. Studio syntax/security checks, topology validation and diff checks passed. No unused-import candidates were found in the new payload module. Files remain uncommitted in the owned task; no publication or deployment occurred.

## Phase 1 implementation — latest result

Phase 1's local fixture repairs and controlled baselines are implemented. Application runtime behaviour is unchanged. The original audit below is retained as the before-state; its failed/skipped checks have since been repaired and rerun.

- Design stage-5 semantics were resolved from the authoritative queue labels and commit `1da7ea222550f8d68123e330d3debf984d970fed`: an undelivered job is pending and does not block the next queue job; a delivered file awaiting review is complete. Tests now assert pending with zero, non-estimated progress and preserved diagnostic detail.
- The hanging design companion fixture invoked the first registered extension message listener. New modules register other listeners first. The fixture now dispatches to the listener that accepts the permit, fails explicitly if none accepts, and exercises the real worker's existing identity checks. All 12 design-companion scenarios pass without timeouts.
- The notification fixture now supplies the interval and DOM insertion APIs used by the current header. Its assertions match the intentional separation of completed Uploads from Ads progress and the current delayed-status wording. Existing dismissal, stale read, action, queue and recovery assertions still execute.
- Historical image parity uses the exact original source at `58569c66`, SHA-256 `464680d788e3eb78b9675e21b4c16a67fea01acc630a5318df4d9da5d0d66b01`. The offline fixture rejects a substituted source. No Git executable, network or production checkout is needed inside the test container.
- Queue tests have an explicit opt-in native PostgreSQL adapter. It refuses to run outside the network-isolated preview environment, uses a unique disposable database per fixture, and drops only that synthetic database. The normal PGlite path remains available. No real database URL or credentials are accepted by the adapter.
- Browser tests can select installed Chromium through `STATUS_TEST_BROWSER_CHANNEL` while retaining their default Edge channel.

Controlled five-tab Chromium status delivery: five cold navigations, three updates per tab (15 warm samples), all three cards asserted after each update. First observed cold median/max: **82.34/98.29 ms**; warm all-three-card median/max: **8.26/14.36 ms**. The final reproducible run recorded **55.40/80.86 ms cold** and **7.32/11.36 ms warm**; variation between runs is not an implementation gain. Twenty synthetic status responses totalled 11,855 JSON bytes. Each of five pages retained 500 DOM nodes and approximately 2.40–2.43 MB of JS heap at the final sample; no long-task entries were observed. These are bounded samples, not total browser RSS, a memory-leak soak, CPU profiling or a production latency guarantee. Cold navigation includes browser rendering; warm timing includes the test driver's round trip and assertion overhead, so it is not an isolated paint-time measurement. HTTP is fulfilled by the fixture rather than a real application API.

The first expanded Python run passed 186 tests, zero skips, plus two subtests, including database-backed actions, queue concurrency/recovery, image pixel/profile/alpha parity and four real header browser scenarios. The final reproducible run **passed 187 tests with zero skips, plus two subtests**, including historical-source tamper rejection. Node coverage: **39 passed, zero failed/skipped**, covering the repaired fixtures, deduplication, scope isolation, deadlines, exact handoff ownership, progress classification, single-flight polling, hidden-document gating and teardown.

Native PostgreSQL upload-queue baseline (three samples, synthetic final PSD metadata): durable acknowledgement **168.72 ms cold**, then **4.24/4.33 ms warm**, four explicitly executed SQL statements per enqueue. Scoped display reads were **13.67/5.85/5.30 ms**, five explicitly executed SQL statements each, with JSON sizes **390/753/1,116 bytes** as the fixture grew from one to three jobs. Repeated enqueue returned the same identity; another staff identity saw no rows. Statement counts exclude implicit transaction protocol messages. These are direct Python function timings, not network HTTP measurements. The cold acknowledgement exceeds the proposed 100 ms budget; investigate lazy imports, connection acquisition and first-use database costs separately before selecting an optimisation. Three samples identify a candidate for profiling, not a dependable tail-latency distribution.

Reproduce Python/browser/queue checks with the provisioned release interpreter and `-B scripts/verify_status_phase1.py`. It exports the approved commit plus selected test changes, records base SHA, per-test hashes, pinned image ID and historical baseline digest, rejects skipped contracts, then removes its isolated container. The final complete evidence is `output/status-speed-audit/sc-status-phase1-f7a52d04bc/` (contracts, browser baseline, queue baseline and manifest). Earlier directories retain an incomplete packaging run and a rejected queue fixture as diagnostic history; use the final directory for conclusions. Node results are in `output/status-speed-audit/phase1-all-node.log`. Reproduce with `node --test` and these test files: `test_upload_progress_notifications.cjs`, `test_morning_design_companion.cjs`, `test_companion_status_polling.cjs`, `test_top_bar_requests.cjs`, `test_companion_message_deadlines.cjs`, `test_ads_handoff_status.cjs`, `test_companion_progress.cjs`, `test_upload_companion_progress.cjs`, `test_upload_companion_progress_existing.cjs` (all under `tests/`).

Still required for the full Phase 1 end-to-end baseline: actual desktop companion/Photoshop and provider generation, queue wait, transfer and durable verification timings; real application HTTP/database statement counts and connection acquisition timings; browser CPU/total RSS and a longer five-tab background/offline soak. The current fixtures validate these workflows' contracts but do not measure real external work. Provider writes remain excluded from local testing. Phase 2 optimisations should be selected only after identifying a bottleneck in the relevant layer. No speed improvement or production readiness claim is made by these test-only changes.

## Result

The shared display infrastructure is fast under synthetic load, with bounded refresh concurrency and successful recovery from injected read failures. The real header passes four Chromium interaction/layout contracts. This does **not** establish that all production companions or end-to-end generation/upload operations are fast and reliable. Test inconsistencies, skipped database checks and unmeasured browser/production costs prevent an all-clear.

Task `20261121-825b78af`, owner `codex-status-speed-20261122`. Tested approved source: `7869c2633854bff6f3a8fec58ded9c9b4e4122aa`. GitHub main observed at `6ae4cc79944d94ce0e0800a3488ce5d6c90e241d`. Selected shared header, cache, ad progress, upload acknowledgement and composer sources are identical between these revisions. This is source parity, not deployment verification. Subsequent Orders/Prodigi extension changes are outside this audit's measured scope.

## Measurements

Existing `benchmark_companion_display.py`, 20 concurrent readers, 1,000 requests per size, 50-row pages:

| Synthetic jobs | Index build | Read p50 | Read p95 | Maximum JSON page | Encoded index rows |
|---|---:|---:|---:|---:|---:|
| 100 | 1.27 ms | 5.39 ms | 6.05 ms | 8,047 B | 15,892 B |
| 1,000 | 10.15 ms | 5.40 ms | 5.94 ms | 8,096 B | 159,893 B |
| 10,000 | 96.60 ms | 5.56 ms | 7.43 ms | 8,144 B | 1,608,894 B |

These are indexed in-process reads, not HTTP/browser timings. Encoded row bytes exclude SQLite indexes, Python objects and process overhead; they are not RSS. Cached page selection issues zero PostgreSQL queries by construction; source refresh query costs were not measured.

Existing 60-second synthetic soak: 10,000 jobs, 20 readers, 22,548 reads, p50 0.12 ms, p95 35.36 ms, 80 refreshes, peak concurrent refreshes **one**, 11,627 stale reads and 20 initial cold reads. Every seventh loader call deliberately failed. Saved status remained readable; this is bounded local recovery evidence, not a long-running production reliability guarantee.

## Coverage and failures

| Surface | Evidence | Remaining gap |
|---|---|---|
| Shared Ads/Uploads/Designs header | Four real Chromium tests passed: rotation, responsive cards/search overlay, exact publish receipt, design defer/cancel | Desktop/mobile production timing, CPU, memory and multi-tab soak |
| Ad posting progress | Existing mocked UI contracts ran in isolated suite; confirmed-success, identity restoration and draft preservation covered | Real provider latency and large campaign snapshots |
| Upload generation acknowledgement and background jobs | Included in isolated suite | Full PSD/mockup/transfer/browser workflow timings |
| Design deletion/display recovery | Included in isolated suite; nonblocking cache contracts | Production queue/query plans and cold provider lookup costs |
| Transfer pacing/control | Real loopback receiver checks included; reduced budget and competing transfers exercised | WAN, actual desktop companion, Photoshop and upstream storage |
| ChatGPT composer progress | 16 Node subtests passed across progress/existing-progress/companion-progress files | Large real conversation DOM and extension lifecycle profiling |

Combined Python suite: **61 passed, 4 failed, 22 skipped, 2 subtests passed**. Do not count skipped tests as coverage. Two failures are explicit disagreement between design-header tests expecting `failed` and implementation returning `pending` for stage 5 without a verified file; delivered stage-5 designs remain complete. Confirm the intended business state before changing code or assertions. Two image-parity tests could not run because the isolated source archive has no Git executable/history for `58569c66:product_upload_artwork.py`; they are environmental failures, not proven pixel regressions.

The upload-notification Node fixture fails because its fake `parentWindow` omits `setInterval` now used by design rotation. Repair the fixture and rerun all notification assertions before drawing conclusions about notification behaviour. Additional bounded Node runs passed shared GET deduplication/account isolation, four message-deadline tests, four ad-handoff tests, and polling single-flight/timeout/visibility/teardown assertions. The morning-design companion script exceeded its 12-second limit with no result; it is unresolved. The edition-status performance script could not start because host Node Playwright was unavailable. An initial combined Node runner was stopped after failing to exit; use bounded per-file runs when reproducing. A process timeout is not a passing assertion.

Isolation: existing preview image `sha256:b1857ed93a713747038020d59353d04ccab683b126c0b5dd782368dc6054ed17`, network none, read-only root, non-root, dropped capabilities, no host mounts or credentials, 2 CPUs/2 GB, tmpfs source copy. Pure pytest dependencies were copied locally because the image lacked pytest. Header browser tests used bundled Chromium in place of their unavailable hardcoded Edge channel; the adaptation was container-only. No host application server was started.

## What is already lightweight

- Header polling already switches between 2-second active and 15-second idle cadence, deduplicates reads and rejects stale scope responses. Identical status JSON avoids rebuilding unchanged DOM.
- The companion-page display cache has two refresh workers, 32 lanes, 10-second TTL, 5-second retry and explicit stale/unavailable states. The header has its own two-worker, 32-lane cache with a 2-second TTL and 3-second retry. Display snapshots never authorize writes.
- Read-only companion connections apply 2.5-second statement and 0.5-second lock limits plus a 3-second cancellation watchdog after acquisition. Connection acquisition itself can still take the factory's existing 8-second timeout.
- Queue source reads are capped at 100; header cards show ten. Transfer budgets and exact source/output preservation already have dedicated regression coverage.
- Design rotation runs every five seconds, respects hidden documents and reduced-motion preference. Ad completion requires verified ad objects rather than elapsed-time percentages.

## Phased plan

### Phase 1 — Establish trustworthy coverage and end-to-end baselines

Resolve stage-5 state semantics with the design workflow owner. Repair notification timer mocks. Supply exact historical image sources to the offline parity fixture without adding credentials or network. Provision disposable database fixtures for skipped ad/upload/queue checks. Run all three workflows with populated queues, failures and reconnects; record at least three samples tied to exact SHAs.

Measure separately: click-to-acknowledgement, queue wait, provider generation, transfer, durable verification and status delivery. Also capture HTTP requests/bytes per minute, database statements, browser long tasks and total memory. Cover cold/warm states, hidden tabs, offline recovery and five open tabs. Existing transfer bandwidth is not a generation benchmark.

Proposed acceptance budgets, not achieved production measurements: acknowledgement p95 under 100 ms; cached status HTTP p95 under 250 ms; status paint under 16 ms; status payload under 20 KB; no duplicate job/write on retry; no browser task over 50 ms caused by status updates. A verified terminal result should appear within the agreed active polling window plus read latency. Separate provider work from UI overhead.

### Phase 2 — Reduce redundant status work

Profile the 2-second browser polling against the 10-second snapshot freshness window. Multiple requests can return the same saved snapshot. Introduce a small, versioned display DTO containing only visible fields, checked-at time, freshness, job identity and revision. Keep prompts, image bytes, large results and history out of polling responses. Use an unchanged-version response where compatible, preserving access checks and explicit stale state.

Keep one in-flight read per scope, bounded backoff with jitter on errors, visibility-aware polling and immediate refresh after confirmed control actions. Consider shared read coordination across tabs only after account-change/logout isolation tests. Do not slow active updates or extend freshness silently. Expected benefit: fewer bytes, repeated decoding and DOM work; savings need measurement.

### Phase 3 — Improve extension/browser responsiveness

`composer.js` observes design responses every 1.5 seconds and upload failures every 3.5 seconds, with a two-hour expiry. It reads response `innerText`; cost on large conversations is unmeasured. Profile first, then consider a scoped MutationObserver with debounce and a bounded fallback timer. Observe the owned response only, disconnect on terminal handoff/navigation, and retain stable double-observation verification. Background generation still needs monitoring even when a tab is hidden.

Patch only changed labels/progress values. Preserve focus, scroll and expanded controls, reduced motion and accessible status announcements. Label estimated progress explicitly; keep unverified completion pending and errors actionable. Avoid noisy popups for unchanged historical failures.

### Phase 4 — Tighten backend reliability and resource budgets

Measure connection acquisition separately from query execution; the watchdog starts after acquisition. Examine p95/p99 under a slow or exhausted pool. Reserve bounded read capacity without starving control writes. Profile snapshot deepcopy/JSON work performed while holding the shared cache lock; the current soak passes, so avoid speculative rewriting. If measured contention warrants change, publish immutable snapshots and copy bounded visible rows outside the lock with invalidation/concurrency tests.

Verify indexes and execution plans on synthetic populated source queues before proposing migrations. Preserve pagination, recovery, access control, moderation and all retained operational history. Table size alone does not justify deletion. Exercise pause/resume/cancel/reconnect, expired leases, duplicate replies and process restarts; confirm durable job identity and exactly one active owner.

### Phase 5 — Professional acceptance and controlled release

Run matched before/after tests and browser traces at phone/tablet/desktop widths, keyboard-only and reduced motion. Confirm unchanged job selection, actions and outputs. Run a longer soak with slow reads and injected failures; compare memory after warmup and repeated mount/unmount. Require zero leaked polling/listener instances and zero cross-account data.

Publish a compact scorecard for each of Ads, Uploads and Designs. Release only after failed/skipped critical contracts are resolved and measured gains preserve behaviour. This request has produced a local audit; no commit, push, production configuration or deployment was performed.

## Evidence

Task-local `output/status-speed-audit/` contains benchmark/soak JSON, Python and browser logs, and bounded Node results. Existing scripts used: `scripts/benchmark_companion_display.py`, `scripts/soak_companion_display.py`; test files are named in the retained logs. These logs remain local and contain synthetic data only. No production speed claim or implementation gain is asserted.
