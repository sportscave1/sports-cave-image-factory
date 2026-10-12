# Sports Cave OS V8 — silent Docker and measured performance

Status: **Implemented locally, not deployed.** 13 October 2026, Australia/Sydney.

## Worktree and baseline

Task `20261013-v8-silent-performance`, owner `codex/v8-performance-01a13216`.
Branch `codex/task/core-v8-silent-docker-and-measured-performance-20261013-v8-silent-performance`; worktree `C:\Users\hello\.codex\visualizations\2026\10\12\01a13216-edba-7c20-896a-70f604c44d7e\v8-performance\core`.
The new isolated CORE task uses the existing V8 HEAD `c6b1c82ab51b915bf7d9e31b4b99ce3f1801e4b7` plus all
17 unfinished connection repair files, copied and SHA-256 verified. The original
V8 repair files were rechecked unchanged at completion. The initial long checkout
name exceeded Windows path limits; only this newly created failed task was
recovered into the shorter `core` path, with per-command Git long-path support.
No existing worktree, branch or unfinished source was reset or overwritten.

## Root causes and changes

The inherited connection repair already supplied CREATE_NO_WINDOW on the main
Docker launch calls. Remaining uncovered Windows subprocess paths included Studio
category checks, static verification and its Python child, the VS Code CLI helper,
and the companion runtime verification helper. These now use the same Windows
no-console policy, retaining captured output, errors and timeouts. Intentional
browser/VS Code application windows still open normally. The production preview
paths use argument arrays with no host PowerShell/CMD shell invocation. The `sh`
controller launch is inside the isolated Linux container.

Every frame previously spawned Docker/Python and inspected the named container.
The candidate keeps one bounded, hidden Docker exec relay per active preview,
pins the verified local Docker context and immutable container ID, and checks
the registry task/owner/lease on every operation. Container labels/policy are
verified before startup, before source transfer and before removal. Names cannot
redirect an event or stop to a replacement container. Full negative isolation
and browser probes still run for every new container; no security-probe cache.
The new relay has bounded request/response sizes, a 20-second deadline covering
both writes and reads, bounded stderr, and explicit recovery without replaying
possibly mutating operations. It closes when the preview stops or idles out.

Cold export repeated the complete secret/AST sanitisation pass just to prove
source consistency. The candidate sanitises once, then verifies raw source
SHA-256 and path safety again before exporting. Concurrent edits still fail
closed. Editor delta exports retain their allowlist and consistency checks.

Saving previously reloaded the isolated browser, creating a new Streamlit
session. It now uses Streamlit's rerun operation while retaining the verified
container, process, active session, synthetic database and authentication cookies.
Repeated Preview uses a bounded live health check plus the last valid frame.
Unchanged viewport sizes reuse the current frame. Synthetic login/navigation
no longer take an unnecessary intermediate login screenshot.

The frontend previously swapped img.src before the replacement JPEG decoded.
It now decodes first, retains the last displayed frame while loading, reports
loading/error state and rejects late or disposed-draft frame results. Identical
frames avoid another source assignment. This is separate from native console
flashes. Successful Save Draft refreshes also count as preview activity, preventing
the idle timer from clearing a preview while a user is actively saving.

The installed Streamlit runtime retained disconnected sessions for 120 seconds.
Only the synthetic preview runtime now reclaims disconnected sessions after
10 seconds; active WebSocket sessions and the existing preview idle shutdown
remain intact. No production Streamlit configuration was changed.

## Measured comparison

Same Windows machine, installed Edge, real Docker Linux daemon, synthetic OS
source in the isolated task. Final comparison uses preserved original V8 host
code (`before-final`) and the final candidate (`after-retention`). Two cold
starts per phase, four navigations and four viewport operations; source refresh
is measured twice. Values are medians except the single editor-open/save sample.
The navigation pages were Developer Studio and Image Protection.

| Operation | Before | After | Reduction |
|---|---:|---:|---:|
| Cold startup | 18.93 s | 14.54 s | 23.2% |
| Warm navigation | 3.28 s | 2.88 s | 12.2% |
| Source-to-preview refresh | 4.66 s | 3.24 s | 30.4% |
| Viewport switching | 0.80 s | 0.42 s | 47.7% |
| Editor file opening | 0.19 s | 0.18 s | 8.3% |
| Save + rendered refresh (combined phases) | 5.30 s | 3.89 s | 26.5% |

Warm repeated start: 0.23 seconds, with the same
container and no extra screenshot. The old direct runtime repeated-start operation
rejected the existing lease. Save + refresh adds the measured save and refresh
phases; it excludes the outer hosted connection and local approval gestures.
These are small local samples, not broad performance guarantees.

Idle comparison used ten-second cgroup CPU deltas and the whole host process tree.
Host RSS: 47.1 → 78.5 MiB,
host processes 1 → 3.
The retained relay costs approximately 31.4 MiB
of host memory in exchange for avoiding repeated CLI startup.
Container memory: 585.5MiB / 1GiB → 583.4MiB / 1GiB.
Average container CPU: 3.05% →
3.42% of one core.
Host CPU consumed 0.0000 → 0.0156
seconds during the samples. **No idle CPU improvement or substantial overall
memory reduction is claimed.** Idle resource figures varied across samples.

## Files specific to this task

- `scripts/studio/preview_boundary.py`, `preview_runtime.py`, new `preview_relay.py`:
  silent commands, immutable identity/context, relay lifetime, health and frame reuse.
- `scripts/studio/preview_export.py`: one-time sanitisation and consistency validation.
- `scripts/studio/isolation/controller.py`, new `Performance.Dockerfile`:
  rerun, health, combined synthetic navigation and disconnected-session cleanup.
- `scripts/studio/studio.py`, `verify_companion_runtime.py`: remaining silent helpers.
- `scripts/studio/draft_ui.py`: Save Draft refresh counts as preview activity.
- `scripts/studio/ui/workspace.js`, `workspace.css`, `editor.js`: decoded frame
  retention, loading indicator, disposed-draft protection and reused-preview opening.
- New `test_preview_performance.py`, `test_preview_frames.cjs`,
  `benchmark_v8_performance.py`, `verify_v8_performance_edge.py`; adapted
  `verify_v8_trusted_reopen.py` writes separate candidate evidence.

Other Git modifications are the inherited connection repair, documented separately
in `DEVELOPER_STUDIO_V8_CONNECTION_REPAIR_LOCAL.md` and the baseline overlay receipt.

## Focused validation

- 81 focused Python regression tests passed during implementation, including
  DPAPI/trust, application protection, editor and source-export checks.
- Final 51-test performance/boundary/Studio suite passed after lifecycle changes.
- Four Node protocol suites passed: decoded-frame races, default selection,
  trusted renewal and source/origin/nonce/approval protections.
- Installed **visible Edge** and real Docker: repeated start, page switches,
  desktop/tablet/mobile, Save Draft with rendered heading update, same-container
  refresh, retained frame/loading indicator, killed relay and explicit recovery,
  Stop, editor close/reopen and preserved three-panel UI. Zero browser errors.
- All 354 audited background Docker/Git launches in final Edge acceptance had
  CREATE_NO_WINDOW. This verifies the candidate's launch behavior; historical
  intermittent flashes were not traced to an individual old PID.
- Separate installed Edge fixtures verified authorised draft switching,
  unsaved-buffer recovery, authenticated one-time trust and trusted reconnection
  after full Edge/companion restart, with fixed 30-day expiry and local editing
  confirmation retained.
- All temporary acceptance edits were restored byte-for-byte. Candidate test
  containers were stopped and leases cleared. Original application ID
  `9ca4a85e-b3f4-4c85-b61e-4eb5551d2740` remains clean at saved revision 6 and
  HEAD `c6b1c82ab51b915bf7d9e31b4b99ce3f1801e4b7`. Existing trust enrollments remain valid.
- Git diff whitespace and changed JS syntax checked. Test evidence recorded for
  the new CORE task only.

Evidence: `v8-performance-before-final.json`, `v8-performance-after-retention.json`,
`v8-performance-edge.json/png`, `v8-performance-trust.json/png`,
`v8-performance-draft-switch.json/png`. Earlier measurement passes are retained.

## Scope and remaining limitations

The existing registered companion task/owner/home/port, startup registrations,
application source, edition data and other worktrees were preserved. The current
18762 companion was not repointed to this candidate. Local tests used the new
task and disposable browser profiles; the everyday user profile was left alone.
The separately tagged candidate image is `sports-cave-studio-runtime:v8-silent-perf-01a13216`;
its parent is digest-pinned and existing runtime tags were not replaced. Tests
downloaded no dependency packages. Applying this candidate to the approved
startup registration would require its owner's explicit approval.

Warm navigation still uses actual OS page loads for route parity. The persistent
relay adds modest host memory; cold security probes still dominate some startup
time. A real Windows sign-out/sign-in was not performed. Historical V5 startup
registrations and other owners' code were untouched.

No commits, pushes, merges, deployments, production writes, automatic Update
from Live, service creation/removal, worktree deletion or unrelated feature work.
