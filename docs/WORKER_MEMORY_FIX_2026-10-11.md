# Worker memory investigation — local only

Service: `sports-cave-seo-worker` / `srv-d9ujm9navr4c73amurgg`.
No deployment, commit, push, plan change, production mutation, or Render topology change was performed.

## Finding and confidence

Render's event history confirms `oomKilled`, limit `512Mi`, at **2026-10-11 08:42:37.807 UTC**. The affected instance was `wl95s`, following deployment of `76e6fb4291895e8290c5402181cad8d047eb2e44`.

The most likely cause is a transient **automation-publication thumbnail burst**. Publication succeeded at 08:42:18.485; the code calls thumbnail `prewarm()` immediately before that log. It launches up to two independent Python/Playwright/Chromium process trees alongside the SEO and CRM processes. Each renderer can also install Chromium at runtime if absent. The same two-renderer configuration exists in the incident commit. A worker startup appears at 08:42:32, followed by Render's failure/restart events.

Thirty-second metrics around the incident remained around 188 MiB and missed the spike. They do not establish a steady leak. There were no per-process/browser measurements at the time, so **the exact production allocation and killed process cannot be proven**. The local experiment reproduced an OOM with the original concurrent-renderer path; this is strong supporting evidence, not proof that every future OOM is eliminated.

## Focused changes

| File | Change |
| --- | --- |
| `worker_memory.py` | Read Linux cgroup v1/v2 limits/current/peak; cap thumbnail concurrency at one for containers up to 768 MiB. Sample supervisor, SEO, CRM and descendant RSS every five seconds; log every minute, on 32 MiB rises, or at 80% container pressure. Monitoring failure is nonfatal and redacted. |
| `sports_cave_worker.py` | Call the memory sampler from the existing supervisor loop. |
| `crm_thumbnail_cache.py` | Apply the small-container browser budget; log render start/concurrency; use bounded-output process helper. Existing queue, deduplication, cache, generation leases and error handling remain. |
| `crm_thumbnail_process.py` | Discard stdout, retain only the last 1 KiB of stderr in Python memory, retain the existing 120-second timeout, kill the Linux renderer process group on completion/timeout, and reap the parent. Windows timeout cleanup also kills descendants. |
| `crm_worker.py` | Enable safe thumbnail INFO logging only. Its existing buyer-sync changes predate this task and must not be mistaken for part of this fix. |
| `tests/test_crm_thumbnail_cache.py` | Point its mocked renderer at the new helper. |
| `tests/test_worker_memory.py` | Budget, cgroup formats, sampling, pressure, failure redaction, output bounds and real child/grandchild cleanup regressions. |
| `tests/benchmark_worker_memory.py` | Offline real-browser publication-burst and memory benchmark. |
| `tests/run_worker_memory_regressions.py` | Explicit loopback-only database regression runner with provider HTTP blocked and thumbnail prewarming mocked. |
| `docs/worker-memory-evidence/` | Read-only Render evidence and verified local test logs. |

SEO imports, schedules, polling intervals, campaign preparation, publication, email delivery concurrency, checkout enrollment, deduplication, retry policy, delivery gates and provider idempotency were not changed. No background feature was disabled. Existing broad local workspace changes were preserved.

## Memory and performance validation

Local Linux Docker, Python 3.12, real Playwright headless Chromium, **512 MiB RAM, no swap, 0.5 CPU**, init for child reaping, 512 process/thread limit, read-only source mount, network disabled. Production clients were not started. The benchmark imports worker dependencies, keeps an SEO import-only sibling alive, renders six synthetic emails per publication burst, and denies every browser image URL. A touched 110 MiB allocation models additional live worker state beyond import-only idle. This is a controlled capacity model, not a replay of production customers or a live SEO import.

| Measurement | Original | Fixed |
| --- | ---: | ---: |
| Browser renderers | 2 | 1 |
| Completed thumbnails | 18 / 3 bursts | 60 / 10 bursts |
| Peak **container** memory | **512.0 MiB** | **355.1 MiB** |
| cgroup OOM / OOM kills | 1 / 1 | 0 / 0 |
| Memory-limit hits (`max`) | 521 | 0 |
| Elapsed | 51.46 s | 149.77 s |
| Average per thumbnail | 2.86 s | 2.50 s |
| Settled process-tree RSS | 209.66–209.94 MiB | 209.02–210.21 MiB |

The original run completed thumbnails but recorded an OOM victim that was not identified. The fixed run additionally asserts the SEO sibling remains alive. The fixed run's small settled increase is consistent with retained thumbnail assets (bounded cache) and the benchmark's samples; this short run does not prove long-term absence of leaks. Sum-of-process RSS double-counts shared browser pages and is **not** the container budget metric.

A separate import-only fixed Linux run completed 18 thumbnails with a 257.7 MiB cgroup peak. Preliminary Windows Chrome comparisons showed lower process-tree RSS with one renderer but longer thumbnail-batch completion (14.95 to 25.16 seconds for 18). Those Windows RSS figures are not comparable to Render capacity. On the constrained Linux test, average throughput improved; on a less CPU-constrained host, serial thumbnail previews can arrive later. Customer-email schedules and delivery concurrency are unaffected.

## Tests

- **92 worker/SEO/thumbnail/monitoring tests passed on Linux**, including actual POSIX process-group timeout cleanup. The same suite passed on Windows.
- **162 database-backed regression tests passed** using a dedicated disposable loopback PGlite PostgreSQL fixture: publication, native automations, abandoned-checkout recovery, campaign dispatch, preparation, flow tests, timing, and shared thumbnail leases/fencing. All external provider HTTP was blocked; real thumbnail testing was separate.
- **60/60 real thumbnails passed** the long Linux test, zero OOMs, SEO sibling alive, approximately 157 MiB peak headroom.
- Python compilation and focused whitespace checks passed.

Verified logs: `worker-memory-evidence/worker-memory-linux-before.log`, `worker-memory-linux-stability.log`, `worker-memory-linux-tests.log`, `worker-memory-crm-verified.log`. Render source evidence: `worker-memory-evidence/render-readonly-evidence.json`.

Early harness attempts exposed sandbox loopback restrictions, a nonexistent test module name, and an artificially low Docker PID limit. These were corrected before the passing results above; they were not application regressions.

## Capacity and deployment decision

**Keep the 512 MiB plan.** The tested workload fits after the fix; there is no evidence that an upgrade is required. However, very large SEO slices, larger CRM working sets, full-resolution external images, cold Chromium installation, or different dependency builds may consume more than this model. No production memory improvement is claimed because nothing was deployed.

The narrow patch is suitable for a **controlled deployment after explicit approval**, with the new cgroup peak/pressure and thumbnail-start logs checked during publication and scheduled workload overlap. It is not an unconditional capacity guarantee or a proven permanent cure for all possible OOM causes. Deploy only these targeted changes after reviewing the existing unrelated workspace modifications. No approval to deploy has yet been given.

To reproduce the regression suite, start `tests/crm_postgres_server.mjs` with `CRM_FIXTURE_SQL_PORT=8898`, then run `.venv/Scripts/python.exe tests/run_worker_memory_regressions.py` with that same variable. The memory benchmark uses `--phase after --cycles 10 --reserve-mib 110 --channel=` in the Linux container. Its original snapshot is saved locally under `tmp/worker-memory-before`; do not replace that snapshot with the modified code.
