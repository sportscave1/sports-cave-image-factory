# Native file opening V2 — local implementation

Task: `20261013-9c55f02e`; owner `codex-native-v2-20261013`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-native-file-opening-v2-secure-browser-help-20261013-9c55f02e`.
Branch: `codex/task/integrations-native-file-opening-v2-secure-browser-help-20261013-9c55f02e`.
Implementation baseline: latest fetched main `a96652e772393ae787fab214c052af9a2cd430d0`. The category entry point was clean. Studio allocated from its older approved pointer; this empty owned task was fast-forwarded before editing at the user's explicit latest-main request. Only this task's recorded baseline was aligned; global approved-base and other tasks remain unchanged.

## Root cause and implementation

Files Open/Open With checked only `window.chrome.webview` capabilities. Normal Edge/Chrome do not supply that embedded WebView2 bridge. The old registered protocol dispatches path-based legacy opening, not the authenticated transfer action used by the desktop bridge.

The existing Windows desktop executable now supports `sports-cave-files://launch` (helper 11). A Files action prepares one immutable Dropbox ID/revision using fresh metadata; filename is not used to resolve identity. The launch URL carries an opaque, account/session-bound single-use code in a fragment, not Dropbox credentials, file paths or transfer secrets. A compact window of the existing desktop app uses its normal signed-in WebView2 session to redeem the code and invoke its existing origin-scoped Open/Open With bridge. Browser cookies are never copied. The same active account with Files permission must be signed in to Desktop.

Codes expire after two minutes; claim is single-use. Both preparation and claim/cancel require an authenticated Files user and a matching, present Origin header. Helper origin parsing permits configured HTTPS origins or configured loopback HTTP only, rejects credentials/extra arguments and unsafe launch forms. The transfer uses the existing bounded lifetime/manager and header secret. The new stream is pinned to ID and revision and checks returned ID/revision/hash. Helper network redirects are refused. Executable/script types, unsafe relative paths, reparse escapes and hash mismatches are rejected.

Helper 11 verifies local Dropbox contents, hydrating placeholders by reading. A stale local revision is not opened or changed. Otherwise the existing managed cache streams the pinned original with bounded buffers and verifies size and Dropbox content hash before opening. Valid cache objects are reused, including filename changes; no repeat download or Dropbox write-back. Windows file associations handle Open, and the genuine `SHOpenWithDialog` handles Open With without registering defaults. Existing legacy Photoshop methods/protocols and v10 WebView2 behavior remain available. No backend rebuild or new background service, polling, schema, database migration or dependency was added.

Single-click remains selection; double-click, Enter, Open and Open With use the same native path. Folder navigation remains unchanged. Browser preparation shows immediate state, Retry/Download/helper-update guidance, and cancellation. If transient browser activation expired while metadata was fetched, an explicit Open desktop helper button provides the required user gesture. External-app prompts cannot be bypassed or reliably detected. The helper window shows progress, sign-in/error guidance and cancellation. Existing Mac/mobile preview/download and device Open With/Share guidance remain; no installed-app selector is simulated.

## Benchmarks

Chromium, same machine/runtime/viewport and fixtures, 9 samples per scenario; millisecond values are median / p95. Baseline and after were measured in the same final run. Rows represent 2 GiB PSD metadata, never downloaded for browsing.

| Scenario | Before render | After render | After selection | After double-click dispatch |
|---|---:|---:|---:|---:|
| 100 rows | 101.7 / 142.0 | 99.2 / 111.1 | 3.2 / 3.9 | 16.6 / 17.8 |
| 500 rows | 124.0 / 135.4 | 126.6 / 129.3 | 2.7 / 2.9 | 16.6 / 16.8 |
| 1000 rows | 170.7 / 191.0 | 163.8 / 172.3 | 3.3 / 4.5 | 16.6 / 16.8 |

500-row median changed by 2.1%, within the 10% goal and comparable to the earlier approximately 128 ms result. Selection p95 is under 5 ms. Each render has one mocked list API call; every 9-render set has 9 list calls, no polling and zero master downloads. Double-click dispatch includes the simulated bridge response and local mocked preparation endpoint, not real application startup or cloud latency.

Actual compiled Windows helper/cache, 16 MiB + 7 byte test fixture, 9 samples:

| Measured preparation | Median ms | p95 ms |
|---|---:|---:|
| Before: existing synced hash verifier | 12.09 | 20.90 |
| After: verified synced open preparation | 13.38 | 22.72 |
| After: cold cache (local fixture HTTP stream) | 60.36 | 97.02 |
| After: warm/repeat cache | 10.78 | 14.48 |

The cold series has 9 transfers into separate test cache roots. Warming the shared cache adds 1 transfer; 9 measured warm repeats and a filename rename add zero transfers. Total test master requests: 10. Synced tests download nothing. Test masters remain unchanged. Content is hashed on reuse; warm preparation is not an unverified size-only shortcut. App startup and browser-to-native IPC time are unmeasured because no actual application or registered protocol was launched.

Metadata-only 2 GiB preparation, 25 samples, mocked Dropbox and real grant code:
- baseline: median 0.0206 ms, p95 0.0478 ms; 1 metadata call per preparation, zero content downloads.
- v2: median 0.0354 ms, p95 0.0516 ms; 1 metadata call per preparation, zero content downloads.

These microbenchmarks exclude Dropbox network latency. A complete 1+ GiB real PSD transfer/hydration/application load remains untested; constant-buffer stream handling and large metadata were validated instead. Opening costs one fresh metadata lookup, with an additional authenticated claim for a browser handoff and the existing manifest request in the helper. A cold cache adds one streaming content request; valid synced/cache reuse does not.

## Tests

- 124 focused Python tests passed across new signed-session/replay/ID/security/cache tests and existing VA permissions, picker, Files upload/download, directory matching, Orders, edition table, desktop and native chooser specifications.
- Additional final PSD/Windows/V2 regression run: 28 tests passed, including representative real snapshot IDs/renames/multi-product Orders and actual Windows helper compilation/hash/Photoshop launch specifications. No Photoshop process or master was opened.
- New V2 Chromium fixtures: 9 scenarios passed (Windows browser, Mac/mobile fallbacks, exact selection, Enter, Open With, helper success/outdated/denied/progress/cancel).
- Existing Files interactions: 4 scenarios passed; existing compact PSD modal/Files: 9; signed-cookie/VA picker: 11. Existing fixture expectations were adapted for the requested browser fallback and helper version; v10 bridge coverage remains.
- Final Windows-normalized filename bypass/security/compiled cache run: 18 tests passed.
- Studio syntax/secret-pattern/unit/static checks and task-local `git diff --check` passed.

Native code was genuinely compiled and its OS chooser flags, strict protocol parser, streamed verified cache, local files, cancellation and renamed-cache behavior were exercised on Windows. Browser/Dropbox responses were mocked. Browser protocol links were intercepted to prevent actual launches. No actual Photoshop/chooser/UI launch, physical Mac/Safari/iOS/Android compatibility or real >1 GiB master benchmark is claimed.

## Files changed

- `components/files_window/index.html`: additive normal-browser handoff and permission/progress/cancel/fallback UI; existing WebView2 path retained.
- `components/files_window/native_launch.html`: compact existing-helper handoff page.
- `files_native_launch.py`: small opt-in opening handlers and ephemeral single-use launch manager.
- `files_upload_api.py`: additive routes and strict ID/revision stream handling for the new grant purpose; existing contracts retained.
- `desktop_helper/SportsCaveFilesDesktop.cs`: helper 11 launch dispatch, safe parser and verified existing cache/association opening.
- `desktop_helper/Install.ps1`, `desktop_helper/README.md`: refresh version and usage documentation; installer was not run.
- `tests/test_files_native_v2.py`, `tests/test_files_native_v2_windows.py`, `tests/test_files_native_v2_ui.cjs`, `tests/test_files_native_v2_bench.cjs`: focused new tests/benchmarks.
- `tests/test_desktop_helper.py`, `tests/test_psd_native_windows.py`, `tests/test_files_premium_ui.cjs`: compatible existing regression fixtures.
- This report. Benchmark output and the read-only snapshot CSV stay ignored under `output/`; no exports are committed.

## Remaining limitations and readiness

Local implementation is tested and ready for review; real browser-to-installed-helper and Photoshop/other-app smoke tests are required before release readiness can be confirmed. A Windows helper refresh to version 11 is required for normal Edge/Chrome launch support. Desktop sign-in uses its existing session; a different account, expired session, blocked protocol prompt or absent helper is actionable rather than silently treated as success. Mac/mobile/Linux browsers use genuine preview/download/OS sharing fallbacks; native arbitrary-app launching is not promised. Legacy raw-path protocols remain unchanged for compatibility; all new V2 UI handoffs use the authenticated single-use route.

Launch/transfer grants are intentionally ephemeral like the existing transfer manager: restart/expiry requires retry. Multiple API instances would need shared/sticky grant routing; none was introduced (existing canonical OS configuration is single-instance). Offline cloud metadata prevents fresh native authorisation even when a local copy exists; the UI offers retry and clear network guidance.

No Supabase records, product mappings, 282 linked PSDs or 51 unlinked records were changed. The five-action PSD popup, VA attachment capability, editions, allocations, Orders and Dropbox operations are preserved. No commits, pushes, deployments, installs, production changes or master writes occurred.
