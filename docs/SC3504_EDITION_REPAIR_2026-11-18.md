# SC3504 missing edition — 18 November 2026

Task: `20261118-6e21f0a9`; owner: `codex-sc3504-20261118-01a1ecdc`.
User authorized diagnosis, prevention and restoring the correct edition on this
order. Production changes were confined to this order/product repair and its
Shopify product mirror. No commit, deployment, email or certificate generation.

## Confirmed cause and numbering

The paid, uncancelled order's Legends Never Die / Messi vs Ronaldo line failed
with `Sales unit counters require review; cursor is independent`. Its product
had total 100, sales 92, remaining 7, next 94; product/run cursors agreed. The
allocator correctly refused the inconsistent sales/remaining pair.

Product GID: `gid://shopify/Product/10057331147059`; run:
`2ca35c93-bd78-477a-9c4b-43fc38624611`. Order GID:
`gid://shopify/Order/19028268351795`; line: `50953359393075`;
variant: `52962949071155`.

There were 52 valid legacy rows, numbered 42–93, and a recorded legacy baseline
of 40. Thus recorded sales 92 were preserved; numbers were not treated as unit
counts. No newer pending order for this product preceded SC3504. Edition 94 was
unused and was accepted by the allocator's collision/tombstone checks.

The recalculation helper `_recalculate_next_edition_number_with_cursor` can
reproduce this exact inconsistency: it wrote remaining as total minus maximum
issued edition, without updating sales. Audit history does not establish which
historical invocation produced this product's mismatch; do not claim that is
proven. Latest pre-repair Shopify mirror still advertised next 93, sales 92,
remaining 8, while allocation 93 had already been issued to SC2985.

## Applied live repair

In one transaction, acquired the allocator's product advisory lock and locked
the product, run, order and line. Asserted the observed identities, paid state,
quantity, counters, run and legacy ledger count. Corrected remaining 7 → 8,
preserving sales 92 and next 94, then invoked the existing atomic allocator.
It created edition **094/100**. Updated both numeric/GID line aliases to Assigned
and cleared their errors. Recorded the before/after in `audit_logs`.

Post-allocation state: next 95, sales 93, remaining 7, last assigned 94. Existing
Captain's Last Dance allocation 080/100 was unchanged. Updated eight existing
Shopify product metafields using compare-and-set digests, then independently
read all thirteen edition fields back and verified them. Recorded successful
mirror state and audit evidence. Replaying the allocation using numeric aliases
returned `was_created=false`, edition 94. Both order allocations are valid and
their product mirror status is synced. No existing edition was renumbered.

## Local prevention and validation

Recalculation now derives remaining from recorded sales, refuses missing or
out-of-range sales before writes, and uses next=101 after edition 100 rather
than advertising an already-issued number. Sales capacity also determines the
sold-out flag. Added regressions for this incident, numbering offsets, exhausted
numbers, exhausted sales and invalid sales; updated existing recalculation tests.

44 selected offline tests passed across `test_edition_recalculation_sales`,
`test_edition_ledger_regressions`, `test_independent_edition_cursor` and the two
recalculation tests in `test_shopify_sync.SupabaseOrderSyncLogicTests`.
The broader run hit one environment error: `test_normal_startup_never_runs_incident_repairs`
imports `webhook_server`, but FastAPI is not installed locally. That test was
explicitly excluded from the 44-test run, not counted as passing.
`git diff --check` passed.

Prevention code remains uncommitted and undeployed under local-only rules.
This fixes the identified recalculation defect; it cannot promise that all
future allocation failures are impossible. Production UI was not visually
inspected; its authoritative allocation and line status records were verified.

## Authorized prevention release

The user subsequently explicitly authorized deployment and required the missing
FastAPI dependency and tests to be fixed first. Installed the already-declared
FastAPI and PostgreSQL driver dependencies locally, and aligned Streamlit with
the existing 1.58 test environment. No production dependency changes are needed.
Corrected the table test's fake backend to supply its settings-reader interface.
The combined UI suite exposed shared Streamlit form/fragment context; the release
runner now runs each module in a fresh process rather than excluding UI tests.

Rebased the focused commit onto verified live main
`a4d96d3d2ca776525938df2a2d2a499be44d3fa1`, preserving the newer Home and product
onboarding changes. Release checks: 204 active Python tests passed across six
complete modules (238 discovered, 34 existing retired-allocator skips), plus 18
isolated PostgreSQL/PGlite allocation scenarios. No FastAPI test is excluded.
Render topology validation passed. These are the relevant release suites, not
a claim that every unrelated repository test was executed.

Reproduce with `scripts/run_edition_recalculation_checks.ps1 -PGLiteModule
<absolute-path-to-pglite/dist/index.js>`. The PGlite scenarios are in-memory and
have no production connection. Preserve exactly one existing primary service;
no Blueprint or migration changes are part of this release.
