# V9 code-first Developer Studio - local implementation

Status: Implemented and tested locally. Not installed in the Windows companion and not deployed.

## Workspace and preservation

CORE task `v9-codefirst`, owner `codex/v9-codefirst-01a13216`, branch `codex/task/core-code-first-v9-codefirst`, based on verified Phase 2 commit `7c6d42126b99a1d9a96a822d60f8af4a8b7c500d`.
No earlier in-progress Save All implementation was found in registered CORE worktrees; the existing Phase 2 code had one active-file buffer. All existing worktrees were preserved.

The existing 18762 companion still runs `v9-performance-phase2-20261013` under `SportsCave-Studio-20261011-7192d493`, Windows owner hello, logical owner codex/v8-01a12f62. Its identity, interpreter, registry home, startup action, DPAPI trust/origins/30-day expiry and automatic application ID remain unchanged. The real application remains revision 8, with revision 6 retained in history. Its source and unfinished V8 repairs were verified unchanged. No Live, GitHub, Render, Shopify, customer-data or edition-number operations were performed. No commits, pushes or merges were made.

## Source-first interface

Resizable left workspace contains an actual folder explorer, selected-page source list, complete source editor and multiple tabs. Right side retains the real isolated interactive OS. Toolbar has one Save Draft / Save All action, dirty-file count, Undo/Redo, Changes, History, Tests and disabled Publish. Properties/Styles are no longer primary controls. The legacy editor/backend remain for compatibility.

Full-file source is exposed through fresh owner/worktree validation and explicit source permissions. No 60,000-character excerpt is presented as an entire file. App/page Python is read-only; protected authentication, account, credential, database/configuration and allocation modules are withheld from whole-source export. Hidden, traversal, linked/reparse, hardlinked and arbitrary filesystem paths remain forbidden. Credential scans apply before source export and saving; Copy Source also checks pending text. There is no AI API integration or automatic transmission to ChatGPT.

Editable real sources:

- `components/sports_cave_top_bar/index.html`
- `mockups_page.css`
- `orders_page.css`
- `components/session_recovery.js`
- `components/sign_in/presentation.html`
- `components/sign_in/presentation.css`
- `signin_presentation.py`

The Sign-in HTML/CSS are genuine extracted presentation used by app.py. Python settings are limited to literal TITLE, DESCRIPTION, BRAND and three bounded COLUMNS values; imports, calls, executable statements and other names are refused. Authentication/form handling after auth_notice was compared by AST to the original and is identical. Existing responsive rules and style ordering are retained. Supported Sign-in inspection validates exported dependency hashes and opens the actual Python/CSS source location.

The editor provides syntax colouring, line numbers, indentation, Find/Replace, complete Copy Source, Select All, wrapping, bounded viewport rendering, file-specific local Undo/Redo and saved history. Original CRLF/LF format is retained on Save. Clipboard denial selects the full file and provides a Ctrl+C gesture fallback.

## Multi-file buffers and Save All

Each draft/file owns its own buffer, original hash, revision, undo/redo and scroll/selection state. Switching files, tabs and OS pages retains every buffer without discard prompts. Source editing and cached source switching remain independent of preview loading. Recovery is namespaced by immutable draft ID and origin, throttled at 300 ms, and flushed on normal beforeunload/pagehide/hidden transitions. Only explicit Discard prompts to destroy buffers.

One Save All validates the initiating owner/grant, exact worktree, file permissions, every original hash and the draft revision. All files pass safety/syntax checks before replacement. Preimages and postimages are durable content-addressed blobs. A prepared journal rolls back on failure or interrupted restart; a durable committed journal finishes one revision exactly once. All target hashes are checked before recovery, so foreign edits are not overwritten. One revision contains the complete changed-file set and per-file history tied to one batch ID. Readers through Studio take the registry lock; filesystem replacement itself is per-file, not an OS-wide multi-file atomic primitive.

After commit, the verified source delta transfers to the existing container and one Streamlit rerun updates the actual application. The exact Phase 2 image is retained; its header-reinstall hint is kept compatible even with seven changed files. Docker isolation, persistent relay, synthetic login/data, session/container reuse, silent process flags, route/epoch validation, idle shutdown, trust and Release Manager foundations remain in place.

## Tests and measured scope

42 focused Python regressions passed: source journal/conflicts/recovery, legacy editor, HTTP boundary authentication and Phase 2 grant/expiry/ownership validation. Native Node buffer tests passed for independent buffers, Undo/Redo, CRLF handling, async file targeting and bounded large-file history. Syntax checks and git diff --check passed.

Real Windows Edge used a separate disposable profile and an isolated sanitised copy of the actual current revision-8 draft. No normal-profile cookies or production credentials were transferred. Checks passed for full HTML/CSS/JS and read-only Python, complete clipboard copying and denied-permission fallback, three independent dirty files across page switches, per-file Undo/Redo, normal beforeunload close/reopen recovery of all files, one-button coherent revision, real preview update, history, large replacement paste, executable Python rejection, external-write conflict rejection with buffers retained, Desktop/Tablet/Mobile, explicit confirmed Discard and restored-source reopening. Browser error list was empty. A separate real-runtime check saved all seven authorised files in one revision, rendered a Python setting change, verified Sign-in source inspection and retained the same container. Every acceptance source byte was restored; only the isolated QA history advanced.

The pinned Docker image remains:
`sha256:d74525e5ce7bd49a602399f6ac1e16476b9158bfaab00bb00703b42a85815baa`

All mandatory runtime and browser probes passed: non-root, read-only root, dropped capabilities, no-new-privileges, seccomp, loopback-only/no outbound route, no host files/credentials/bind mounts/public ports, bounded resources, native libpq/TCP/HTTP/SMTP/IMAP/UDP/IPv6/DNS denial and browser fetch/navigation denial.

Final browser timings (one complete run; not before/after medians):
- editor_available_seconds: 3.148735700000543
- cold_ready_seconds: 45.684804599994095
- navigation_seconds: [4.40485500000068, 3.9017452000116464, 3.4152812999964226]
- reopen_recovery_seconds: 2.4629681000078563
- save_all_to_preview_seconds: 7.308585499995388
- large_paste_seconds: 0.042327200004365295
- large_typing_median_ms: 3.7999999821186066
- large_typing_p95_ms: 5.9000000059604645

Separate all-seven backend Save-to-rendered-frame: 2.8031781000026967 seconds (single sample). Browser Save All includes transport, source re-reads and UI work and varied across successful runs; no comparable speedup is claimed. Large-file typing median/p95 are 100 input-handler measurements, not 100 complete human keystroke round trips. Cold Docker preview remains a genuine long operation; code becomes available beforehand.

## Limits and release readiness

- Current limits: 2 MiB per file, 8 MiB / 32 entries per save, explicit edit allowlist, 100 local inverse edits / 4 MiB history per file. Arbitrary Python execution and filesystem editing are not granted.
- Browser localStorage quota can limit very large multi-file recovery. A prominent warning keeps buffers in memory and prevents draft switching when recovery cannot persist. Normal recovery passed; hard process kill can lose the last ~300 ms of pending recovery writes.
- Legacy visual recovery keys remain untouched. New code-first recovery uses a separate namespace; migration of old visual-property buffers is not implemented. Existing installed V8/P2 functionality is unchanged.
- HTML/CSS checks are structural plus inline-JavaScript syntax checks; they are not full semantic validation of every browser behaviour. Source scans are safeguards, not a replacement for owner review before sharing source.
- Unsaved preview execution is not implemented; Save All refreshes the secure runtime. Publishing remains disabled. Applying this interface/presentation change to the real application copy or installing its companion runtime requires separate approval.
- One attempted broad restore of a failed long-path QA checkout was rejected by automatic approval review. That checkout was left untouched; a fresh shorter QA copy was created with per-command long-path support. It and the successful QA worktree are retained.

Local review-ready source and exact manifest are retained. The active companion and production have not been changed.

## Exact implementation files
- app.py
- developer_studio_page.py
- components/developer_studio/panel.js
- components/sign_in/presentation.html
- components/sign_in/presentation.css
- signin_presentation.py
- scripts/studio/source_editor.py
- scripts/studio/editor.py
- scripts/studio/dev_sources.py
- scripts/studio/draft_ui.py
- scripts/studio/preview_export.py
- scripts/studio/preview_runtime.py
- scripts/studio/ui/code-editor.js
- scripts/studio/ui/workspace.js
- scripts/studio/ui/workspace.css
- scripts/studio/ui/workspace-local.js

Acceptance evidence: codefirst-acceptance.json, codefirst-runtime-check.json, codefirst-qa-copy.json, codefirst-ready.png and source-related-tests.log.
