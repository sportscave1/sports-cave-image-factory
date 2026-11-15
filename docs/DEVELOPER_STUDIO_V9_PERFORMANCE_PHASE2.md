# Sports Cave OS V9 — Performance Phase 2

Status: implemented locally; tested with final evidence recorded alongside this report. No installation, commits, pushes, merges, deployments or production changes.

CORE task: `v9-p2`, owner `codex/v9-p2-01a13216`, branch `codex/task/core-perf2-v9-p2`. Worktree: `C:/Users/hello/.codex/visualizations/2026/10/12/01a13216-edba-7c20-896a-70f604c44d7e/p2/sports-cave-core-perf2-v9-p2`.

The base is verified V9 commit `c646cf0a6c69a71a5b4ee16a4c3778805761131e`, rather than a production snapshot. Every runtime file matched the prior V9 SHA-256 manifest before allocation. Seven unfinished evidence files were copied byte-for-byte; their receipt is `v9-p2-source-receipt.json`. The original V9 source and untracked evidence remain unchanged.

## Baseline and method

Prior evidence: `DEVELOPER_STUDIO_V6_EDITOR.md` records a single 19.314-second cold runtime result; `DEVELOPER_STUDIO_V8_SILENT_DOCKER_PERFORMANCE.md` records a 14.54-second median after its silent relay/session improvements. `DEVELOPER_STUDIO_V9_LOCAL.md` contains single acceptance observations, including 36.9-second entry, 5.93-second navigation and 6.73-second mapped Save. These are historical context, not comparable repeated Phase 2 measurements.

The repeated Phase 2 comparison is `v9-p2-before-active.json` versus `v9-p2-completed.json`: same machine, installed visible Windows Edge, a disposable profile, local hosted-entry fixture, authenticated local bridge and real isolated Docker application. The existing 18762 companion and application copy are never used for test mutations. Production sign-in/cookies/customer data are not imported. The profile has its own synthetic trusted-device enrollment. The actual required local editing-confirmation click is performed; waiting for a human to approve is excluded. Backend processing after that click is included.

Dev Mode is explicitly foregrounded after confirmation. An earlier background-tab run is retained as diagnostic evidence, since Edge delays painting and timers in background windows. Five repetitions cover warm reopening, navigation, Save/Undo, device changes and wheel input. Three cold runtime repetitions each create a new owned container with fresh security probes, with Docker already available and the image locally cached. p95 is nearest rank; with five or three samples this is the maximum observed value, not a statistically stable production percentile. The additional 300 ms UI settling allowance in `ready()` is identical in both phases. Cold full-entry and initial HTML-opening observations are single samples and are labelled accordingly.

## Measured comparison

| Operation | n | Before median / p95 | After median / p95 |
|---|---:|---:|---:|
| Warm reopening | 5 | 11.10 / 11.62 s | 2.05 / 2.54 s |
| OS page navigation | 5 | 6.25 / 7.28 s | 4.73 / 5.22 s |
| CSS Save to preview | 5 | 6.77 / 8.30 s | 3.72 / 4.79 s |
| Desktop/Tablet/Mobile | 5 | 3.20 / 3.73 s | 1.17 / 1.67 s |
| Single wheel interaction | 5 | 1.83 / 2.35 s | 1.32 / 1.84 s |
| Cold Docker runtime | 3 | 14.74 / 23.25 s | 15.40 / 15.92 s |

Cold full entry is a single sample: 35.76 to 24.48 seconds after clicking editing confirmation; it is not a reliable p95. Mounted editor DOM appears in 1.90 / 1.91 seconds median / p95 before, versus 0.88 / 0.99 seconds after (six samples); this measures attachment, not readiness of every editor control.

Repeated controller input (five Tab/text/Backspace sequences): 1.05 / 1.05 seconds median / p95 before, 0.31 / 0.35 seconds after. This isolates the controller roundtrip rather than the full bridge.

Source-only installed Edge diagnostic, 200 dense input events on the actual 151 KB HTML: handler median / p95 23.3 / 29.2 ms before, 2.4 / 4.0 ms after. JS heap sampled after the edit burst: 19.34 to 2.46 MB. Recovery writes: 200 to 1. The diagnostic storage-length field is a character/code-unit count, not measured disk bytes. Native clipboard paste passes in both phases; its reported timer includes a fixed 500 ms settling allowance, so no paste-latency improvement is claimed.

Five two-second source-only idle samples: total disposable Edge process RSS median 619.3 to 562.4 MiB; CPU median 0.23% to 0.88% of one core. There is no verified idle CPU gain. Full-application Docker stats and ten-second Edge process CPU observations are retained in the workflow JSON; they are single observations with different loaded-page state and are not controlled idle savings.

Five repeated HTML source switches: 3.02 / 3.42 seconds median / p95 before, 2.48 / 2.86 after. This focused comparison loads the exact baseline host/editor Git blobs in memory, without replacing worktree files, and keeps application source and security checks intact. File switching still has visible processing latency.

## Confirmed costs and fixes

1. The full draft catalogue ran on every workspace capability RPC, despite its presentation results being discarded. In the first baseline it took 584 ms median, launched twelve Git commands, and ran 78 times. In the larger matched foreground scenario it ran 117 times; the completed candidate performs 6 initial catalogue loads. Git launches fall from 3,401 to 791 across the same scenario. All 858 audited Git/Docker launches are silent. Normal capability operations now perform fresh initiating-owner/worktree validation and exact selected UUID/task validation, without rebuilding catalogue rows or calculating unrelated Live revision comparisons. Selected-task operations still perform their existing source and lease validation. Grant task reassignment now fails explicitly. Catalogue operations retain their full existing checks.
2. Remaining identity validation used three independent Git process launches. Ten interleaved measurements found 161.5 ms median versus 63.9 ms for one fresh `git rev-parse` returning common directory, top-level root and attached branch. All three facts are still checked on every invocation, including rejection of detached HEAD, wrong branch, wrong common directory and nested roots. No identity or authorization cache was introduced.
3. Workspace mount/start repeated workspace-model, editor-files, initial editor-open and navigator calls. The editor now uses the just-validated model/file listing, avoids the duplicate initial file load, coalesces pending model/navigator/viewport requests, and returns the mounted editor while genuine preview startup proceeds. Navigator presentation is invalidated on Save, page change and Stop. Source reads/writes and inspection still validate their authority and current source at the backend. The local fallback renders its validated model first, then loads the catalogue without blocking initial editing.
4. Each keystroke rebuilt highlighting and stored a whole source snapshot in Undo and browser recovery. A 200-event burst on the actual 151,397-character HTML template wrote 31.4 million serialized UTF-16 code units in 200 recovery writes. Highlighting is now scheduled once per animation frame; source Undo retains bounded inverse edits and the original buffer. Recovery writes occur at most once every 300 ms during continuous editing, with synchronous flush on before-unload, pagehide, hidden visibility and disposal. Stale recovered hash/revision protection remains unchanged. Native large-file paste, keystroke Undo and immediate-close recovery pass.
5. Keyboard sequences previously captured a screenshot after each text/key event. Bounded ordered batches now apply up to eight fixed text/key/scroll events and capture one final frame. Text totals, JSON size and fixed key limits remain enforced. Enter finishes a batch; queued events from an old page are cancelled. The controller rejects an unexpected actual page before applying any batch. Wheel events are queued/coalesced rather than discarded while another operation runs. Mutating events are never automatically replayed after transport failure.
6. The controller’s stable-content poll used multiple browser round trips per sample; it now reads the same readiness, body text and Running status together. It retains three stable samples and the same bounded timeout. Normal visible OS sidebar navigation uses the real application button, retaining Streamlit’s session, with the old validated route URL as a fallback. Rendered route/epoch metadata is collected together; icon-only sidebar controls cannot be mistaken for Sign in, and a collapsed sidebar cannot hide the actual page identity.
7. Actual HTML Save testing found that the top-bar component intentionally retained its old parent DOM across reruns. Authorised changes to its HTML now reinstall that component inside the isolated preview, while keeping its container, Streamlit session and synthetic database. Readiness also waits for the replacement header. The displayed raster is retained throughout. A real static label change rendered successfully and Undo restored exact bytes and preview. No production top-bar source was changed for this correction.

## Exact runtime files changed

- `scripts/studio/studio.py`
- `scripts/studio/draft_ui.py`
- `scripts/studio/preview_runtime.py`
- `scripts/studio/preview_input.py` (new fixed bounded input validator)
- `scripts/studio/isolation/controller.py`
- `scripts/studio/isolation/PerformanceP2.Dockerfile` (new)
- `scripts/studio/ui/workspace.js`
- `scripts/studio/ui/workspace-local.js`
- `scripts/studio/ui/editor.js`

There are no CSS/layout changes or changes to other OS pages. Exact byte hashes are in `v9-p2-runtime-manifest.json`. Test-only changes: `test_preview_input.cjs`, `test_performance_p2.py`, `test_editor_performance.cjs`, `test_page_metadata.cjs`, `benchmark_v9_p2.py`, `benchmark_editor_p2.py`, `verify_input_p2.py`; raw JSON/PNG/JPEG evidence under `docs`.

## Safety and verification

- 65 focused Python tests, including Studio ownership/identity, capability scope/expiry, source allowlists, stale-write/revision conflicts, Undo, references and persistent relay behavior.
- Six Node suites: automatic draft restoration/reconnect, retained decoded frames, bounded ordered input, source viewport/wrapping, inverse Undo/recovery scheduling, and rendered route/epoch metadata.
- Real Edge/Docker repeated workflow: automatic authorised test-copy restore, existing trust reuse, genuine editing approval, navigation, HTML/CSS editing, CSS Save/Undo, device sizing, scrolling, closing/reopening, same container, no browser JS errors, all audited Git/Docker launches using CREATE_NO_WINDOW.
- `v9-p2-input-final-host.json`: actual page identity across Desktop/Tablet/Mobile, ordered input, stale-page rejection, real changed-lease-owner rejection, local fallback, immediate-close recovery in the same Edge storage context, visible HTML Save and exact source/preview Undo.
- Fresh Docker policy and negative probes remain mandatory for every new container. Network-none, non-root, read-only root, seccomp, no published ports, no host mounts, resource limits, synthetic authentication and data, immutable image/container/context identity, owner/lease validation and idle shutdown are unchanged. Current allowlists and sensitive-operation confirmations are unchanged.
- Existing companion preservation verified independently: port 18762, task `SportsCave-Studio-20261011-7192d493`, Windows owner `hello`, logical owner `codex/v8-01a12f62`, original registry home, interpreter and startup action unchanged. Installed files still match the approved V8 runtime manifest. Original application `9ca4a85e-b3f4-4c85-b61e-4eb5551d2740` remains revision 6, selected automatically, with original source hash and DPAPI trust expiry unchanged. No draft was updated from Live.

The exact candidate image is `sha256:d74525e5ce7bd49a602399f6ac1e16476b9158bfaab00bb00703b42a85815baa`, built locally from verified V9 image `sha256:5a22bde08670c241dd349f56e374ee5510a58f9f13d077831d1cd9de8746d061`. Only fixed controller/input code is replaced; existing tags and the installed V8 image are untouched.

During testing Docker’s Linux engine stopped with a WSL-version precondition error while Desktop’s UI remained open. A bounded normal Desktop restart recovered it; no reset, image deletion, settings change or companion restart was performed. A tab-close test can produce an existing Windows 10053 aborted-response diagnostic; the action is never replayed. Tests initially using a fresh Browser.new_page storage context were corrected to reopen within the same context; this was a harness issue.

## Limits and local readiness

The automated driver's bulk `fill()` action still times out on the large HTML textarea, despite visible/enabled/editable state. Actual native clipboard paste, ordinary typing, Save, Undo and recovery pass; the driver limitation is not reported as a user paste failure. Browser hard termination can lose the most recent pending recovery interval (up to roughly 300 ms when the event loop is responsive); normal navigation/closure and temporary disconnection retain the buffer and flush it.

Cold startup remains dominated by genuine isolated application/database/security startup; no cold-start or idle CPU saving is claimed. Navigation and Save still take seconds. Full-runtime memory observations and source-only editor measurements have different scopes and must not be conflated. This is local tested source for review, with uncommitted changes; it is not installed, integrated, published or deployed. The active companion remains its approved V8 runtime. Everyday production Edge has not been repointed to this candidate, and receiving these changes requires a separate approved installation/release.
