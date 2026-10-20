# Product Uploads colour repair and companion release

Task `20261019-2a576331`, owner `codex/companion-speed-20261020`.
Continue the registered companion-speed worktree/branch. User authorised commit,
push and deployment on 20 October, with further speed optimisation paused until
Product Uploads works in production. Earlier local-only restrictions are superseded
for this release, not for unrelated active work or customer backlogs.

## Diagnosis

Current source: `Pinstripe Immortals - Ruth & Mantle.psd` under
`/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/`.

- File ID `id:u1tYiAa2O-AAAAAAAACGzQ`.
- Revision `0165e3b47576fc1000000036d367e13`.
- Dropbox content hash `ac5aa7d68a7265b76e22a95be0d3e684995599229d2c90c64d00f7927288e013`.
- Local/source SHA-256 `ec598df55adbb48e0b2821b430121cf87663e7e4b71ab49a457c84fef3c57d24`.
- 193,732,129 bytes, RGB8, 2835 x 2004, genuinely **no embedded ICC**.
  Metadata inspector and exact local Dropbox hash agree; this is not an inspector
  false negative or a bandwidth failure.
- Latest failed Product Upload workflow `06251083-2675-41c2-b379-8f8ecd1fe254`;
  earlier same-source workflows `0d889916-bdf7-4bfc-a49f-d42146ef81c7` and
  `314760e8-a93e-48b0-b08f-f61cd3648dde`. Workflow version 3. Failure is server
  `decode original PSD`, before companion/Photoshop/mockups. Render logs and the
  durable intake error agree. One earlier attempt was cancelled by a deployment.
- No audited approval or workflow membership matches this new file/content.
  A review-folder name, familiar dimensions or a Photoshop working-space label
  cannot supply an original profile. Steve Smith's approval is unrelated.

The server PSD adapter was introduced by `3d8af11d` and already called the colour
resolver using a pre-product `template_id`. Exact Edition Ops approvals use
`product_gid`; the strict whole-source dictionary match omitted valid approvals
for the identical physical file. That compatibility bug is independent of this
new source's genuinely absent approval. Both conditions are addressed without
loosening Edition Ops gates.

Live audit before release: primary OS completed deploy `a3b69acc758dc4c11cbbf5f6010a0c769b792f6e`
(a concurrent task's deploy was allowed to finish); SEO worker same source.
Installed Windows listener PID 29112, port 18761, still used approved `dfe44257...`.
Five installed helper hashes matched Git `dfe44257` exactly. Phase 1/2/3 speed
changes were not in that installed code; `companion_transfer.py` was local-only.
Current web failure therefore did not result from deploying Phase 2.
Full hashes and deploy evidence are retained under
`output/product-upload-colour-20261020/` without credentials.

## Owner decision and repair

Two labelled colour-managed hypotheses were rendered from the saved full-resolution
PSD composite without editing the original. The owner answered **“Approve A for
this exact source”** to the sRGB candidate, explicitly naming this file/revision.
This is a new intended-appearance decision, not a claim of historical creator intent.

The exact-source policy `product-upload-pinstripe-owner-20261020` has approval hash
`0b9ef5d1f18839e5c14795a1f5409d70aed82d0f9e6c79067166b9f27a41dfa7` and reviewed
proposal hash `a92c691602b61e986e34da274c4bad79006a425e1dbc1a902ee13a6e15b6ad7d`.
It is appended to the existing approved policy registry, with source/provenance,
preview/comparison hashes and the owner's decision. No default, workflow membership,
template replacement, print approval or approval for another source is created.

`product_upload_colour.resolve_web` bridges pre-product identity to an existing
approval **only for the same file ID + revision + content hash**, returning the
original policy receipt. Existing verified-workflow rules remain available under
their original explicit scopes. Conflicts/tampering fail closed; changed files,
revisions and content do not inherit exact approvals. Edition Ops' global resolver
and product/run checks are unchanged.

Server `product_upload_artwork.decode` and native `render_product_upload_psd`
share that adapter. Preparation fingerprints include its code and the full
existing policy configuration, so failed/stale work is re-evaluated after approval.
The server reads its approved registry/audit configuration; companion receives the
same validated authenticated configuration through existing host sync.

The real PSD locally decoded through the repaired server path to a tagged
2000 x 1414 RGB PNG (the existing Mockups size limit). Source hashes were unchanged.
The original PSD, layers, dimensions, metadata and sync settings were not modified.
Native working copies retain the existing metadata-only assignment and closure/
preservation guards; no native Photoshop dispatch was needed for this diagnosis.

## Verification and release scope

Focused tests cover exact-source reuse before product creation, changed identity,
conflicting/tampered policies, synced companion configuration, failed preparation
then approval/retry, tagged/untagged native mock boundaries, original preservation,
server decoding/cache invalidation and the actual shared Mockups renderer.
Phase 1/2/3 tests and desktop/mobile Worker Health checks are retained.
Known prior stale colour/preflight mocks and the synthetic missing-edition-limit
Product Upload test are documented baseline failures, not reasons to weaken gates.
Final counts and actual live verification are recorded in the release evidence.

Release includes this fix, exact owner approval and completed Phase 1/2/3 source,
tests and migration. Review the preceding phase reports for measured results and
trade-offs; no new speed optimisation is included. Durable migration/back-end
capability precedes the matching companion. No failed backlog, edition counter,
allocation, certificate, order or authoritative source is changed.

The Git/Studio inventory separates active work, already released/superseded
snapshots and generated `tmp` evidence. A branch's old Tested label is not authority
to replace newer production files with its historical working copy. Completed
changes from this task are selected explicitly; active unrelated worktrees stay
untouched. Inventory details are retained with the release evidence.

Production acceptance must confirm the exact PSD prepares and generates mockups
through the normal authenticated workflow, then record the new Render commit and
installed companion revision independently. A successful deploy alone is insufficient.
The historical 288-second ingress question and household browsing performance
remain unmeasured; further optimisation is paused pending this functional release.
