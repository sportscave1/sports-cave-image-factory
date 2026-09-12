# SC3148 allocation investigation — pending authoritative database audit

Inspected 12 September 2026. No production writes, deployments, migrations or
certificate generation have been performed for this incident.

## Confirmed evidence

- Shopify order `gid://shopify/Order/7408832905523` is PAID, not cancelled.
- It has **one** line, `gid://shopify/LineItem/17545899573555`, quantity **2**,
  variant `gid://shopify/ProductVariant/54020683989299` (Black / L), SKU `FSWOA2B`.
- Product `gid://shopify/Product/10431944393011`, handle
  `the-first-shift-willie-o-ree-wall-art`, is ACTIVE.
- Read-only Shopify inspection returned sports_cave metafields: total 100,
  next 50, last_assigned 49, sold 0, remaining 100, enabled true,
  is_sold_out false. These are mirrors, not proof of allocation history.
- Render webhook service `srv-d9146onlk1mc739nrm7g` received the order at
  `2026-09-11T23:53:03Z`. At `23:53:15Z` the atomic RPC rejected it:
  `Atomic edition suffix is not contiguous ... enforced rows 0, min 0,
  max 0, product sold 0, next 50. Repair is required before allocation`.
- The same guard rejected reconciliation at approximately 23:55 UTC,
  00:11 UTC and 04:18 UTC. The initial result reported zero assignments.

## Confirmed code mismatch

The manual override branch of `_update_edition_product_with_cursor` updates
product/run next pointers while explicitly preserving sold/remaining/history.
Commit `86b331b` restored this editing behaviour. The installed allocator from
`20260828_fix_sparse_legacy_allocator.sql` still requires both next pointers to
equal sold_count + 1 and sold_count to equal last_assigned_edition. It derives
the next allocation from sold_count. Consequently a permitted pointer override
can create a state that this older allocator refuses.

The failure occurs before the quantity loop. There is no evidence that these
two copies raced. The existing RPC already locks by canonical product GID and
locks the product/run rows, inserts all units of a line in one transaction,
and uses channel/order/line/unit identities plus database uniqueness.

**Not yet established:** who/what set this product's pointer, the active run,
historical or reserved #50/#51, partial older allocations, certificates,
adjustment reasons and whether 49 is an approved historical sold baseline.
The Shopify mirror cannot establish those facts. The RPC error excludes only
valid identity-enforced rows in its selected run; it does not prove that all
other history is empty.

## Local changes so far

- Atomic RPC diagnostics now log stable identities and committed unit results,
  reject incomplete unit responses before commit, and report failures without
  copying raw SQL exceptions that could contain customer data.
- Order webhook diagnostic completion events now say failed when allocation or
  mirror errors are present. This does not hide or clear Orders errors.
- `scripts/audit_sc3148.py` uses a repeatable-read, read-only transaction to
  inspect this product/order, allocation numbers, tombstones, adjustment history,
  certificates, repair audit metadata and other lines with the same error.
  It fingerprints the snapshot and complete product allocation rows.

The SQL allocator algorithm is **not changed yet**. No proposed sold baseline
has been applied. Nine added tests cover diagnostics and audit safety; they do
not constitute the requested complete allocator/concurrency regression suite.

Validation: 295 tests run across the incident diagnostics, edition ledger,
atomic incident repair, product webhook restoration, Shopify sync, Edition Ops
and Supabase modules: 261 passed, 34 skipped. All three changed/new Python files
compiled successfully. `git diff --check` passed. No real PostgreSQL concurrency
test or production data readback has been performed.

## Required next step

Use an existing authenticated Supabase connection or OS-configured Render shell
to run the read-only audit. With this local file present in that environment:

```sh
python scripts/audit_sc3148.py
```

Do not paste credentials. No configured local database, Supabase connector or
authenticated database browser session was available during this investigation.

Review the audit before choosing #50/#51 or changing any sold baseline. If either
number is reserved or history conflicts, stop. After a reviewed allocator fix,
use a narrowly scoped, locked, snapshot-guarded repair of this source line,
preserve all old allocation rows, leave certificates missing unless already
present, mirror via the existing service and read back every affected state.
Installing a replacement SQL function is code deployment and is not included
in the user's narrow production data-repair authorization.
