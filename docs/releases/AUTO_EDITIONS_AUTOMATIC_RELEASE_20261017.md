# Automatic technical Auto Editions release — 17 October 2026

Owner authorised this release, feature activation, eligible backlog reconciliation
and an idle-only Windows Companion handoff. Baseline: c8e6688f. Release task:
20261017-60eb7469; source task: 20261017-b660fa07.

Includes the completed automatic technical TEST-readiness implementation described
in ../AUTO_EDITIONS_TECHNICAL_FLOW_LOCAL_20261017.md. The manual artwork gate is
removed only under AUTO_EDITIONS_TECHNICAL_FLOW_ENABLED=true. Technical validation,
source identity, durable uploads, generation fences, audit and supplier restrictions
remain mandatory. No allocation, certificate or supplier activation is introduced.

The source report records the pre-release local-only boundary; the owner's later
explicit release instruction authorises this release. Runtime activation and live
results must be verified separately and are not implied by this document.

Inventory: earlier Bulk Review, Worker Health, reset, download-feedback, email and
colour-policy updates are already incorporated in main. Historical dirty prototypes
are superseded; active colour/template work and pending PSD repairs are excluded.
All task worktrees remain intact. Detailed comparison evidence is retained locally
under output/release-auto/task-inventory.json.

Release validation caught and corrected a Windows CRLF migration checksum mismatch.
The mirrored SQL files use LF and the reviewed deployment hash is the normalized
UTF-8 text hash 07cad75344b5df4d522a2b161e7093bf109d20eebf8961d477f347dd2cd4c7e3.
Integrated checks: 86 passed, one optional native benchmark skipped, one checksum
failure subsequently corrected. Migration/technical rerun: 31 passed in 54.35s.
Source verification: 212 passed, one optional native benchmark skipped; technical
suite 30 passed; three additional claim/package/checkpoint checks passed.

Existing primary service identity and supporting service topology are unchanged.
The feature uses the existing preparation worker's discovery loop. Existing
Cloud Ready and deliberate deferred/excluded rows are protected. Maintenance
pause 2348 belongs to the concurrent template task and must not be overridden.

Companion installation must use the committed revision, preserve authorisation and
colour configuration, wait for an idle checkpoint, and verify Photoshop/Dropbox
process identity and job journals remain unchanged across the handoff.
