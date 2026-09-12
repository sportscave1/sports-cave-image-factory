# SC3148 allocation investigation â€” pending authoritative database audit

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


## Authoritative audit and approved final repair — 12 September 2026

User explicitly approved commit, push main and deploy in the conversation.
Read-only audit ran in the existing webhook Render service at 05:00:45 UTC.

- Product 657 / gid://shopify/Product/10431944393011, run 9799b113-0ff2-4dd6-9185-381357d04748.
- Supabase: total 100, next 50, sold 0, remaining 100; enabled, active run.
- Manual adjustment c50e76f5-e622-412b-ba24-b63e4e59c647 changed next 1 to 50 on 6 September without sales.
- No product allocations, tombstones/reservations or certificates. Numbers 50/51 are unused.
- Order 7408832905523 is PAID, not cancelled; one line 17545899573555, quantity two, variant 54020683989299.
- Ingestion contains numeric and GID aliases for this same line, both Error. These must become two physical units, never four.
- Other failures matching the old SQL invariant: only these SC3148 aliases.
- Old RPC definition MD5: 1e5f260172220751170863b927f1f2a8.
- Audit snapshot SHA256: 9e15ed654a17b2670c69b032196dc3e7c544c4dba816960017a1cf508eec94d6.

The old RPC required next=sold+1 and last_assigned=sold before entering its quantity loop.
This was not a two-line race. The valid manual cursor triggered that incorrect precondition.
The replacement uses the locked cursor, counts only newly committed units, preserves source-unit
identities on retries and rejects occupied/reserved numbers, inactive runs and inconsistent sales.

The reviewed migration installs only a function; it does not rewrite historical product rows.
The explicitly gated incident helper backs up original records and the old function in
edition_repair_audits, installs the function and allocates SC3148 in one transaction. It updates
both ingestion aliases through the existing status helper. After commit it invokes the normal
single-product Shopify mirror and reads the normal Orders and Edition Ops loaders. It never
creates or sends certificates. Restart after commit validates existing units and only retries the mirror.

Expected verified result: editions 50/51, next 52, sold 2, remaining 98. Production execution and
final readback are recorded below when complete.

Validation: 16 actual PostgreSQL/PLpgSQL scenarios executed using isolated PGlite 0.5.8.
PGlite serializes connections; cross-process exclusion relies on the existing PostgreSQL advisory
transaction lock, product/run FOR UPDATE locks and source-unit/run-number unique constraints.
Relevant Python modules are run in separate processes because a combined broad unittest discovery
leaks Streamlit form context between unrelated UI suites. The isolated Edition Ops UI tests pass.
