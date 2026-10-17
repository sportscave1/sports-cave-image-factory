# Colour workflow reuse — local investigation and implementation

17 October 2026 AEDT. Local task `20261016-e16c71b7`, owner
`codex-colour-reuse-20261017`.

Worktree:
`C:\Dev\SportsCaveWorktrees\sports-cave-integrations-reusable-verified-colour-policy-handling-a-20261016-e16c71b7`.
Branch:
`codex/task/integrations-reusable-verified-colour-policy-handling-a-20261016-e16c71b7`.
The INTEGRATIONS entry was clean on codex/category/integrations. The new task was
clean before alignment to current origin/main, commit ccfef1e2. Other tasks and
the pending PSD-repair checkout were not edited. The owner subsequently authorised
this colour release, scoped live policy activation/recovery and an idle Companion
update. The original investigation below records the earlier local-only state;
the release report in output/colour-reuse records actual deployment/results.

## Owner decision and completed release controls

The owner's 17 October approval explicitly interprets the pinned current
Volkanovski source and independently verified legacy RGB8 workflow as sRGB
IEC61966-2.1 (ICC SHA-256 2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e).
This is an owner-approved interpretation, not proof of previously unknown creator
intent. Valid embedded profiles remain authoritative. CMYK, conflicting profiles
and unknown workflow membership remain separate.

The new dated registry retains both old policies unchanged, adds the existing
56 verified workflow members under explicit content-identity scope, and adds one
exact Volkanovski approval. A changed file/content requires new provenance.
The Review control now approves a pinned proposal and resumes that exact blocked
job atomically, or resumes an existing approval without redundant colour approval.
Administrator/origin permissions, current Dropbox identity, mapping, leases,
retained preparations, diagnostic and once-only audited requests are checked.
Claims remain serialised through the existing worker. It does not approve artwork.

Approved runtime policies and provenance receipts are append-only events in the
existing audited backend. The authenticated preparation host reads them at idle
boundaries; it cannot write approval or provenance. The app independently resolves
the same registry when validating packages and review previews.

Files uploads optionally accept a verified workflow creation/export manifest.
An administrator supplies independent hashed provenance, e.g.:

```json
{"workflow_id":"legacy-sportscave-rgb8","verified_workflow":true,"content_hash":"<exact Dropbox content hash>","provenance":[{"name":"designer-export-record.json","sha256":"<actual SHA-256>","purpose":"Independently verified creation/export lineage"}]}
```

Only the actual completed upload bytes, independently inspected untagged RGB8
metadata and matching Dropbox content receipt produce automatic membership.
Ordinary uploads, names, folders, dimensions and visual resemblance never do.
Capture is bounded to two optional 1 GiB uploads per app process; interrupted or
invalid provenance does not falsely fail a completed upload. Such files retain
normal profile checks and require independent verification. Sources created
outside this upload path need a trusted lineage receipt or an exact approval.

The prepared shared-template replacement is LOCAL ONLY in
output/colour-reuse/shared-template-sRGB-OWNER-APPROVED-LOCAL.psd. Its layer/pixel
payload is unchanged. The original was preserved. Export settings are recorded in
config/auto_editions/srgb-template-export-settings-20261017.json; production
replacement still requires separate authorisation.


## What happened to Volkanovski

Product `gid://shopify/Product/10071572578611` now maps to:

- Name: Alex Volkanovski UFC Champion.psd
- File ID: `id:u1tYiAa2O-AAAAAAAABgxA`
- Revision: `0165dfd6f449ede000000036d367e13`
- Dropbox content hash:
  `1a8848cef905588ea0a80389bb1a2b76b35f57babb50e9d6616d95f4e54ba48b`
- Bytes: 187,538,325; independent metadata inspection: untagged RGB8, 2835×2004.

Dropbox's current file ID/revision/size match the retained Companion source.
The retained original's independently recomputed Dropbox content hash matches
the onboarding source. The connector does not return content_hash; the hash was
computed over the retained exact-revision bytes, not invented from its name.

The job was claimed at 10:27:43.431 AEDT and blocked at 10:28:35.811: 52.38 seconds.
The host retrieves/verifies the PSD and inspects it in Photoshop before resolving
the untagged-source policy during role detection. The retained inspection and
policy exception show it stopped at that gate, before successful master
preparation. No preparation hash exists. This is not a completed preparation
waiting for gallery acceptance, and repeated Refresh cannot supply missing policy.

Both the live Render app and actual Companion heartbeat report
`ccfef1e2e5cce3c9b889084b5da9210906adfb8e`. Companion code hash:
`5d2468ce441512c402c55b2a9ac222151254451db314f4660115873460e963fc`.
The installed registry matches the committed policy file byte-for-byte; its SHA
is `b1e4090ddbcc2edbe77eae5083c65739daf596dbc39c6f3631d35889c19422de`.
This is not a stale app/Companion rollout or missing installed policy file.

## What the previous fix did, and what it missed

The colour-preservation work in task `20261015-65dad529`, included in the released
code, corrected Photoshop profile-state inspection, independently inspected PSD
ICC resources, preserved valid embedded RGB ICCs, required a native profile
witness and restored export ICC metadata without recompressing image pixels.
The approved records cover one exact template plus 56 exact legacy product
source identities. Seven tagged-source export omissions were a separately
reviewed package-recovery scope; that is not authority to assign profiles to
arbitrary untagged originals. Source/mode/integrity/geometry checks remain intact.

Three gaps explain this case:

1. The approved schema-1 registry matches the entire source dictionary: product,
   permanent file ID, revision and content hash. It has no reusable workflow
   scope/default or independently verified future membership mechanism. Neither
   current Volkanovski nor its former mapped source is among the 56.
2. The earlier audit mapped Volkanovski to a different source,
   `id:u1tYiAa2O-AAAAAAAAAVBQ`, revision
   `0165da1cafa24a3000000036d367e13`, hash
   `523be412b3462591f66dbbda87f78013f7178b4c6d4ceadd87057ea24cc281f5`.
   It was classified `CAUSE_UNDETERMINED` / `pending_uncertain` after a runtime
   failure, with colour_approved=false and fresh source confirmation required.
   Remapping to the new file changes both file identity and bytes. This is not
   just a metadata-only revision, a hash formatting issue, or a missed title alias.
3. The corrected sRGB template was retained as an approved isolated copy, not
   published over the original shared template. Fresh Dropbox metadata still
   shows original designs-canvas.psd at revision
   `0165db12ed0d0f5000000036d367e13`, unchanged since 13 October. The hash-matching
   retained original is untagged. New PSDs therefore cannot be assumed to inherit
   the corrected copy's ICC. The old status projection also deliberately returned
   no actions for colour failures, producing the dead-end Refresh screen.

Same canvas, folder, layer names or a similar appearance do not prove membership.
No existing approved policy legitimately authorises assignment to this new source.

## Proposed default and actual evidence

Candidate: **sRGB IEC61966-2.1**, exact existing approved ICC SHA-256:
`2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e`.

Its bytes match both the approved template/legacy policy and the actual retained
trusted export `#001-At Last Dale EarnHardt Sr.jpg`. That export's SHA-256 is
`b9a72ca8407f59f87a9c47bfa1c1536afe248dea8d8d393c30265cf8af600721`, matching the
previously owner-reviewed reference. Its embedded profile is the exact candidate,
not a profile generated from a machine working-space label.

An **awaiting-approval** schema-2 workflow proposal and fingerprint are in
`output/colour-reuse/`. It explicitly names verified legacy RGB8 workflow scope,
not all files in the catalogue. Its initial members are the existing 56 pinned
legacy sources; `coverage.csv` lists every product/file/revision/hash. The template
keeps its separate exact policy. Volkanovski is not silently inserted as a member.
Future matching sources need independent, content-bound workflow provenance,
not repeated per-product approval of the same ICC. Unknown origins, CMYK,
conflicting ICCs, different bytes and failed inspection remain separate.

For Volkanovski, obtain either a trusted designer/export manifest establishing
this exact source's intended RGB workflow, or explicit owner review approving
the proposed sRGB interpretation against a trusted colour-managed reference.
If that evidence identifies another profile, propose that profile separately.
Do not label an absence of evidence as sRGB approval. The colour policy cannot
certify physical print appearance, font availability, plaque/number correctness,
supplier enlargement quality or production printing.

## Local implementation

- Schema-1 exact approvals and their returned preparation evidence remain
  unchanged. Tagged files still use their original embedded ICC and skip policy
  assignment. No Photoshop preparation/export scripts were modified.
- Schema-2 proposals include owner-reviewed workflow ID, RGB8 restriction and
  permanent-file/content identity. Already reviewed identical file bytes may be
  reused across product mappings or metadata-only revisions only under this new
  explicit scope; a changed content hash cannot inherit it.
- Workflow defaults require an explicitly selected group and an independently
  verified membership receipt bound to file ID/content hash, policy approval hash,
  actual untagged-RGB8 inspection and hashed provenance. An operator-controlled
  registry is trusted configuration, never a browser-provided approval assertion.
- If a workflow extension and original exact approval overlap with identical
  ICC bytes, retain the original exact receipt. Duplicate records or differing
  profiles stop resolution. Passed preparation records are not reprocessed.
- Bounded recovery remains opt-in/dry-run by default, excludes retained/active
  designs and preserves priority, mappings and allocations. It recognises verified
  workflow members before its 50-row bound. Once-only retries bind to file/content,
  so a previous mapping's retry does not suppress a genuinely new source.
- Needs Review exposes **Review colour profile**. The authenticated admin view
  shows the pinned source, exact scopes, evidence checklist and registry digest.
  It hashes small evidence files locally, prepares a downloadable pending proposal
  and rejects stale source/registry snapshots. It never uploads PSDs, records
  approval, activates a registry or starts a job. CMYK/conflict/inspector exceptions
  offer the pinned review request; they cannot propose a generic RGB assignment.

## Configuration / approval path — NOT activated

Use the existing offline CLI to propose/approve the exact reviewed JSON. The
optional `scope` is covered by the approval fingerprint; changing it invalidates
approval. Example workflow scope:

```json
{"kind":"verified_workflow","workflow_id":"legacy-sportscave-rgb8","mode":"RGB","depth":8,"identity":"file_id+content_hash","default_for_untagged_rgb":true}
```

Only after actual owner review, prepare operator-controlled membership receipts:

```text
python scripts/review_auto_editions_colour.py member --source VERIFIED-COPY.psd --identity source.json --policy APPROVED-policy.json --provenance independent-evidence.json --verified-by IDENTIFIED-OPERATOR --output member.json
```

This verifies the exact content hash and actual PSD mode/profile state. The
operator must independently verify workflow lineage; the command cannot infer it
from a filename. It never overwrites a source or activates a receipt.

After separate deployment/activation authorisation, app and Companion must use
the same approved policy registry and membership registry:

```text
AUTO_EDITIONS_COLOUR_POLICIES_FILE=<operator-controlled approved policy list>
AUTO_EDITIONS_UNTAGGED_RGB_DEFAULT=legacy-rgb8-verified-workflow-default
AUTO_EDITIONS_COLOUR_WORKFLOWS_FILE=<operator-controlled verified receipt list>
```

Leaving the default unset disables workflow-wide fallback. Selecting an old
schema-1 group does not turn it into a blanket default. Keep the old approved
records so passed/exact preparations retain their evidence. Recovery additionally
requires its existing separate enablement and explicit bounded invocation.

## Tests and isolated appearance checks

Real retained sources: current Volkanovski, former Volkanovski, and approved
legacy products 10468403806515 and 9319178993971. Independently recomputed pinned
hashes, assigned the candidate only to new isolated PSDs, then decoded and compared
their stored merged composites. All four have **zero changed RGB pixels**, equal
pixel hashes, unchanged originals and equal layer/pixel tail hashes. Candidate and
untagged diagnostic PNGs are provided; current Volkanovski's pair was visually
inspected. No artwork, plaque, numbering, layers or pixels were rewritten.

That is a metadata-only assignment result. An untagged source has no defined
colour-managed interpretation: zero numeric changes do not prove that assigning
sRGB matches its creator's intent or a physical print. No full new 100-edition
Photoshop run was performed, and no live Photoshop/Companion session was used
or restarted. Existing tests exercise export ICC/witness guards with synthetic
native responses. A separately owned native preparation remains a later gate.

Final focused Python/disposable PGlite result: **86 passed, 1 skipped**. The Edge
desktop/mobile review checks also passed. These checks
cover exact reuse, changed hashes/revisions, default selection/provenance,
CMYK/tagged/conflicting profiles, stale approvals, source remapping, access/origin,
passed-design preservation, duplicate recovery and pending-only review proposals.
The optional native 334-product performance fixture is explicitly skipped.
Detailed XML, coverage, profile/preservation proofs and screenshots are in
`output/colour-reuse/`.

Changed production files: `auto_editions_colour_policy.py`,
`auto_editions_colour_workflows.py` (new), `auto_editions_colour_recovery.py`,
`auto_editions_colour_review.py` (new), `auto_editions_status.py`,
`components/auto_editions/status.html`, `components/auto_editions/colour-review.html`
(new), and `scripts/review_auto_editions_colour.py`. Added focused workflow,
recovery and review-UI tests. The committed ICC registry, original preparation
scripts and active installed Companion files are unchanged.
