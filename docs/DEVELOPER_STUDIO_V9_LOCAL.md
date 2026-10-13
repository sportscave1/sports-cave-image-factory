# Developer Studio V9 — local implementation

Status: **Implemented and tested locally, not installed or deployed.**

CORE worktree: `C:\Users\hello\.codex\visualizations\2026\10\12\01a13216-edba-7c20-896a-70f604c44d7e\v9\sports-cave-core-dev-mode-v9-dev`  
Branch: `codex/task/core-dev-mode-v9-dev`  
Assigned task/owner: `v9-dev` / `codex/v9-01a13216`  
Base: `fcb1b6e87f672a5a5fc182dd73d793ffc7183c68` (exact completed V8 connection/performance file contents verified before allocation).

## Interface and workflow

- The authorised sidebar entry is now Dev Mode, a real new-tab link with `noopener`. The original tab stays open. The standalone Streamlit tab is titled Sports Cave OS — DEV; its ordinary Live shell is hidden only on this owner-only editor route.
- The existing V8 workspace/editor modules are rearranged into a compact toolbar, resizable/collapsible left navigator and editing workspace, and one full-height interactive application on the right. Editing mounts immediately and preview starts or reuses its current session. No Edit Page button, old embedded landing screen or repeated draft selection.
- Draft name and saved revision, page selector, Desktop/Tablet/Mobile, Save, Undo, Changes, Tests, History and disabled Publish remain available. Additional preview lifecycle controls and draft/release management are retained.
- Actual route branches, directly called page functions, explicit imports and literal lazy imports produce read-only Python references. Verified grouped route definitions support additional pages. The shared top-bar HTML and existing authorised CSS/JavaScript files are directly accessible; no HTML page is fabricated.
- Alt+click or Select element protects ordinary interaction while selecting verified visual mappings. The existing six sign-in/shared-submit mappings remain the only visual property mappings. Arbitrary elements and Python source remain read-only.
- The existing source editor retains syntax colouring, line numbers, search/find, two-space Tab indentation, wrapping, source recovery and conflict protection. Colouring/gutter rendering is bounded to the visible rows, while the complete editable value is retained. The source pane leaves the application visible.
- Preview keyboard input is batched/queued to preserve rapid text and key order; stale-page queued input is cancelled. Fixed raster click, scroll, keyboard, viewport and page metadata stay inside the existing isolated controller.

## V8 retained

Immutable application IDs and default-selection provenance; worktree/task ownership; DPAPI-protected trust and 30-day expiry; origin checks and short-session renewal; explicit local editing grants and sensitive-operation confirmations; stale-write/hash/revision checks; saved history and Undo; recovery blobs; Release Manager; isolation probes, non-root user, network-none, seccomp, read-only root, bounded resources; pinned container identity/context, persistent hidden relay, cached decoded frames, idle shutdown and Windows startup/recovery.

Valid editing grants are reused only after the existing capability endpoint revalidates them. Browser popup restrictions retain a Connect button; initial/expired editing permission still requires the existing local confirmation. Production authentication is never copied into Docker.

The serial companion now times out idle request connections after five seconds, preventing browser preconnects from blocking requests. Ordinary sidebar clicks wait for a stable application render and report the actual selected page. The synthetic controller invokes the application's existing guarded navigation-completion API with its own rendered route/epoch; it never blindly removes a pending overlay.

## Verification

- 27 focused Python tests: editor permission/allowlist, compare-and-save, Undo/recovery, source provenance, bounded viewport, idle preconnect and retained relay/ownership behavior.
- Four focused Node suites: frame decode/retention, default selection/reconnect correlation, bounded source viewport, and queued preview keyboard ordering/stale-page cancellation.
- Real visible installed Windows Edge with a disposable browser context and isolated V9 task: separate Dev tab; synthetic Live entry fixture stays open; automatic authorised test draft; pre-enrolled test-profile trust reused; existing local editing confirmation retained; editor immediately available; full application; CSS Save/Undo; mapped selection/highlight/Save/Undo; History; device resizing; same container; no browser JavaScript errors. All 1,129 audited Git/Docker launches used CREATE_NO_WINDOW.
- Focused Edge/Docker follow-up: ordinary OS sidebar navigation updates the left navigator; actual custom HTML opens; native HTML edit survives navigation and tab closure/reopening; Undo returns its unsaved buffer to the original source; wrapping, resize/collapse and warm container reuse pass. All 915 audited launches were silent; zero JavaScript errors.
- Actual HTML source save changed the rendered full-application header. Undo restored exact source bytes and the rendered header, without replacing the container. Result: `v9-html-save.json`.
- Existing 18762 companion was rechecked independently: same Windows owner `hello`, logical owner `codex/v8-01a12f62`, task `app-9ca4a85e-b3f4-4c85-b61e-4eb5551d2740`, registry home, interpreter and scheduled action. Existing application revision 6, source hash, automatic default, trust expiry and original unfinished source are unchanged.

## Measurements and limits

Single acceptance samples (not a controlled before/after benchmark): full Edge entry including connection/editing approval and cold Docker render 36.9 s; warm page switch 5.93 s; mapped save-to-preview 6.73 s; warm tab reopen including permission confirmation 13.33 s. Direct runtime cold start 16.35 s; the final exact-image smoke (startup plus synthetic Dashboard navigation) took 20.24 s; real HTML save-to-preview 4.25 s. The preview occupies 1266 × 897 px at a 1600 × 1000 browser viewport. No V9 idle CPU/RAM improvement is claimed. Containers and Streamlit sessions are reused throughout the acceptance flows.

Large whole-file replacement through the browser automation driver's bulk-fill operation timed out on the top-bar template. Short native HTML edits, Save/Undo and recovery pass; large bulk paste performance is not certified. Source viewport rendering was bounded after a problematic QA renderer reached approximately 1.2 GiB. This is not a measured before/after idle-memory claim. Read-only Python excerpts are bounded and explicitly labelled when truncated. Additional visual mappings require separate verified mappings, not broader filesystem access.

## Installation and release boundary

No change was installed into the active Windows companion, its startup task or the existing application worktree. No commits, pushes, merges, deployments or production writes were performed. Edge entry tests used a local synthetic Live-entry fixture and the real isolated OS preview, not the deployed Live entry. Ordinary Edge using the existing 18762 companion cannot receive V9 until a separately owner-approved companion upgrade; the deployed sidebar also remains unchanged until a separately approved application release.

V9 test image: `sha256:5a22bde08670c241dd349f56e374ee5510a58f9f13d077831d1cd9de8746d061`. Built locally from exact V8 image `sha256:a76ad636607432cf763373e321d1151a1936d2df6f152dbbe01ef4badfa1c3b4`; only the fixed controller is replaced. Runtime source pins this exact V9 image ID and fails closed if unavailable. The active V8 image/tag is untouched.

## Files

- `app.py`
- `os_accounts.py`
- `developer_studio_page.py`
- `components/developer_studio/panel.html`
- `components/developer_studio/panel.js`
- `components/developer_studio/panel.css`
- `scripts/studio/draft_ui.py`
- `scripts/studio/dev_sources.py`
- `scripts/studio/preview_runtime.py`
- `scripts/studio/isolation/controller.py`
- `scripts/studio/isolation/DevMode.Dockerfile`
- `scripts/studio/ui/workspace.html`
- `scripts/studio/ui/workspace-local.js`
- `scripts/studio/ui/workspace.js`
- `scripts/studio/ui/workspace.css`
- `scripts/studio/ui/editor.js`
- `scripts/studio/ui/pair.js`

Focused test scripts: `test_dev_mode.py`, `test_source_viewport.cjs`, `test_preview_input.cjs`, the adapted `test_preview_frames.cjs`, `verify_v9_edge.py` and `verify_v9_reopen.py` under `scripts/studio`. Evidence JSON/PNG files are retained under `docs`; the exact runtime-file hash manifest is `docs/v9-runtime-manifest.json`.
