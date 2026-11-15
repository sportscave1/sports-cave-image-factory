# Developer Studio V6 — local acceptance

Task: `20261012-e16f6570`, owner `me/studio-editor-v6`.
Branch: `codex/task/core-developer-studio-v6-lightweight-os-editor-20261012-e16f6570`.
Base: `fecab25fb01fb3cb4e4e783c00093be517676ac5`.
The task registry records the exact accepted V5 uncommitted dependency and file hashes.
No occupied worktree was modified. The V6 implementation is uncommitted, not live.

## Everyday workflow

Sports Cave OS → Developer Studio → Development drafts → Edit an authorised draft.
Confirm that exact draft in the existing local approval window once. The editor then
stays inside Studio: Pages / Drafts / Files on the left; actual synthetic OS raster
in the centre; Properties / Styles / Source on the right. No private URL copying.

Choose an OS page and Preview. Non-login pages use the existing synthetic sign-in.
Inspect selects only explicitly mapped components. Edit a property or an authorised
frontend file, Save Draft, then View Changes. Undo, Discard and revision Restore use
the existing compare-and-save engine. Tests displays recorded evidence, never an
invented current result. Draft selection is retained across these controls.

Desktop, Tablet (820px) and Mobile controls resize only this isolated browser.
Drag or keyboard-resize panel separators on desktop. On narrow screens, navigation
and properties collapse into closable panels. Preview occupies the remaining space.
Back to Drafts stops the selected preview. Other idle previews retain the existing
15-minute shutdown. There is no continuous Git scan or screenshot loop.

## Security and connection

The existing 127.0.0.1:18762 companion remains the production device endpoint.
V6 changes have NOT replaced its currently running V5 code or Windows startup action.
Existing trust, profile cookies, task owners and startup settings are preserved.

The hosted bundle contains static editor code only. A locally approved editor grant
is scoped to one registered draft and expires after 15 minutes of editor inactivity.
Its capability and session token stay in the exact-origin local bridge. The OS browser
sends bounded, correlated RPC messages; the companion independently checks owner,
worktree, allowlisted action/path, expected source hash and expected draft revision.
Disconnect revokes the grant. Resume editor renews permission without replacing
unsaved text. File/target changes are blocked during a pending save.

The companion still has no CORS, public listener, remote shell or arbitrary file API.
If a browser blocks the embedded module/bridge, Open secure local workspace uses the
same V6 module at the authenticated `/workspace` route. The old root checkpoint UI
remains available. Do not weaken CSP, origin checks or popup policies to force embedding.
The newly embedded V6 workflow has not yet been accepted over hosted HTTPS.

Application execution remains inside the verified Docker boundary: network none,
no host mounts or published ports, non-root, read-only filesystem, bounded tmpfs,
CPU/memory/PIDs, Chromium sandbox and pinned seccomp. Only screenshots and bounded
inspection metadata leave it. No caller-supplied JavaScript, selector or URL can run.
Inspection of a stale source snapshot becomes read-only until refreshed/restarted.
Application credentials are synthetic; workers, webhooks and migrations stay blocked.

## Editing support and limits

49 real OS page entries are statically discovered from the selected draft's page
registry (plus Sign in), without executing its Python. These are OS pages, not
Shopify storefront templates. Some data-heavy pages may show synthetic empty/error
states because real integrations are intentionally unavailable.

Current explicit visual mappings are the sign-in heading, description, brand label,
container, mobile container and submit control. The submit style is shared with
other form-submit buttons; its label edit is the mapped sign-in label. Unsupported
OS elements are read-only; source locations are never guessed. Python is not a
free-form editable file. Mapped excerpts show verified app.py line numbers.

The existing source allowlist is unchanged: top-bar HTML, mockups CSS, orders CSS and
session-recovery JavaScript. HTML/CSS/JS editing includes search, highlighting, line
numbers, unsaved warnings and history. Arbitrary new files/pages are not enabled.
After external Codex changes, Restart performs a full validated export. Editor Save
incrementally exports only its saved file and reloads the current isolated session;
synthetic database contents survive. Preview-only invalidation refreshes the two cached top-bar/recovery assets; production caching is unchanged. Restart deliberately resets synthetic data.

## Local evidence, 12 October 2026

- 79 focused Python checks: editor, owner/HTTP, preview/export, V6 scope and companion.
  The expected handoff path was updated to `/workspace`; its focused check was rerun.
- Three Node suites: exact origin/opener/nonce, selected-draft capability/revocation,
  V5 trust renewal and selected task routing/locks.
- Disposable headless Edge 155.0.4283.45: embedded editor through the real local bridge;
  visual/source Save, Undo, Restore, Discard/Keep editing, history, test evidence,
  unsaved reconnect, 1440/1100/390 widths, no browser JS errors.
- Actual V6 worktree + isolated Docker: mapped click and exact source location;
  visual change rendered, source label visibly changed in the selected preview after a cached load, stale save denied,
  file restrictions, synthetic DB retained, Desktop/Tablet/Mobile, synthetic login,
  actual Developer Studio route, Stop. All tested source restored byte-for-byte.
- HTTP/native libpq/native socket/DNS/SMTP/IMAP/child-process and credential/mount
  isolation probes passed for the actual V6 image before application startup.
- Actual local V6 canvas rendered the Docker raster and its mapped highlight correctly;
  tablet/mobile controls and stopping worked. No personal browser profile was operated.

Final recorded runtime: 19.314s cold preview start versus prior 18.472s. Earlier V6
acceptance runs ranged down to 17.941s; no reliable cold-start improvement is claimed.
Save-to-current-preview 4.453s versus 14.482s (about 69% faster). Warm canvas open 3.417s. Static hosted panel build about 2.2ms, ~58 KB bundle.
These are local single-run acceptance measurements, not a benchmark guarantee.
Normal app.py and navigation entry code are unchanged; assets load only in Studio,
and editor modules are instantiated only after selection and local confirmation.

Machine-specific evidence and screenshots live outside source control in the local
Studio registry directory: `v6-editor-runtime-e16f6570.json`, `v6-ui-e16f6570.json`,
`v6-canvas-e16f6570.json`, and `v6-acceptance-e16f6570.json`.

## Release gates

Current GitHub main was read-only verified as `a1f8c3c55778aa27ff21310cbcf5383810992b48`.
It already contains V5 commit 506d7ae. Do not replace main with this older task base.
Untracked V5 files in this task are real dependency files, NOT deletions; use the
acceptance file manifest, not a naive `git diff origin/main` deletion list.

1. Owner authorises the focused local handoff commit after reviewing this change set.
2. Existing RELEASE workflow integrates only that approved Studio revision with the
   then-current main, explicitly reconciling already-deployed V5 files. Preserve all
   other live changes and active task worktrees. Run focused combined checks and
   app/worker compatibility, preserving production service identity/configuration.
3. Upgrade only the companion runtime implementation in a controlled idle window,
   retaining port 18762, assigned owners, DPAPI records, cookies and startup policy.
   Do not edit the occupied UI/UX or V5 worktree and do not silently transfer ownership.
4. Verify the new embedded V6 editor under actual hosted HTTPS/desktop browser policy,
   or retain the authenticated local fallback. Existing V5 trust acceptance alone
   does not certify V6's new editor transport.
5. Obtain owner approval for the exact immutable RELEASE commit before pushing or
   deploying. The current dirty task cannot be marked Ready for Review/Approved by
   the registry. Real Publish remains disabled throughout.

Remaining master-plan work: broader reviewed component mappings (including iframe
components), production-grade trusted publishing executor, scoped VA permissions and
release monitoring/recovery. This change does not enable arbitrary visual Python edits,
production data previews, automatic publishing or unaudited file access.
