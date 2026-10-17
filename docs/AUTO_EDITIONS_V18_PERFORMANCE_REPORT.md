# Auto Editions V18 — local performance report

16 October 2026. Isolated INTEGRATIONS task `20261016-86a3dda5`, owner `codex-v18-performance-20261016-01`. Based on verified live revision `3cbbfc177dcb7dd01af53a93a44429fa5b3600fe`, including V17, ICC recovery, Worker Health and the newer Orders release. All V18 changes remain local and uncommitted. No deployment, live configuration, asset, queue or companion changes occurred.

## Comparable results

| Measurement | Approved baseline | V18 local | Interpretation |
|---|---:|---:|---|
| Small synthetic package cycle, median / p95 | 0.742 / 0.756 s | 0.737 / 0.744 s | Essentially unchanged |
| Medium synthetic package cycle, median / p95 | 2.272 / 2.340 s | 1.992 / 1.993 s | 12.3% lower median |
| Large synthetic package cycle, median / p95 | 5.554 / 5.641 s | 4.583 / 4.591 s | 17.5% lower median |
| Large loopback transfer, median | 4.454 s | 3.351 s | Fewer bytes; approximately 15.4 MiB/s in both modes |
| Large packet bytes | 72,221,801 | 54,242,872 | 24.9% smaller, exact reconstruction |
| Three retained verified packages | 119.9–174.3 MB | 93.7–132.7 MB | 21.9–23.8% smaller; every reconstructed byte unchanged |
| Cloud logical requests: new 101-asset package | 202 | 102 | Same 101 uploads; metadata requests reduced |
| Cloud logical requests: fully resumed package | 101 | 1 | Fresh bounded listing; zero uploads |
| Worker Health cold snapshot, 285 products, median / p95 | 67.0 / 79.1 ms | 63.0 / 69.7 ms | Disposable local SQL fixture |
| Worker Health cold snapshot, 334 products, median / p95 | 84.9 / 104.8 ms | 80.7 / 96.9 ms | Read queries 5 → 2 |
| Worker Health cached snapshot median, 285 / 334 | — | 1.26 / 1.48 ms | Two-second single-flight cache; zero SQL on hit |
| Browser unchanged render CPU, 334 desktop / mobile | 1.870 / 1.916 ms | 0.083 / 0.082 ms | 100 repeated renders; CDP main-thread task duration |
| Browser unchanged table mutations, five refreshes | 375 | 0 | 25 visible rows; 347 DOM nodes retained |

Synthetic package cycles include construction, paced loopback upload and full server import/ICC/pixel verification, excluding Photoshop and real providers. Three repetitions per size use identical fixture fingerprints and 100 numbered patches. With three samples, reported p95 is the observed maximum, not a reliable population tail estimate. No synthetic cycles/hour figure represents finished designs/hour.

At 285/334 products and desktop/mobile, mocked navigation medians were 54–73 ms before and 53–64 ms after; refresh remained approximately 27.7 ms. No material navigation or refresh wall-time gain is claimed. Page responses remain approximately 14.6 KB with 25 rows; diagnostics remain lazy and scan at most 200 records, returning at most 50. A 1,000-record synthetic diagnostic corpus took approximately 9–11 ms per filtered request. Filters, selection, scroll, dialog state and hidden-page suspension are retained.

The controlled synthetic runs used 9.66 → 10.23 process CPU seconds and sampled peak RSS 81.5 → 99.5 MiB: CPU/RAM reduction is **not** claimed. Peak logical temporary files fell 317.6 → 281.7 MB, including both packets and reconstructed assets. Retained full-resolution validation peaked at approximately 952 MiB across both modes. TEMP-volume free space is measured; actual Photoshop scratch configuration/availability remains unknown. Production web-service five-minute observations were 0.042–0.131 CPU cores and 210–572 MB RAM across instances, not per-job peaks or V18 results.

## Observed bottlenecks and limits

Read-only production telemetry contains 44 successful imports: median / p95 server receive 25.42 / 33.09 s, validation 13.66 / 17.67 s, Dropbox asset publishing 52.44 / 77.31 s and database checkpoint persistence 5.78 / 6.47 s. One retained recovery receipt took 355.53 s through client upload/confirmation versus 116.05 s server processing; the difference cannot be attributed wholly to Dropbox. A historical safe template run spent 68.44 s exporting numbering assets out of 75.33 s native Photoshop stages. These establish transfer/confirmation overhead, numbering export and cloud asset publishing as substantial bottlenecks in different cohorts; they are not a single comparable ranking.

Four naturally completed recovery imports observed over 24 minutes yielded 10.0 successful imports/hour, with claim-to-import median / p95 326.98 / 418.72 s. This is recovery throughput, not catalogue Photoshop throughput. Historical terminal-to-next-claim gaps: 98 bounded samples, median / p95 5.10 / 41.61 s, excluding two over 300 s and including failures. V18 terminal wake-up is tested, but no production after figure is available. Photoshop rendering and live Dropbox throughput before/after remain unmeasured because active preparation was not interrupted and no production benchmark uploads ran.

## Implementation and safeguards

- `auto_editions_performance.py`, `scripts/prepare_auto_editions.py`, companion and setup API: stage durations, CPU/RAM/free-space snapshots, bytes, effective throughput, attempts, claim latency and completion-to-claim gap outside immutable manifests. SHA256 and Dropbox hashes share one file pass. Original/staged PSD integrity checks remain independent.
- `auto_editions_local_cache.py`: reuse pinned, fully hashed local staged sources; inspection receipts bind source identity, raw SHA256, inspector code and report hashes. Raw ICC inspection, geometry, roles and preparation proofs still run. Existing verified masters, patches, packages and cloud receipts remain reusable.
- `auto_editions_transport.py`, package importer and capability negotiation: optional bounded lossless reference-byte sharing. Retained PNGs share image data but differ in metadata, so whole-file deduplication was ineffective. ZIP deflate also gave inconsistent benefits. Exact reference bytes, metadata, independent export hashes and full ICC/pixel proofs are retained. Limits apply to expanded assets; malformed dependencies and evidence fail closed. Older servers receive legacy packets by default. A compact retained packet requires a compatible server; rollback rejects it safely rather than weakening checks.
- `auto_editions_cloud.py`: one fresh bounded listing reuses immutable verified receipts; incomplete listings fall back to per-file lookup. Upload concurrency remains three, conflict mode remains cancel, and ID/revision/size/content-hash validation remains mandatory. No storage/service replacement. Existing durable recovery remains; HTTP upload retry does not gain byte-offset resume.
- Companion: terminal completion or acknowledged failure wakes the existing host loop. Idle polling and error backoff remain bounded. Photoshop single-owner lock, paid-order priorities, leases, retries, Pause/Resume and durable checkpoints are preserved.
- `worker_health.py`, `worker_health_cache.py`, API and existing HTML: bounded compact SQL, two-second single-flight read reuse with mutation invalidation and per-request authentication, keyed rows and changed-text updates, bounded diagnostic history, request coalescing and stale-response protection. No layout redesign or extra cards.

No image resolution, JPEG quality, profile policy, colour conversion, supplier/visual approval, edition number, allocation, certificate, source identity or original Dropbox PSD was changed. Full expensive pixel validation remains; no new trust shortcut replaces it.

## Validation and reproducibility

Evidence is retained under ignored `output/v18/`: `pipeline-*-final.json`, `retained-package-comparison.json`, `upload-simulator-comparison.json`, `sql-*-final.json`, `worker-health-*-final.json`, read-only production aggregates and `verified-base-update.json`. New repository benchmark scripts run offline; retained-package comparison accepts the existing pinned package index. No customer data or production credentials are used in fixtures.

Focused coverage includes tagged/untagged ICC policy handling, conflicting profiles, exact reconstructed bytes, independent pixel proofs, unchanged originals, hostile transport inputs, source/inspection-cache invalidation, retained recovery, concurrent imports, lock ownership, queue priorities, Pause/Resume, edition allocation and cached-read invalidation. A synthetic PGlite fixture deadlock was repaired with logical transaction ownership across AnyIO workers; production database code was unchanged.

The combined regression on `3cbbfc17` finished with **442 passed and 13 pre-existing failures** in 190.41 seconds, plus the expected duplicate-ZIP warning. All Auto Editions/ICC/recovery/Worker Health tests passed. The 13 older Orders/Edition Ops UI failures were reproduced individually against a pristine `git archive HEAD` source fixture: **13 identical failures**, recorded in `pristine-base-regression.log`. They concern unchanged page structure/legacy UI assumptions and are not repaired in this performance task. The earlier focused pipeline run had 271 passing tests.

Seven JavaScript suites passed: Worker Health desktop/mobile, V18 race handling, Photoshop ICC inspection, V17 state preservation, quality review, the native reset grid and onboarding. The native grid used its dedicated synthetic loopback server, which was stopped after the checks. Studio static verification, secret-pattern scanning and Render topology validation passed. Studio status is Tested; integration readiness remains false because the work is intentionally uncommitted. V18 requires separate review and release authorization.
