# Auto Editions V16 - local implementation and production-evidence limits

Status: IMPLEMENTED LOCALLY, NOT RELEASED. Automatic production approval is OFF.

## Isolation and authority

Task `20261015-1fe4408e`, owner `codex/v16-20261015-01a13cc7`.
Worktree: `C:/Dev/SportsCaveWorktrees/sports-cave-integrations-auto-editions-v16-conclusive-automatic-qua-20261015-1fe4408e`.
Branch: `codex/task/integrations-auto-editions-v16-conclusive-automatic-qua-20261015-1fe4408e`.
Baseline: independently verified live `607d10cb743694f5b94b1567897adad8280dd159`.
Studio allocated from its older global base; only this new task was fast-forwarded
locally to the verified committed baseline. The global base and all V15/RELEASE/
other worktrees were preserved. No commits, pushes, deployments, production reads
beyond baseline deployment inventory, production data writes, live flag activation,
Photoshop operations or companion installation changes were performed for V16.

## Automatic operation

V15 registration, exact discovery, audited mappings, preparation queue, Photoshop,
upload/checkpoint, manual preview approval and allocation authority stay intact.
When explicitly enabled later, the existing discovery worker assesses one prepared
artwork per cycle. No new service, cron or dependency is added to the application.
A transaction advisory lock prevents duplicate quality workers; crashes roll back
the assessment and release the lock. Persisted due times survive restarts. Existing
and newly completed preparations are eligible; intentionally Deferred/unprepared
jobs are never selected, prioritised or reset by V16.

The gate requires an EXACT previously owner-approved artwork/preparation/source
standard. It pins the manifest, source ID/revision/hash/product, plaque/number
geometry, every patch checksum, fonts and edition limit. It independently reads
every Dropbox receipt and downloads/verifies all generated asset checksums,
revisions, sizes and approved paths. Valid pixel/outside-number proofs are mandatory.
It inspects actual RGB PNG dimensions and a real embedded ICC profile, checks native
effective PPI, then validates sample encoded JPEG dimensions, profile, 300 DPI,
quality 100 quantization and 4:4:4 encoding. Every order-time production export is
independently validated before archival. Production exports use a new policy-bound
job identity and Production archive path; historical TEST archives are unchanged.
Existing allocation authorization and final source/allocation fences still apply.

A successful check writes a separate production assessment/audit, not a fabricated
human approval or replacement of historical layout records. Edition Ops projects
Production Ready only for a current unexpired certificate, matching source,
proofs, edition limit, standards and policy. It identifies an approved supplier
variant scope, NOT permission to fulfil orders. Generation checks that exact
variant; unverified variants cannot inherit a product-wide production approval.
New/changed artwork, changed PSD revisions, changed plaques or numbers and ambiguous
or conflicting evidence retain Needs Review/Needs Repair/Failed. Routine repeats
of the exact approved standard need no further click.

Recheck validation only schedules the current quality assessment and audits the
administrator. It never changes the mapping, legacy approval, Photoshop lease or
edition allocation and cannot restart preparation. Missing/disabled policy and
non-administrator access fail closed. A stale/changed assessment cannot certify
assets while a recheck is pending.

## Current eligible artworks and genuine blockers

**Zero real artworks are enabled for automatic production approval in this local
proposal.** `data/auto_editions_production_standards.json` intentionally contains
`[]`. Existing human approvals remain valid for their existing preview scope.
They are not supplier certificates and are never silently promoted.

V15 supplier evidence for GLOBAL-CFP-A1 states certification incomplete: bleed,
safe margins and colour profile are unknown, quality approval is false. The V15
Favre/Rodgers preparation observed before V16 used a 2835x2004 source enlarged to
11340x8016, source resolution metadata 72, and no inspected source profile. An
assigned 300-DPI export tag and successful upload cannot create native detail,
prove colour or certify that artwork. The recorded A1 target is 9933x7016; V16 does
not crop, stretch or silently resample assets to force a match.

Before any real certification: obtain exact supplier SKU/variant geometry including
bleed, safe areas, physical canvas size, required ICC profile and native-resolution
requirements; validate actual source/output against them; have the owner approve
the exact artwork and complete numbered range as a reusable visual standard.
A new design requiring aesthetic judgement cannot safely inherit approval from a
different design merely because the plaque is similar. This requirement prevents
fully automatic certification of arbitrary new artwork.

Create an owner-reviewed server standard only after those checks. Required fields:
`id`, `actor_id`, `approved_at` (timezone-aware), `human_visual_approved=true`,
`supplier_requirements_verified=true`, supplier evidence reference, `supplier_sku`,
exact `variant_ids`, exact `source`, exact immutable `preparation_hash`, and `output`:
- exact pixel `dimensions`, `format=JPEG`, `mode=RGB`, `dpi=[300,300]`,
  `quality=100`, `subsampling=0`, exact valid `icc_sha256`;
- `printable_mm` for the FULL supplier canvas, four `bleed_mm`, four
  `safe_margins_mm`, `minimum_source_ppi` at least 300;
- `geometry_includes_bleed=true`, `safe_area_visually_approved=true`.
Never copy a synthetic test standard into deployment configuration. The preparer
still emits the existing immutable manifest; a separately approved production
record certifies it only if all real checks succeed. Unsupported supplier sizes,
colour modes or conversions remain blocked; no conversion is invented.

V15 historical exceptions remain read-only: two unrecorded folders, two
checkpoint/approval gaps, 1,919 legacy missing-size receipts. They must be
individually investigated using existing asset audit controls. V16 never deletes,
relinks or approves them by folder name. Incomplete legacy receipts fail the gate.

## Interface and performance

Same narrow Auto Editions column, toolbar filter, modal and 25-second safe batch
refresh. New Production Ready / Needs Review states reuse the existing table.
Pending automated validation needs no manual action. No UI redesign, whole-page
refresh, extra toolbar, per-row Dropbox call or edition-ledger write was added.
Everyday dialogs use Preview or supplier-validation language. Historical internal
TEST contracts, API fields and archive filenames remain unchanged for compatibility;
no historical output is falsely relabelled. Production downloads identify their
validated supplier output and retain separate fulfilment authorization.

Synthetic 334-product benchmark (7 samples, local PostgreSQL with Python allocation tracing; not hosted capacity):
- v15_baseline: {'median_ms': 46.8, 'python_peak_bytes': 1130794, 'queries_per_refresh': 1, 'response_bytes': 70750, 'dropbox_calls': 0}
- v16_on: {'median_ms': 48.23, 'python_peak_bytes': 1123166, 'queries_per_refresh': 1, 'response_bytes': 70750, 'dropbox_calls': 0}

## Release and rollback (not executed)

1. Review this local diff and supply verified production standards. Obtain owner
   release approval. Check companion is idle before any later configuration rollout.
2. Apply only additive `20261015022631_auto_editions_v16_quality.sql` after existing
   V6/V11/V15 schemas. It creates two private RLS-enabled quality/audit tables and
   indexes; no existing table is rewritten. Browser roles have no access; server
   role cannot delete either table or update the audit. Test the exact migration.
3. Deploy an approved matching revision to the existing app/webhooks/worker only if
   authorized. Preserve V6/V15 gates, all queue priorities and active jobs.
4. Only after schema/standards/capacity checks and explicit approval, enable
   `AUTO_EDITIONS_V16_AUTO_APPROVAL_ENABLED=true` on the app and existing worker.
   The webhook service may share the same setting for consistency; its V15
   registration path is unchanged. The shipped default is false.
5. Run isolated host/Dropbox/production-output and authenticated hosted acceptance;
   local synthetic tests do not establish supplier certification or hosted memory.
6. Rollback: disable V16 flag on app/worker. Legacy preview approval and V15 queue
   remain authoritative; no quality/approval/asset records are deleted. Revoke a
   standard by setting revoked=true in reviewed configuration; changed standard
   fingerprints immediately fence new production jobs, with durable reconciliation.
   Previously archived outputs remain immutable historical files.

Routine operation requires Windows sign-in startup, paired companion, Photoshop,
required fonts, network and disk. It does not depend on Codex or VS Code. Exceptional
hard-kill locks, source repairs and new aesthetic/supplier judgements still need an
administrator. V16 does not alter Shopify products, customers, certificates,
edition allocations, supplier orders, email, advertisements or fulfilment.


## Validation and changed files

- Combined focused regression run: **133 passed, 1 skipped**, 41.99 seconds.
  Modules: quality, status, V15 lifecycle, cloud/API, onboarding API and discovery.
  One older optional PGlite fixture was unavailable; V16 schema, real transactions,
  RLS/grants, idempotency, rollback and restart recovery ran on disposable native
  PostgreSQL bound exclusively to 127.0.0.1 in this assigned worktree.
- Final quality refinements: **37 passed**; explicit 167-Deferred preservation and
  final lock-order/restart checks also passed. Final status/editor stability:
  **44 passed**. These overlap the combined regression; counts are not additive.
- Five focused browser scripts: **9 desktop/mobile scenarios passed**: V16 status
  and Recheck validation, onboarding preview approval, layout setup, status/modal
  edit/scroll preservation and the actual 334-row native Streamlit table at
  1440/390 widths. No production browser/account was used.
- Focused diff whitespace, syntax and Render topology checks passed. No Render
  topology or service configuration was edited.
- Studio Verify parsed the V16 files and passed its infrastructure/secret checks,
  but its overall result is NOT passing: the task's older global base includes
  inherited whitespace issues already present in live 607d10cb (Studio V9 docs,
  legacy Photoshop/test EOFs and tracked tmp logs). Those unrelated files were
  preserved. This task records feature tests as Tested, not committed review-ready.
- Application changes are local only. No live migration, policy activation,
  production approval, source inspection, Photoshop run or supplier test occurred.
  A synthetic supplier fixture proves the implemented gate/export contracts;
  it does not certify any actual artwork or supplier.

Exact focused file inventory follows (relative to the V16 worktree):
- `.env.example`
- `auto_editions_api.py`
- `auto_editions_cloud.py`
- `auto_editions_discovery.py`
- `auto_editions_status.py`
- `auto_editions_store.py`
- `components/auto_editions/download.html`
- `components/auto_editions/onboarding.html`
- `components/auto_editions/setup.html`
- `components/auto_editions/status.html`
- `edition_ops.py`
- `tests/test_auto_editions_onboarding_ui.cjs`
- `tests/test_auto_editions_setup_ui.cjs`
- `tests/test_edition_auto_status_ui.cjs`
- `auto_editions_quality.py`
- `auto_editions_quality_store.py`
- `data/auto_editions_production_standards.json`
- `docs/AUTO_EDITIONS_V16_LOCAL_IMPLEMENTATION.md`
- `supabase/migrations/20261015022631_auto_editions_v16_quality.sql`
- `tests/test_auto_editions_quality.py`
- `tests/test_auto_editions_quality_ui.cjs`
- `docs/AUTO_EDITIONS_V16_TEST_RESULTS.json`
