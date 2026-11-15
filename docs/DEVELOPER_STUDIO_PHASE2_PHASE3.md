# Developer Studio: local previews and editing

Status: implemented locally, with focused verification evidence in the local `.studio` directory. Nothing is committed, pushed, merged or deployed. Phase 4 publishing is not implemented.

## Open the existing task

From the assigned task worktree, run:

```powershell
.\scripts\studio\Studio.ps1 DraftUI -Id 20261011-c24ca137 -Owner 'me/phase2' -Open
```

Use this task-local launcher while these changes are uncommitted. The parent-directory Phase 1 launcher still targets the committed setup revision. Keep Docker Desktop running with its local Linux engine. No further Windows setup is required on the verified computer.

The private session link authenticates the companion. Do not share it. The interface shows the actual task, branch, owner and worktree. Create/open its named draft, choose explicit checkpoint files, then Start Preview. Stop Preview releases its runtime; Restart Preview creates fresh synthetic data. Reopen through the same task and owner to recover saved revisions. A second task needs its own worktree, owner allocation and launcher; two active tasks must never share a working directory.

## Enforced preview boundary

Actual Streamlit application source executes only after the exact container passes isolation checks. Docker uses `--network none`, non-root UID/GID 65532, all capabilities dropped, no-new-privileges, a default-deny seccomp profile, read-only root, private PID/IPC namespaces, no mounts, no published ports and no host Docker socket. Only a generated source allowlist is streamed into private tmpfs. Host environment, Git metadata, credentials, customer data, caches and databases are not mounted or copied. The known default authentication literal is replaced only in the exported source by a synthetic credential. Unknown suspicious credential literals cause export failure.

Each preview gets its own synthetic PostgreSQL database, Streamlit process, Chromium browser, tmpfs and cache. Production launchers, migration runners, webhook entrypoints and workers are excluded or import-blocked. Read mocks return empty synthetic provider responses; mutations and unknown providers fail. Network isolation also applies to native database/email clients, subprocesses and descendants, independently of Python guards. Normal application table initialization can write only to the synthetic database.

The application browser also runs inside the container with Chromium sandboxing enabled. The host receives bounded JPEG frames and sends bounded input events. This prevents application JavaScript from using the host browser's network or credentials. No app HTML, iframe, script or arbitrary source is executed by the companion page. HTTP requests require a session token and exact localhost Host/Origin. The companion accepts only fixed development operations, never shell commands.

The local Docker daemon, Windows account, companion implementation and reviewed image are trusted. This is a development isolation boundary, not protection against a compromised Docker daemon or administrator. The secret scanner is a focused safeguard, not a proof that arbitrary new source contains no secrets; expanding the source allowlist requires review.

## Runtime lifecycle and resources

No previews run by default. Each runtime is capped at 1 GiB memory, one CPU, 192 processes and 512 MiB private tmpfs. The companion shuts down after 15 minutes without authenticated activity and removes its own preview. A container also has a hard 15-minute lifetime as a crash backstop; use Restart Preview if an active session reaches that limit. An abandoned registry lease is not reassigned automatically: inspect the exact owning task/container before manual recovery.

Editor Save exports checked source again and restarts only Streamlit inside the same boundary, retaining the synthetic database. It reloads the preview automatically and resets the browser session to sign-in. Full Restart resets the entire synthetic runtime. Refresh image captures current rendering. Desktop/mobile controls use 1280/390-pixel viewports. There is no unattended screenshot polling or production startup hook.

The cached runtime image is approximately 3.2 GB, largely the existing application requirements plus PostgreSQL/Chromium. Verified two-preview startup was approximately 16-18 seconds per preview; the final measured memory was approximately 508-533 MiB each (earlier runs reached 829 MiB). Editor save-to-preview measured 13.9 seconds. Current run timings are recorded in `.studio/phase2-preview-acceptance.json` and `.studio/phase3-editor-acceptance.json`. The editor itself uses browser-native controls and a lazy ES module, with no additional frontend dependency.

Build the runtime only when its reviewed files/dependencies change:

```powershell
docker build -f scripts/studio/isolation/Runtime.Dockerfile -t sports-cave-studio-runtime:phase4d-login-369a5c73 scripts/studio/isolation
```

Build context contains infrastructure only, never the application or its secrets. The base image is digest-pinned. Existing requirements are reused; their broad version ranges mean future builds can resolve different dependencies and must pass acceptance again. Startup resolves an immutable local image ID and probes that exact image before application execution.

The Chromium seccomp profile comes from the official Playwright v1.63.0 profile, with `chroot` added for its non-root user-namespace sandbox; its exact SHA-256 is checked by the launcher. No host firewall or Windows configuration was changed. References: [Docker network none](https://docs.docker.com/engine/network/drivers/none/), [Playwright Docker sandbox guidance](https://playwright.dev/python/docs/docker), [upstream profile](https://raw.githubusercontent.com/microsoft/playwright/v1.63.0/utils/docker/seccomp_profile.json).

## Editor scope and recovery

Edit Draft lazy-loads the editor. Visual mappings support the sign-in heading, description, brand label, panel, mobile panel and shared submit-button styling/text. Supported literal properties include colours, typography, spacing, borders, dimensions and flex alignment. Unsupported mappings, CSS URLs/functions and raw Python editing are refused. This deliberately does not promise arbitrary Streamlit visual editing.

Authorised source editing is limited to:

- `components/sports_cave_top_bar/index.html`
- `components/session_recovery.js`
- `mockups_page.css`
- `orders_page.css`

Source editing provides basic syntax highlighting, line numbers, search, local undo and unsaved-change warnings. Save changes the actual selected worktree. View Changes shows its source diff. Undo restores a saved preimage; Restore Revision restores the chosen saved image. Both create a new history entry. Discard Unsaved Changes reloads the file without writing it.

The service validates owner, Git root, branch and allowlisted path on each operation. Traversal, sensitive files, symlinks/junctions and hardlinks are refused. Save compares the loaded content hash and draft revision before writing; stale edits fail without overwriting the other change. Registry updates are serialized and source replacement is atomic, with durable preimage/intent records for interrupted-save recovery. This is optimistic conflict detection: arbitrary external editors must still cooperate with task ownership; do not run concurrent editors intentionally against the same file.

Checkpoint recovery produces a separate copy and never overwrites work. Editor revision recovery intentionally updates only the selected allowlisted file after its conflict check. Uncommitted drafts remain release-ineligible. Ready for Review continues to use the Phase 1 tested/clean-commit rules; Phase 3 is Tested locally and Ready for Review against a recorded working-file snapshot. The task remains Tested under the existing clean-commit integration gate; release/integration eligibility remains false.

## Verification and limits

Run focused offline fixture tests:

```powershell
$env:TEMP = 'C:\Dev\SportsCaveWorktrees\.studio'
$env:TMP = $env:TEMP
python -B -m unittest discover -s scripts/studio -p 'test_*.py'
```

Explicit real-runtime acceptance scripts are `verify_preview_runtime.py` and `verify_editor_runtime.py`. These use the existing assigned task and a separate registered verification task; they are not automatically run by test discovery. The editor acceptance makes reversible test edits and restores their original bytes through editor history.

Negative probes cover HTTP/DNS/TCP/UDP/IPv6, native PostgreSQL/libpq and libc connections, SMTP/IMAP, credential discovery, read-only filesystem, subprocess/child/grandchild network access, browser fetch/navigation, provider mutations and worker imports. Positive-control canary testing prevents treating an unreachable test destination as isolation proof. Two real previews validate independent ports/databases, synthetic sign-in, owner/workspace isolation, mobile rendering, restart, stop and idle shutdown.

Scope limitations: synthetic fixture data is minimal; all business modules and production routes are not certified. External assets/integrations fail or return empty synthetic data. Some module workflows need additional synthetic fixtures. Raster interaction is less convenient than a direct webpage and does not provide native accessibility semantics for application content. No production performance benchmark or all-module regression suite was run. Ordinary application source is restored after editor demonstrations.

## Phase 4 integration contract

Developer Studio remains a future dedicated section inside Sports Cave OS. This on-demand localhost page is a development harness, not a separate desktop application. `ui/editor.js` exports `mount(panel, transport, showFrame)` so an in-app section can lazy-load the same component. The companion retains authenticated filesystem/container operations; the host application must not gain arbitrary filesystem or Docker access. Phase 4 must supply an explicit local-companion connection/authentication flow and preserve its ownership and file restrictions.

Publishing, production credentials, release merging, GitHub/Render operations, live data, visual editing of unmapped components and delegated multi-user security remain outside this phase. No release is eligible merely because a draft preview works.

## Changed infrastructure and verification record

The existing `Studio.ps1` / `studio.py`, `drafts.py`, `draft_ui.py` and draft UI are reused. New preview code is `preview_boundary.py`, `preview_export.py`, `preview_runtime.py`, and the files under `isolation/`. New editor code is `editor.py`, `ui/editor.js`, and `ui/editor.css`. Focused coverage is in `test_preview_safety.py`, `test_editor.py`, the extended `test_draft_ui.py`, and the two opt-in `verify_*_runtime.py` scripts. The earlier blocker report remains unchanged; the foundation guide now points to this current guide.

Latest checks: 78 Python tests passed in 8.593 seconds; Studio Python syntax, both UI JavaScript syntax checks and Git whitespace checks passed. Two actual previews passed the critical negative isolation checks, independent synthetic data, owner/lease restrictions, mobile rendering, restart and idle shutdown. Real editor acceptance verified visual rendering, frontend source transfer, automatic refresh, stale-save refusal, allowlists, save/reopen and exact undo/restore. Test edits to application source were restored byte-for-byte.

Original repository preservation: main branch, HEAD and index matched the Phase 1 baseline; all 22,474 baseline file hashes matched. Historical Phase 2 preflight report hash also matched. Runtime evidence and screenshots remain outside source control under the shared local `.studio` directory. The extra registered CORE preview-verification worktree is retained for explicit review/cleanup, with no feature changes.

Final browser acceptance completed on 11 October 2026 in a fresh authenticated session. In-page confirmations passed cancel/accept, mapped Save, saved Undo, Restore Revision with unsaved input, visual/source Discard, stale-edit refusal and desktop/mobile layout checks. All task working files matched the pre-test snapshot after recovery. See [Phase 3 acceptance](DEVELOPER_STUDIO_PHASE3_ACCEPTANCE.md). The earlier browser limitation is closed.
