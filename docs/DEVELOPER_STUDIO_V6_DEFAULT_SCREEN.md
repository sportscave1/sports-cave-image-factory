# V6 Editor default screen — local release handoff

12 October 2026. Implemented locally from V6 release commit
`6071943214bff3c6abae7aa2f9bd4d688537b002`. No commit, push, merge, deployment,
production mutation, companion replacement or trust enrolment was performed.

The primary checkout predates V6 and contains unrelated changes. Work is isolated
in task `20261012-default-01a12f62`, owner `codex/v6-default-01a12f62`, branch
`codex/task/core-v6-editor-default-screen-fix-20261012-default-01a12f62`.
Its separate registry is under the parent `studio-task/.studio` directory.
The existing shared registry, registered task owners and worktrees are preserved.
The new task checkout was recovered from an initial sandbox/Windows long-path
failure using per-command long-path support; no global Git setting was changed.

## Result

Developer Studio mounts the existing shared V6 three-panel workspace immediately.
Its centre contains a compact draft selector until a draft is authorised. Drafts
are listed under the left Drafts tab, with assigned-owner lock explanations.
Pages and Files use the same existing V6 catalog and allowlists. Selecting a page
starts or navigates its actual synthetic Docker preview; unsupported selections
stay read-only when switching Properties/Styles/Source.

The toolbar retains Save Draft, Undo, Preview, Tests, History, View Changes and
Discard. Connection details and release tools are available in small header menus.
The OS host sizes this workspace to the available viewport, scoped only to the
Developer Studio page. Preview controls fit in one wrapping row.

Only the last successfully opened draft ID is remembered, scoped to the companion
address. The live catalog must still mark it actionable. Opening requires the
existing secure local confirmation, after which the Editor stays embedded in
Sports Cave OS. Missing/locked selections leave the compact selector in place.
Reconnect and permission renewal preserve the current unsaved editor buffer.
Cancelling confirmation can be retried without repeating companion setup.

## Changed files

Production UI (six files):

- `components/developer_studio/panel.html` — Editor entry, compact menus; old catalog removed.
- `components/developer_studio/panel.css` — bounded shell and connection menu layout.
- `components/developer_studio/panel.js` — eager shared workspace, draft restoration and approval correlation.
- `developer_studio_page.py` — owner-gated, page-scoped host sizing.
- `scripts/studio/ui/workspace.js` — empty selector, Drafts tab, toolbar, actual page navigation and read-only selection state.
- `scripts/studio/ui/workspace.css` — compact shared workspace and selector styling.

Verification:

- `scripts/studio/test_workspace_selection.cjs` — entry/restoration/lock/protocol regressions.
- `scripts/studio/verify_v6_ui.py` — real local HTTP editing in a disposable browser; restoration, recovery and layout checks.
- `scripts/studio/verify_v6_default_screen.py` — opt-in full local OS/Docker acceptance for an explicitly assigned task.
- This report.

The V6 editor save engine, source allowlists, backend ownership checks, trust
protocol, Docker policy and Render topology are unchanged. No dependency was added.

## Successful verification

- `python -B -m unittest discover -s scripts/studio -p 'test_*.py'`: **189 tests passed**.
- All three Node suites passed: `test_pairing.cjs`, `test_trusted_pairing.cjs`,
  `test_workspace_selection.cjs`.
- Disposable Edge UI: default three panels, compact selector, locked-owner
  explanations, local confirmation, Save/Undo/Restore, source edits, delayed-load
  field locking, Discard, tests/history, unsaved reconnect, last-draft restoration,
  locked-draft restoration rejection, cancellation retry and expired-permission recovery.
- UI widths 1440, 1100 and 390: no document overflow; no JavaScript errors.
- Actual assigned draft in the existing hardened V6 Docker image: edit appeared
  in the rendered preview; Undo restored `app.py` byte-for-byte. Selecting
  Developer Studio in the Pages list navigated the real synthetic OS and showed
  the new three-panel entry screen. Unsupported inspection stayed read-only.
  Only this test's preview was stopped afterwards.
- Runtime checks passed: no network, no credentials, no host mounts, no published
  ports, non-root user, read-only filesystem, bounded resources and negative probes.
- JavaScript/Python syntax, `git diff --check`, and
  `python scripts/validate_render_topology.py` passed.

The sandbox initially denied disposable test directories and Docker access.
The same local tests completed successfully with tool-approved execution outside
that sandbox; no application permission or isolation boundary was relaxed.

Single-run local measurements: default shell **0.152 s**, connected fixture Editor
**4.806 s** (including deliberate cancellation and retry), cold Docker preview **29.272 s**,
save plus explicit preview verification **10.025 s**. The last figure includes an
extra verification request; it is not a like-for-like refresh benchmark. No new
Docker startup or save-speed improvement is claimed. Generated panel HTML grew
from 58,246 to approximately 60,300 bytes, with no new library or polling loop.

Evidence lives beside this task's registry: `default-unit.log`, `default-ui.json`,
`default-runtime.json`, and screenshots beginning `default-ui-` / `default-runtime-`.
`default-runtime-os-route.jpg` shows the actual Sports Cave OS → Developer Studio
screen inside the isolated runtime; `default-runtime-edited.png` shows a real saved
edit and its preview inside the embedded Editor.

## Release readiness

Ready for a focused production release review. Release only the six UI files above
with their tests/documentation against the then-current production base; inspect
any overlap if that base has advanced. The existing V6 companion can serve the
embedded Editor: these changes require no companion reinstall, owner reassignment,
new service, migration or Docker image rebuild.

Production and personal-browser HTTPS acceptance have not been run for this
uncommitted change. Separate user approval is required before creating a release
commit, pushing or deploying. After an approved release, verify authenticated OS
navigation and the existing trusted companion handoff in the user's browser.
