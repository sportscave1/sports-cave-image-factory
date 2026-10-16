# ICC release review — 16 October 2026

The owner has approved the **56 standard-canvas legacy sources** and **seven
recovery packages**. Their exact identities, revisions, evidence and archive
hashes are recorded locally. The template policy was approved earlier. This is
an uncommitted review snapshot, not a production release or authority to run
recovery. No production state, active companion configuration or Dropbox asset
has been changed.

## Approval scope

| Scope | Decision | Execution |
|---|---|---|
| designs-canvas sRGB template | Previously approved | Corrected local PSD retained; publishing requires separate authority |
| 56 legacy RGB8 2835×2004 sources | Approved in this turn | Exact revision membership; staged copies only |
| Seven tagged-source recovery packages | Approved in this turn | Reuse verified packages; retain original embedded ICC bytes |
| David Warner, 1448×1086 | Pending | Excluded from approved registry |
| Uncertain artwork and genuine structure/runtime defects | Pending | No colour assignment or blanket retries |

Reviewed legacy proposal SHA-256:
`5112d5325f203a42e1cbd88068208b533d653dee1cafcc1875d15122c9926749`.
Recorded approval hash:
`bad6824badae5897f12c4ddb9510cfe4ba025e9583b6af1bd10d3a79e0975163`.
The registry contains two policies, covering one template and exactly 56 product
sources. It has **not** been installed or enabled. A changed revision or an
unverified new member does not inherit approval just because its canvas matches.

The seven packages retain ICC SHA-256
`3f6d674174f3804eb0dabdac90ae17486e898c5063a66f861c116ea033da8301`.
This differs from the approved template's ICC bytes; both remain supported.
Profile approval and recovery-package approval do not certify a supplier SKU,
physical print match, enlargement quality or fulfilment readiness.

## Catalogue disposition

The bounded read-only audit covered 334 products: 285 mapped and 49 unmapped.
The source/checkpoint recheck at **09:24 AEDT on 16 October** found no changes.
This is an observed snapshot; a fresh preflight is mandatory before execution.

| Mapped disposition | Count |
|---|---:|
| Keep existing preparations: 45 visual review + 16 Cloud Ready | 61 |
| Continue existing eligible queue | 26 |
| Approved legacy source policy | 56 |
| Approved existing export packages | 7 |
| Different canvas, pending | 1 |
| Structural and colour decisions pending | 5 |
| Other unresolved causes, pending | 129 |
| Total mapped | 285 |

The 26 unresolved paid-priority designs remain first in the review queue.
Neither colour approval nor a release may override their actual defects. Keep
paid orders ahead of catalogue work whenever they become eligible.

## Change and validation summary

The corrected inspector distinguishes truly untagged RGB documents from
inspection failures. Preparation independently reads PSD ICC resources,
checks a Photoshop profile witness before export, assigns an approved profile
only to a temporary copy, and restores missing PNG metadata from independently
verified source ICC bytes. Conflicts stop the affected job. JPG exports retain
and recheck their ICC bytes. Original PSD, layer/pixel tail and exported pixel
integrity checks remain enforced.

The confirmed defects were an incorrect Photoshop profile enum, reliance on
profile labels/working-space fallback, and PNG export dropping ICC metadata,
including original.png. Missing-profile, inspector, mismatch, policy approval,
recovery, scratch and transfer diagnostics remain distinct. Supplier and visual
checks remain enforced. Worker Health uses bounded rows and database summaries;
it does not scan PSDs or call providers during page refresh.

All seven approved archives passed the actual server `unpack` validator locally
in **39.199 seconds**, including manifest/source/edition identity, every asset
hash, ICC checks, first/last reference pixels and unchanged pixels outside the
number area. No upload occurred. The earlier preparation produced 728 restored
PNG copies without changing their source files or originals.

The combined Python run passed 180 tests and exposed one test-only timestamp
serialization assertion in the host capability test. The SQL fixture now returns
real PostgreSQL datetime values. That token-storage assertion now serializes
timestamps with `default=str`; its token non-disclosure check remains intact.
All three host API tests passed on the focused rerun (including the failed test),
giving **181 distinct passing tests** across the combined run and repair rerun.
The original run log is retained, including its failure and expected duplicate
ZIP-entry warning. No application behavior changed for this repair. Photoshop
JSX checks and desktop/mobile Worker Health and V17 results are also saved beside
this review packet. Browser
checks rendered 25 rows and 350 DOM nodes, with fixture first paint 115 ms at
1280 px and 70 ms at 390 px, and retained the 20-second refresh interval. These
are local fixture measurements, not production network benchmarks.

## Release sequence for subsequent explicit authorisation

1. Review the frozen source/configuration hashes and diff against verified base
   `8a9b87baaf0e9d7a5e76e4e8cdb25486e436777a`. The task preserves that base's
   Worker Health, V17 and release changes. Integrate later changes explicitly;
   never publish mutable working-directory contents. Commit, push, integration,
   deployment and active companion installation still require authority.
2. On authorisation, rerun combined checks for the exact committed release.
   Use the existing canonical Render service; no Blueprint or topology change
   is part of this work. No database schema migration is introduced here.
3. Update the idle companion and server together, including all new root
   colour modules, the preparation script and both Photoshop JSX files. Check
   the installed release hashes. Do not interrupt an active paid preparation.
   Install the approved policy file explicitly on each process that validates
   or prepares policy-assigned packages; never change the default to sRGB.
4. Before recovery, refresh source file ID/revision/content hash, mapping,
   edition total, priority, status/reason, lease/replacement state and existing
   stored/checkpoint preparations. Compare to release-recovery-plan.json.
   Hold any changed or prepared source for review. Respect Worker Pause.
5. The missing-profile recovery function handles the approved 56 only. Start
   with a bounded dry-run, then enable recovery only under separate execution
   authority. It preserves source/priority, excludes stored preparations,
   retries once and records its audit trail. Do not use the generic Retry
   action: that existing action clears source and promotes priority.
6. The seven tagged export packages use a **separate controlled import lane**;
   generic ICC mismatch retries deliberately remain disabled. After the same
   fresh guards, issue new scoped leases/grants through a reviewed operator
   transition, preserve source/priority, and stage the exact approved archives
   as companion reuse candidates. The companion's existing automatic reuse
   path expects `*/prepared.zip`; review-package.zip is not discovered by that
   path. Never edit old journals or fabricate leases. The server revalidates
   each archive before checkpointing. This operator transition/staging has
   **not been executed or enabled** and must be reviewed with the release;
   the current automatic missing-profile hook does not import these seven.
7. Keep the 61 prepared products, especially the 45 awaiting visual review,
   untouched. Continue eligible queue work independently of pending designs.
   Never reset numbers, certificates, allocations, mappings or approvals.
   Observe separate approved/recovered/remaining counts and stop the affected
   lane on a conflict; do not block unrelated work.

Rollback disables the recovery flag and removes the active policy-file setting
under authorised operations, then restores the previously verified server and
idle companion release. Never reset queue, approvals, stored packages or edition
state as a rollback. Keep uploaded verified packages and audit records.

## Review files

The new packet is `output/icc-release-review-20261016/`:

- `owner-approval-receipt.json`, `legacy-standard-canvas-APPROVED.json`,
  `approved-colour-policies.json`
- `seven-approved-packages.json`, `local-import-verification.json`,
  `release-recovery-plan.json`
- `source-review.zip`, `source-review-manifest.json`, `tracked-changes.patch`
- Combined regression, JSX, browser and static-check logs

The seven large archives and corrected local template remain at their original
review locations under `output/icc-catalogue-review-20261016/`; the packet pins
their hashes rather than duplicating 1 GB. The source archive contains review
overlays against the named base, not a standalone deployable repository. The
earlier audit report retains its historical pending decisions; this document
and the new receipts supersede those decisions only for the approved scopes.

**Remaining approvals:** release/integration and recovery execution, active
companion installation, and any future template publication. The one different
canvas and uncertain artwork still require their own evidence/review. The 56
source-profile approvals and seven package approvals do not need repeating
while their reviewed identities and hashes remain unchanged.
