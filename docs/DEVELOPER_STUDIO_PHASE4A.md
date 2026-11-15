# Developer Studio Phase 4A — local integration

Implemented in CORE task `20261011-c24ca137`, owner `me/phase2`. No commit,
push, merge, deployment or production operation. Phase 3 evidence remains a
historical acceptance of its original snapshot; Phase 4A has separate evidence.

## In Sports Cave OS

Developer Studio is a first-class sidebar route. Both navigation permissions and
the route renderer require the active configured owner (the existing reporting
owner predicate: `SPORTS_CAVE_REPORTING_OWNER_EMAIL`, then
`SPORTS_CAVE_ADMIN_EMAIL`). Missing owner configuration fails closed; other admins
and workers cannot open it. No account, permission table or deployment setting is
changed. The old Developer settings page is unaffected.

The lazy page provides Live, Development drafts, Editor & preview, and Tests &
releases. Live explicitly says revision/health/GitHub/Render are **not verified**:
no local commit is represented as production. Publishing stays disabled.

The local registry supplies actual drafts in all nine category filters; empty
categories stay empty. Cards show immutable draft ID, task identity, branch,
owner, recorded status, checkpoint, update time and timestamped test evidence.
Evidence is labeled recorded, tied to its snapshot, and is not re-certified by
refreshing the catalog. No continuous Git scan, polling or background service is
introduced. The page never receives worktree source, tokens or local editor URLs.

## Owner-controlled device connection

1. From the allocated Windows task, start the existing launcher:
   `scripts/studio/Studio.ps1 DraftUI -Id 20261011-c24ca137 -Owner me/phase2 -Open`.
2. In the OS Developer Studio page, enter only `http://127.0.0.1:<port>` from the
   launcher. Click Connect local device. Allow the requested popup.
3. In the **localhost** approval window, verify the requesting OS origin and paste
   the private launcher URL. Approve the read-only catalog connection.
4. Select a draft and action in OS. Confirm the exact name/task/owner/branch in
   the local window; follow its private link to the existing editor or preview.
5. Disconnect either side to remove the catalog connection. Pairing expires after
   ten minutes. A disconnected OS page does not affect normal OS navigation or
   discard source work. The companion retains its existing idle shutdown.

Pairing pins the exact opener window, origin and random 192-bit nonce. Only HTTPS
or loopback HTTP requesting origins are eligible, and every origin needs local
approval. Null/sandbox-opaque origins are rejected. Tokens remain only in local
page memory; no browser storage, token-bearing postMessage, CORS exception,
public tunnel or Render endpoint is added. The only wildcard message is the
non-sensitive initial readiness nonce; all catalog/acknowledgment messages use
the approved exact origin. The protocol accepts catalog requests and allowlisted
handoff intents only. The local link is never returned to the remote page.

Same-origin Host/Origin/token checks and frame-ancestors 'none' remain intact.
Catalog discovery validates the initiating task. Every handoff revalidates the
selected draft UUID, owner, Git root and branch. Other-owner drafts are visible
as recorded metadata but not actionable. Another same-owner task gets a separate
on-demand companion port/token; reopening reuses that companion. Parent shutdown
stops owned child companions. File operations still run all Phase 3 allowlists,
CAS stale-edit checks and recovery journaling.

**Secure local handoff is deliberate:** browser mixed-content/local-network,
COOP or sandbox policies may block pairing from some hosted configurations.
In that case use the private launcher locally; do not weaken those policies.
The in-app catalog is the Studio entry point; source editing and raster previews
open locally rather than embedding a filesystem-capable page on Render.
The network-isolated application preview itself cannot reach the Windows
companion. Its offline display is expected. Pairing is separately exercised by
the shipped browser panel on localhost; this is a UI test fixture, not a second
application or proof of deployed HTTPS browser compatibility.

## Editor and previews

Handoffs reuse the existing lazy `mount(panel, transport, showFrame)` editor and
explicit visual mappings / HTML, CSS and JavaScript file allowlists. Edit mounts
the selected draft, View Changes mounts its diff, Preview starts the existing
Docker runtime after its mandatory safety probes, and Open reopens checkpoints.
Save, Undo, Restore Revision, Discard, concurrent-change rejection and recovery
remain Phase 3 operations. Source saves go only to the selected worktree.

Docker isolation is unchanged: no networking, host mounts, credentials, workers
or production databases; synthetic data and bounded raster relay only. Desktop,
Mobile, loading/errors, Stop and Restart remain available in the local preview.
Exactly four new application UI source files are explicitly added to the reviewed
preview export; arbitrary untracked files are not exported. No image rebuild,
new dependency, system installation or Windows configuration change is required.

## Focused verification

- `python -B -m unittest discover -s scripts/studio -p test_phase4a.py`
- `python -B -m unittest discover -s scripts/studio -p test_editor.py`
- `python -B -m unittest discover -s scripts/studio -p test_preview_safety.py`
- `node scripts/studio/test_pairing.cjs` and JavaScript syntax checks.
- Opt-in `python -B scripts/studio/verify_phase4a_browser.py` serves the shipped
  panel as a temporary localhost UI fixture plus the existing authenticated
  companion. It never imports or runs app.py on Windows.

Browser acceptance covered discovery, empty categories, explicit pairing,
confirmed correct-draft Edit handoff and disconnect. Actual Docker application
acceptance covered synthetic sign-in, sidebar route, in-app page at 1280px and
390px, visual Save reaching the real preview, and Undo restoring exact source
hashes. Existing focused editor tests cover source saves, stale conflicts, file
restrictions, undo, restore and recovery. The Phase 3 browser acceptance evidence
is retained rather than repeated or overwritten.

Measured locally: lazy page import 0.445 ms, panel assembly 0.373 ms, inlined panel
8,948 bytes. One preview after navigation used about 779 MiB of its existing 1 GiB
limit; this is a point observation, not a controlled performance comparison.
Ordinary routes import no Studio backend or panel, and no Docker work occurs on
OS startup. No broad benchmark or production performance claim is made.

Exact fingerprint, per-file hashes and final verification results are recorded in
`C:/Dev/SportsCaveWorktrees/.studio/phase4a-acceptance.json`. That machine-local
file is outside shared source. No uncommitted snapshot is an approved release.

## Phase 4B dependencies (not implemented)

Owner review and authorization are still required before any integration/release.
Future work needs verified production revision/health evidence, immutable approved
release candidates, combined CI, explicit owner approval, exact-commit deployment,
worker compatibility and live verification/rollback. Hosted browser pairing must
be tested against the approved OS HTTPS origin and its actual browser policies;
retain the secure local-only handoff when direct pairing is unavailable. No
publishing token or deployment permission belongs in the companion or this page.
