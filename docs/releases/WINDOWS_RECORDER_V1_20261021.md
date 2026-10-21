# Windows Recorder V1 release candidate — 21 October 2026

The owner explicitly authorized final checks, Git publication, deployment to the
existing Render primary and updating the installed Windows helper/companion.
This supersedes the local-only boundary for this release only. Future releases
still need fresh authorization. Task: `20261020-ff6cc91d`; owner:
`codex-windows-recorder-release-01a1589a`.

Current production main was merged without conflict, preserving its Edition Ops,
Product Uploads and advertising changes. No Render topology, database migration,
Photoshop preference, source approval, job journal or customer automation setting
is changed by the recorder release.

## Accepted behavior

- Physical Edge/Notepad text and taskbar transitions; durable save, restart and
  playback with actual values checked and immutable definitions retained.
- Physical scroll, checkbox, selection and menu playback; final Controls 21 run
  `099ff3db-bdf6-498a-b791-1fa47cbce9ad` completed 4/4, every step verified,
  no pending action, and all eight saved definitions unchanged.
- Physical Product Uploads embedded Copy with exact clipboard verification;
  Generate 21 run `eb2fc8ac-0eac-401e-88f3-4f9574534b04` completed 2/2 after
  observing a fresh working state and applied result acknowledgement.
- Emergency Stop, manual intervention, Pause/Resume, protected input exclusion
  and disconnect recovery. Unknown effects are preserved, never automatically
  repeated. General Invoke still requires an application-specific postcondition
  to report success.

Native SHA-256:
`c7399e7ff115cdf979d753814c14b46bb69fa958745830f1ab3e75e3b4ecfe8b`.
The signed-off physical candidate is reused without recompilation.

## Download and update

`recorder-releases/windows/SportsCaveTaskRecorder.zip` is the exact reviewed x64
Windows archive, not a Linux-generated replacement. Archive SHA-256:
`c01313e53f6314de49818136e563c89ceb63f2a752fa3e7536d568b51e39bff3`.
Manifest SHA-256:
`b1b1cb2ec52a9ce0752a32bbf726d016a2804fe888d263e1035522826547868e`.
The authenticated setup route validates the archive before serving it. An
explicit configured package path retains precedence. No recordings, credentials,
receipts, profiles or recovery archives are shipped.

The Windows installer prepares and health-checks a separate pinned environment,
switches code only when the current recorder is idle, and retains the previous
release. Data remains in TaskRecorderV1. Recorder rollback selects previous code
without replacing data. Broader companion updates use a new immutable Git export
and preserve the existing startup identity, triggers, settings and job stores.
The first real legacy update exposed a Windows connection reset during shutdown
confirmation. The installer now continues polling after that reset and switches
only after connection refusal proves the listener has exited. A focused regression
checks that reset alone cannot authorize activation. An exclusive recorder-lock
check also proves that an old helper has fully exited when Windows times out on
its stale connection. A held process lock prevents that offline path. All seven
package checks pass, including the actual Windows lock behavior.

## Validation and remaining limits

Combined checks: 74 focused recorder/relay/component Python tests and six
subtests; both JavaScript component checks; 22 native generation policies;
six native provider/overflow checks; valid canonical Render topology. The current
main preparation geometry/resolution checks pass (34 tests, one skip).

Mixed monitor DPI was not measured; the two-monitor trial reported DPI 134.
Arbitrary unsupported menus and buttons remain unsupported or uncertain. Native
provider faults are covered by isolated fault checks, not induced in customer
applications. General coordinate playback is never used. Sustained-load and
memory-leak claims are outside the short idle/record/play measurements.

This report describes the prepared candidate. Actual live deploy ID/revision,
HTTP health, authenticated package download, installed capability/connection and
data-preservation evidence are recorded in Studio runtime `live-release/` and
the final release report after those actions complete. Deployment requests or
installer exit alone do not establish success.
