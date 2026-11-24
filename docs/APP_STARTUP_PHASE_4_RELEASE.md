# Sports Cave OS performance — Phase 4

User authorized completing all four phases and publishing Git/Render on
24 November 2026. Task: 20261124-564ab6e2. Phases 1–3 reports remain historical
local checkpoints; this release combines them with current main, including
PublicReviews routing and authorized Reviews prefetch.

## Final changes

- Phase 1: startup, public transport and database timing instrumentation.
- Phase 2: Home pooled transaction/pipeline and indexed Orders certificate lookup.
- Phase 3: Home/Orders fragment completion without a full application rerun;
  permission/scope checks, retained rows and native retry preserved.
- Phase 4: one background thread precompresses installed public hashed Streamlit
  JS/CSS using Brotli quality 5. Maximum 512 entries, 16 MiB compressed, 8 MiB
  per source file. No customer response cache or provider calls. Requests use
  gzip while warming. Source signature and downstream ETag/content length,
  public cache policy, type and cookie checks gate replacements. Preserve
  conditionals, ranges, HEAD, cache policy and security headers.
- CI on main, this task branch and relevant PR changes runs isolated SQL,
  permission/loading/transport contracts, native JavaScript and real-browser
  synthetic fixtures. Artifacts include framework versions and source hashes.
  Baseline SQL is pinned to pre-Phase-2 commit 333d9a9d, so committing the
  candidate cannot turn a comparison into candidate-versus-itself.
- Repaired the obsolete toolbar timer contract to count the guarded planner
  interval specifically and use the existing refresh constant. Companion
  rotation intervals and application behavior are unchanged.

## Measured local evidence

See APP_STARTUP_PHASE_4_EVIDENCE.json. Synthetic data only; these are not
authenticated production Home/Orders or desktop cold-launch measurements.
Three normal samples, two throttled samples and one server restart for transport;
three paired samples per page scenario. Browser cache remains enabled.

| Measurement | Before | Candidate |
| --- | ---: | ---: |
| Initial encoded frontend bytes | 908,331 | 802,542 |
| Throttled fresh-browser median | 8.838 s | 7.878 s |
| Normal fresh-browser median | 449 ms | 466 ms |
| Normal cached reload median | 383 ms | 354 ms |
| Synthetic Home, 300 ms read | 1.379 s | 0.435 s |
| Synthetic Orders, 1.4 s read | 3.218 s | 1.897 s |
| Completion-triggered full-app reruns | 1 | 0 |
| Cached JS/CSS reload transfer | 0 | 0 |

Normal cold loading has no demonstrated improvement; the useful compression
gain is 11.6% fewer frontend bytes and approximately 11% faster throttled cold
load. A sub-2.5 s slow-network cold launch is not achieved. The framework and
connection still impose a substantial initial cost. No framework rewrite is
included in this release.

## Validation and reproduction

Local focused suite: 176 passed and 39 passing subtests; budget tests add two
passing cases. SQL baseline correction revalidated all 13 SQL cases.
Reviews compatibility: 26 passed, 28 explicitly skipped because its disposable
PostgreSQL suite was not enabled. Shell/Home JavaScript passed and native
Orders JavaScript passed 14 cases. Transport tests verify actual StaticFiles,
body integrity, negotiation, weak validators/304, ranges, HEAD, streaming,
pathsend, source changes and nonblocking bounded warming.

Core commands:

~~~powershell
python scripts/benchmark_app_startup.py --samples 3 --slow-samples 2 --restart-samples 1 --out .tmp-startup-phase4/final-startup.json
python scripts/benchmark_page_loading.py --samples 3 --out .tmp-startup-phase4/pages.json
python scripts/check_os_performance.py --startup .tmp-startup-phase4/final-startup.json --pages .tmp-startup-phase4/pages.json
python scripts/validate_render_topology.py
~~~

CI ceilings are regression guards for these fixtures, not production SLOs:
median initial encoded bytes <=850,000; zero cached JS/CSS transfer;
normal cold <=5 s, throttled cold <=15 s; page synthetic readiness <=4 s;
one app navigation run, zero full-app search/completion reruns, retained rows.

## Release procedure and limits

Publish the exact passing task revision, then fast-forward main without force.
The existing primary sports-cave-os and supporting services auto-deploy main;
do not trigger a second deployment or sync a Blueprint. Preserve the existing
suspended daily cron. No migration or production configuration change is
required for these performance edits.

Verify the exact deployed commit, primary and webhook health, public shell,
compressed assets, validators and startup logs. Do not test customer mutations.
Record deployment IDs and verification in a separate release receipt after
observing the result. Authenticated production Home/Orders timings remain
unverified unless a signed-in live measurement is explicitly recorded there.

## Live release and measured follow-up

Runtime a6ec215cd87705454d22b03dda2b51261102f2d6 is the final production
revision, following the initial dddc13be rollout. See
APP_STARTUP_PHASE_4_LIVE.json for deployment IDs, timestamps, source hashes,
public HTTP checks, browser samples and sanitized startup logs.

The final live check found that anonymous opening unnecessarily called account
bootstrap discovery. Missing tokens now fail closed immediately; invalid or
expired tokens cannot trigger bootstrap discovery. Valid signed user tokens
still fetch the current active account and verify session version; valid legacy
tokens retain existing bootstrap rules. Eighteen tests exercise real signatures,
expiry, revoked/inactive/mismatched accounts, lookup outages and legacy/session
behavior. Submitted sign-in still performs the required account discovery.

The app, webhook and SEO worker deployments use the exact runtime revision.
The existing suspended daily cron remains suspended. Public health, shell,
identity/gzip/Brotli body parity, immutable cache policy, weak ETags/304, ranges
and HEAD checks passed. Live browsers rendered sign-in without app exceptions
or page errors; no credentials were entered or customer workflows exercised.

| Live anonymous check, Australia to Oregon | Before auth follow-up | Final |
| --- | ---: | ---: |
| Fresh browser median, three samples | 4.428 s | 4.259 s |
| Cached reload, one sample | 3.021 s | 2.756 s |
| Server anonymous authentication check | 1,279–1,433 ms | 0.07–0.08 ms |
| Cached frontend bundle transfer | 0 | 0 |

The small browser differences are not a robust end-to-end speed claim. The
server lookup cost was removed, while network/framework rendering remains
material. A sub-2.5 s production cold opening has not been demonstrated.
Authenticated live Home/Orders were not measured.

GitHub OS performance CI passed on the exact final runtime revision:
123 checks and 22 subtests plus browser/JavaScript budgets, on Linux/Python3.12
and Streamlit1.67. Reviews CI passed too. The extended Orders gate passed;
its Orders sources are unchanged by the subsequent anonymous-auth guard.
The collection gate exposed a pre-existing Node VM harness missing FormData;
the test-only repair passed all 82 native tests and types locally. Final
collection rerun also passed, including its full duplicate Orders/Inbox gate;
the exact run IDs are recorded in the live receipt.

Required deployment migrations and SEO setup retain their fail-closed ordering.
Final server process lifecycle readiness was 42.913 s; this is deployment
startup, distinct from opening the already-running standard-plan application.
