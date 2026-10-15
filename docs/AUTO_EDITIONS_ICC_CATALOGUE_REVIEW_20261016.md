# Current catalogue audit and colour recovery review — 16 October 2026

Your sRGB template policy approval is recorded locally. The approved template
copy is ready; no Dropbox template or production configuration was updated.
Legacy colour approval, deployment, live retry and publication are not authorised.

Audit used SELECT-only Supabase connector queries against repository-confirmed
project `ceyzbfpuwuuxaiqwiltz`, plus read-only Dropbox metadata and retained local
artwork evidence. No production credentials were imported into development.
The mapped snapshot was taken at **09:12:38 AEDT** and rechecked at **09:24:18 AEDT**.
All 285 mapping/source/status/priority/preparation identities remained unchanged.
Catalogue coverage was checked at **09:24:56 AEDT**. These are timestamped
observations; every eventual recovery must revalidate the then-current state.

## Complete catalogue coverage

There are **334 catalogue products: 285 mapped and 49 unmapped**. All 285 mapped
products have onboarding checkpoints and source-inventory metadata. All existing
non-null checkpoint source identities match their pinned inventory identities.
There were no active preparations in the observed snapshots.

| Mapped decision | Designs | Treatment |
|---|---:|---|
| Retain existing prepared assets | 61 | 45 awaiting visual review and 16 Cloud Ready; no regeneration or reset |
| Existing queued designs | 26 | Retain queue identities and priority; normal checks still apply |
| Proven ICC export omission | 7 | Local verified packages prepared for review; preserve embedded ICC |
| Untagged RGB/8, structurally eligible for a proposed policy | 57 | 56 standard-canvas and 1 different-canvas proposal; neither approved |
| Missing profile plus structural defects | 5 | Keep pending: 4 number-layer cases, 1 plaque case |
| Other blocked or unresolved cases | 129 | Keep pending; detailed causes and priority are in the review CSV |
| **Total mapped** | **285** | No live queue or artwork mutations |

The 49 unmapped products are recorded separately in `catalogue-coverage.json`.
This task does not guess their PSD mappings or classify them as ICC failures.
All **26 unprepared paid-priority products** appear first in the review plan and
in `paid-priority-review.csv`. They remain pending their specific source, colour,
structural or connection decisions. Paid priority is preserved; unsafe paid work
does not prevent a different eligible design from progressing after release.

## What the failure evidence establishes

- 62 current failures explicitly report a missing profile. Every one has a
  matching retained source inspection and fresh Dropbox revision confirmation.
  Of those, 57 pass retained edition-layer checks and 5 have an additional
  structural blocker.
- Of 43 generic preparation RuntimeErrors, 42 retained sources are genuinely
  untagged. The runtime cause itself is not established by that fact, and the
  remaining case has insufficient retained evidence. All 43 remain pending.
- 13 designs report profile mismatches. Seven have complete retained exports and
  independently proven metadata omission. Five other inspected mismatch sources
  are untagged, and one is tagged without enough retained export proof. These six
  are not automatically reclassified as repairable export omissions.
- Inspection, transfer, package-size, numbering, plaque, expired-worker and
  non-opaque-composition errors remain separate. Colour approval cannot repair
  those causes or authorise painting a background.

The audit reused 139 matching retained inspection records and read PSD metadata.
It did not reopen hundreds of files in Photoshop or rerender the catalogue.
Full source hashes were independently checked for all 57 proposed legacy members
and all 7 export-omission candidates. Fresh Dropbox metadata was checked for the
62 explicit profile failures, all 13 mismatch sources and the template: 76 files,
with no changed revisions. Hashing the 57 proposed sources took 8.094 seconds.

## Approved template — approval completed

The exact reviewed template proposal fingerprint remains
`904bb099537bfeb0a1059a442116ba210fa9f4dd3223122ecf78d2765c064f02`.
Your approval was recorded at 09:11:35 AEDT. Its approval record hash is
`2d2e8f3d5520b047efac577098d5080fd69aa1e75000ec05ac6a685375c542b8`.

`designs-canvas-sRGB-APPROVED-LOCAL.psd` has SHA-256
`deb8eed2a958168389acc7863418895cf17e13941df4923471c16f49541320e9`,
matching the reviewed candidate. Its 2835 × 2004 canvas, layers, editable numbering,
fonts, plaque, geometry and stored pixel/layer bytes remain preserved. The
approved registry contains only that pinned template. Future designs that retain
its embedded profile can use the tagged path once publication is separately
authorised. The original live template remains untouched.

Approval does not extend to legacy art because dimensions, layer names and
filenames do not establish historical colour intent or template ancestry.

## Legacy policies prepared for owner review

| Proposed cohort | Members | Proposed document profile | Status |
|---|---:|---|---|
| Current untagged RGB/8, 2835 × 2004 | 56 | sRGB IEC61966-2.1 | Awaiting approval |
| Current untagged RGB/8, 1448 × 1086 | 1 | sRGB IEC61966-2.1 | Awaiting separate approval and additional resolution/aspect review |

Each proposal pins every member's product/file/revision/content hash and includes
hashed per-member structural evidence, reference evidence and representative
comparison images. Source SHA checks and Dropbox revisions match. No legacy PSD
has been assigned a profile. No lineage from the approved template is claimed.

The comparisons show the same RGB values left untagged and labelled with the
proposed sRGB interpretation. Original pixels are untouched; the comparison does
not prove historical colour intent or a physical print match. The proposed
standard follows the previously documented Sports Cave sRGB export practice,
subject to your scoped legacy decision. All supplier and visual checks remain.

Proposal fingerprints:

- 56-member cohort:
  `5112d5325f203a42e1cbd88068208b533d653dee1cafcc1875d15122c9926749`
- Separate 1-member cohort:
  `e7c53b17e995796628516169a6aa2e2fd9faf09506deec8e751dd2b5c8859719`

Both remain `awaiting_approval`; the template approval is not reused as a legacy
approval. The exact member lists and comparisons are in `legacy-proposals/`,
`member-evidence/` and `comparisons/` in the review output directory.

## Seven export recoveries prepared locally

All seven pinned sources already embed a valid sRGB profile. The entire 104-file
export set for each design had lost ICC metadata. The source profile SHA-256 is
`3f6d674174f3804eb0dabdac90ae17486e898c5063a66f861c116ea033da8301`.
Those exact bytes were preserved; they were not replaced with the approved
template's different ICC bytes.

The seven review packages contain **728 ICC-preserving PNG copies**. Photoshop
was not rerun, and original retained PSDs/PNGs were not modified. Reference
renders for the first/last editions are pixel-exact, and pixels outside the
number region are unchanged. All source and original export hashes were
rechecked. Metadata restoration and package proofing took 52.521 seconds total.

Each archive is under the existing 256 MiB transfer limit (114.39–166.20 MiB).
A representative archive also passed the independent server unpack and pixel
verification path locally, in 5.958 seconds. Nothing was uploaded. Every result
retains `print_ready=false`, `uploaded=false` and `retry_authorized=false`.

The per-design package list is appended below. Full checksums and proof hashes
are in `export-recovery-review-results.json` and each `review-result.json`.

## Recovery sequence for review

1. Keep the 61 prepared identities intact, including the 45 awaiting visual
   review. Reuse existing verified packages and receipts. Never regenerate those
   designs or reset approvals, allocations, certificates or edition numbers.
2. Review the 26 paid-priority cases first using their specific diagnostics. They
   retain priority 8. Do not grant colour approval to resolve an unrelated
   number-layer, plaque, transfer or runtime problem.
3. After a separately authorised release and idle companion update, revalidate
   the seven omission candidates against the current mapping, source revision/
   content hash, edition total, absence of existing preparation and exact archive
   hash. Authorise only those scoped retries/imports, preserving priority/source
   identity. Reuse these packages through fresh owned grants and independent
   server verification. A changed source or new existing package cancels that
   recovery candidate; do not overwrite it or blanket-reset the queue.
4. Approve either legacy proposal only after its comparison/member review. Once
   approved, install that exact scoped policy on server and companion during an
   authorised release. Assign ICC interpretation only to temporary staged copies;
   do not convert pixels or modify the Dropbox originals. Reuse approval for
   matching pinned members and keep changed/unverified members pending.
5. Retain the existing queue and paid ordering, bounded leases, Pause control,
   failure isolation, visual acceptance and SKU-specific supplier validation.
   A locally verified package or approved document profile is not supplier print
   certification and does not authorise fulfilment.

`RECOVERY-PLAN-REVIEW-ONLY.json` contains exact source IDs, package hashes,
preparation hashes, expected checkpoint/priority guards and required release
conditions. It is a review artifact, not an executable production operation.
No recovery flag, server/companion installation, service setting, Dropbox asset,
mapping, allocation, edition number, order or certificate was changed.

## Validation and files

New offline helpers are `auto_editions_colour_audit.py` and
`auto_editions_colour_review_exports.py`. Structural checks are exposed separately
as `detect_roles` for review evidence; the existing preparation path still calls
`detect`, which enforces the colour gate first. Synthetic tests cover approval
scope, missing/stale evidence, source hashes, protected 45 designs, paid priority,
lease holds, unresolved runtime causes, export conflicts and immutable originals.

The loopback SQL test fixture initially encountered Windows socket exhaustion
after repeated suites; its isolated transport now reuses a connection. Broader
fixture coverage also exposed missing Worker Health columns in its minimal fake
onboarding table; the fixture now includes those columns. Neither change touches
application networking, database schema or production. A retired test assertion
was also updated to accept the current safe blocked-status link while still
asserting generation is rejected after a mapping change.

Final validation: **83 focused tests passed** (1 warning) in 47.67 seconds, plus
**16 Worker Health regression tests passed** in 16.42 seconds. The final
audit/export-specific rerun passed all 17 tests in 0.56 seconds; these overlap the
83-test suite and must not be added again. Scope checks also confirmed that the
approved registry matches no legacy members, both proposals remain pending, all
seven archives retain their exact hashes and every execution/publication gate
remains unauthorised. Studio static checks and topology validation are recorded
with the task before handoff.

Review artifacts are under `output/icc-catalogue-review-20261016/`:

- `catalogue-snapshot.json` / `.sql`, `catalogue-coverage.json`,
  `handoff-source-recheck.json`
- `catalogue-review-plan.json`, `catalogue-review.csv`,
  `paid-priority-review.csv`
- `template-owner-approval-receipt.json`, `approved-template-policies.json`,
  `designs-canvas-sRGB-APPROVED-LOCAL.psd`
- `legacy-proposal-index.json`, `legacy-proposals/`, `comparisons/`,
  `member-evidence/`
- `verified-review-evidence.json`, `verified-export-omission-evidence.json`,
  `export-recovery-review-results.json`, `export-recovery-review/`
- `RECOVERY-PLAN-REVIEW-ONLY.json`, test logs and Studio verification receipts.

Local work remains uncommitted in task `20261015-65dad529`; it is not released.

## Per-design export review packages

All are held locally for review; no new source-profile assignment is proposed.

| Design | Product ID | Priority | Package MiB | Review result |
|---|---|---:|---:|---|
| Kevin De Bruyne Manchester City Art | 8188011118899 | 1 | 134.46 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/8188011118899/review-result.json) |
| Marcus Rashford Manchester United Wall Art | 8286069227827 | 1 | 114.39 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/8286069227827/review-result.json) |
| Cristiano Ronaldo Siuuu Wall Art | 8866756165939 | 1 | 148.98 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/8866756165939/review-result.json) |
| Robert Lewandowski Wall Art | 8897947599155 | 1 | 132.77 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/8897947599155/review-result.json) |
| Antoine Greizmann Master of Movement Wall Art | 9494826746163 | 1 | 134.28 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/9494826746163/review-result.json) |
| Dominik Szoboszlai Liverpool FC Wall Art | 9495409295667 | 1 | 125.80 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/9495409295667/review-result.json) |
| Colin McRae ’95 Wall Art | 9959233618227 | 1 | 166.20 | [Pixel proofs and hashes](../output/icc-catalogue-review-20261016/export-recovery-review/9959233618227/review-result.json) |

## Direct review links

- [Approved local template](../output/icc-catalogue-review-20261016/designs-canvas-sRGB-APPROVED-LOCAL.psd)
- [56-member legacy proposal, pending](../output/icc-catalogue-review-20261016/legacy-proposals/legacy-untagged-rgb8-2835x2004-20261016-PENDING.json)
- [Separate one-member proposal, pending](../output/icc-catalogue-review-20261016/legacy-proposals/legacy-untagged-rgb8-1448x1086-20261016-PENDING.json)
- [Review-only recovery packet](../output/icc-catalogue-review-20261016/RECOVERY-PLAN-REVIEW-ONLY.json)
- [All mapped designs and decisions](../output/icc-catalogue-review-20261016/catalogue-review.csv)
- [Paid-priority review list](../output/icc-catalogue-review-20261016/paid-priority-review.csv)
- [Unmapped catalogue coverage](../output/icc-catalogue-review-20261016/catalogue-coverage.json)

Comparison images for the 56-member cohort:

- [10130210914611-original-UNTAGGED.png](../output/icc-catalogue-review-20261016/comparisons/10130210914611-original-UNTAGGED.png)
- [10130210914611-PROPOSED-sRGB.png](../output/icc-catalogue-review-20261016/comparisons/10130210914611-PROPOSED-sRGB.png)
- [10134728409395-original-UNTAGGED.png](../output/icc-catalogue-review-20261016/comparisons/10134728409395-original-UNTAGGED.png)
- [10134728409395-PROPOSED-sRGB.png](../output/icc-catalogue-review-20261016/comparisons/10134728409395-PROPOSED-sRGB.png)

Comparison images for the 1-member cohort:

- [8119132651827-original-UNTAGGED.png](../output/icc-catalogue-review-20261016/comparisons/8119132651827-original-UNTAGGED.png)
- [8119132651827-PROPOSED-sRGB.png](../output/icc-catalogue-review-20261016/comparisons/8119132651827-PROPOSED-sRGB.png)
# Subsequent owner approval

The owner subsequently approved the 56 standard-canvas group and seven recovery
packages. See [the release review](AUTO_EDITIONS_ICC_RELEASE_REVIEW_20261016.md)
and its exact-scope approval receipts. The audit below is retained as historical
evidence; the different-canvas proposal and uncertain artwork remain pending.
