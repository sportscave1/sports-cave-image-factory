# Edition Ops numbering incident — 25 August 2026

> Historical incident report. The later, narrowly authorised #SC3055/#SC3056
> correction and #SC3058 eBay recovery are tracked in
> `docs/SHANE_WARNE_SC3058_REPAIR_2026-08-25.md`. Where the later authorisation
> differs from this report's original no-renumbering constraint, the later user
> request and current production evidence govern.

## Outcome

The jump was not caused by the two recent Shane Warne customers, by a duplicate
delivery of either recent webhook, or by certificate regeneration.  The first
observable corrupt allocation was historical Shopify order `#SC2762`.  On
22 June 2026 it copied an already-high editable Shopify product cursor into a
durable order allocation as edition `#091`.  The Supabase allocator subsequently
treated that order snapshot and the maximum existing allocation as a lower bound,
so later legitimate paid orders continued at `#092` through `#100`.

The exact origin of the value `91` before it was copied to `#SC2762` is not
available in Shopify's current-value API or the retained application logs.  It
may have been an earlier manual/counter sync value, but that is not asserted as
fact.  The confirmed fault is that an editable counter was trusted as allocation
authority, a historical order was allowed through a new-order path, and that
unverified number was then made irreversible by the promised-number/MAX-ledger
floor logic.

No production data was changed during this investigation.

## Confirmed production evidence

Canonical product identity:

- Shopify product GID: `gid://shopify/Product/8116473790771`
- Current handle: `shane-warne-framed-art`
- Product title: `Shane Warne Tribute Wall Art`

The Shopify product is in a split-brain state:

- Canonical storefront fields, updated 25 August 2026 00:29:34 UTC: next `10`,
  sold `9`, remaining `91`.
- Legacy Edition Ops fields, updated 23 August 2026 01:59:18 UTC: next `101`,
  last `100`, sold `100`, remaining `0`, sold out.

The order evidence is:

| Edition | Order | Shopify order GID | Shopify line-item GID | Order time UTC | Allocation/certificate evidence UTC | Source/status |
|---:|---|---|---|---|---|---|
| 091 | #SC2762 | `gid://shopify/Order/7201680720179` | `gid://shopify/LineItem/17183921471795` | 2026-06-08 | allocation metafield 2026-06-22 22:37:03 | Shopify web / paid; historical at allocation time |
| 092 | #SC2905 | `gid://shopify/Order/7260692316467` | `gid://shopify/LineItem/17287645167923` | 2026-07-09 | 2026-07-10 | Shopify web / paid |
| 093 | #SC2930 | `gid://shopify/Order/7270464684339` | `gid://shopify/LineItem/17305630638387` | 2026-07-14 | 2026-07-15 | Shopify web / paid |
| 094 | #SC2964 | `gid://shopify/Order/7313555456307` | `gid://shopify/LineItem/17370930610483` | 2026-07-29 | 2026-07-30 | Shopify web / paid |
| 095 | #SC3034 | `gid://shopify/Order/7360091095347` | `gid://shopify/LineItem/17451635048755` | 2026-08-19 | 2026-08-20 | Shopify web / paid |
| 096 | #SC3038 | `gid://shopify/Order/7366416498995` | `gid://shopify/LineItem/17463561519411` | 2026-08-20 | 2026-08-21 | Shopify web / paid |
| 097 | #SC3041 | `gid://shopify/Order/7366779830579` | `gid://shopify/LineItem/17464233689395` | 2026-08-21 | 2026-08-21 | Shopify web / paid |
| 098 | #SC3043 | `gid://shopify/Order/7367208042803` | `gid://shopify/LineItem/17464949997875` | 2026-08-21 | 2026-08-22 | Shopify web / paid |
| 099 | #SC3047 | `gid://shopify/Order/7368742928691` | `gid://shopify/LineItem/17467698807091` | 2026-08-22 | 2026-08-24 | Shopify web / paid |
| 100 | #SC3050 | `gid://shopify/Order/7370333913395` | `gid://shopify/LineItem/17470527865139` | 2026-08-23 | 2026-08-24 | Shopify web / paid |

There are no current Shopify allocation/certificate metafields for Shane Warne
editions `#001`–`#090`.  A read-only 30-day Shopify query around the initial
allocation found one Shane Warne paid unit, `#SC2762`, not 90 units.

Production Render logs add the following database/runtime evidence:

- On 18 August 2026 04:22:56 UTC, schema setup logged a `UniqueViolation` while
  creating `idx_edition_orders_allocation_key_unique`; the old schema helper
  caught the error and continued.  Production therefore contains duplicate
  allocation keys and was running without its intended uniqueness barrier.
- `#SC3047` was allocated once by its paid webhook: one new line, one assignment,
  zero existing assignments, successful mirror.
- `#SC3050` was allocated once by its paid webhook with the same one/zero result.
- Reconciliation subsequently processed both orders as
  `refreshed_existing_assignments`; a later batch reported 14 assignments,
  zero new and 14 existing.  Webhook plus reconciliation was idempotent for these
  orders.
- Certificate generation used existing Supabase edition-order rows: row `368`
  for `#099` and row `371` for `#100`.  It did not call an allocation path.

No customer names, emails, addresses, or credentials are included here.

## Code path that propagated the jump

Commit `21a7113` introduced the June Shopify-metafield allocator in
`order_allocator.py`.  Its allocation flow read the product
`edition_next_number`, assigned that value to an order, then incremented the
product metafield without a database allocation ledger or row lock.  That is the
path that wrote `#091` to historical order `#SC2762` on 22 June.

The later Supabase flow in `supabase_backend.py` compounded the problem:

1. `promised_edition_hint_for_order_line` trusted the order allocation metafield.
2. The former `allocate_edition_for_order_line` accepted that promised number.
3. Its counter correction used `MAX(edition_orders.edition_number) + 1` as a
   floor and never lowered it.
4. Normal paid orders therefore received `#092` through `#100`.

An earlier Edition Ops refresh path also recalculated order allocations from a
30-day Shopify fetch and advanced products from the maximum order number.  It
was capable of replay corruption, although the read-only Shopify record set
shows that it did not create 90 Shane Warne sales during the relevant window.

## Ruled out for #099 and #100

- Duplicate webhook delivery: the durable receipt and allocation logs show one
  new assignment for each order.
- Reconciliation/polling replay: later runs found existing assignments and
  created zero.
- Fulfilment/status change: those runs refreshed existing rows only.
- Certificate creation/regeneration: the certificate path consumed existing
  edition-order IDs 368 and 371.
- Etsy/eBay direct allocation: both orders were Shopify `web` orders.  An Etsy
  order after `#SC3050` was not allocated because the product was already shown
  as sold out.
- Quantity expansion: each recent line quantity was one and produced one row.

## Allocation eligibility policy

Only an order whose financial status is exactly `PAID`, with a non-empty line
set, may enter allocation.  Test, cancelled, pending, unpaid, partially paid and
already-refunded orders do not allocate.  A later cancellation/refund or
fulfilment update never creates, revokes, reuses or renumbers an existing issued
edition; it remains an auditable order-state change and any customer-facing
repair is sent to manual review.  Historical orders are stored without an
allocation unless a separately approved, hash-bound backfill workflow is used.

## Permanent controls implemented locally

- The source-unit key is channel-aware:
  `source_channel + external_order_id + external_line_item_id + unit_ordinal`.
  Shopify, Etsy and eBay numeric IDs therefore cannot collide.
- The database enforces one row per source unit and one row per product
  GID/edition number.  Allocation takes a transaction-scoped advisory lock plus
  product/run row locks, inserts the complete line quantity, derives counters
  from valid ledger rows, and rejects any non-contiguous ledger or edition above
  `#100`.
- Repaired/deleted source units leave durable tombstones.  A replay of an
  archived order line is rejected instead of becoming a new allocation.
- Shopify-hosted orders resolve by their exact canonical Shopify product and
  variant IDs, regardless of whether their displayed channel is Online Store,
  Shop, Etsy, or eBay. Direct Etsy/eBay payloads resolve only through an active
  explicit listing/external-variant/SKU mapping. Missing or ambiguous mappings
  are persisted in the quarantine table; title and handle fallback is absent.
- Historical reconciliation stores orders without allocation by default.  The
  old Limited Editions CSV apply paths, Stage 3 direct importer apply mode,
  Shopify-product-metafield allocator, SQLite allocator and promised-number
  allocator are disabled.
- Shopify metafields are written only after the database transaction commits.
  Canonical and legacy fields are mirrored together; GraphQL transport errors
  and `userErrors` fail the mirror, while a durable `pending`/`failed` state is
  retried without allocating again.
- Edition Ops and storefront read sold/remaining/next values from valid ledger
  history.  Counter editing, counter resets, CSV counter replacement, new-run
  resets and handle/title CSV identity matching are disabled.

## Products requiring production reconciliation

A read-only comparison of 338 Shopify products found 235 Edition Ops products
and 37 products whose canonical and legacy storefront counters disagree.  This
does not prove that every allocation below is invalid; it is the affected audit
set that must be reconciled before its counters are trusted.

| Product | Shopify GID suffix | Canonical next/sold/remaining | Legacy next/sold/remaining |
|---|---:|---:|---:|
| Ben Cousins Eagles Art | 9155735978291 | 60 / 0 / 41 | 1 / 0 / 100 |
| Blue Heaven LA Legacy | 10377381577011 | 6 / 5 / 95 | 2 / 1 / 99 |
| Brett Binga Lee | 8944788537651 | 101 / 74 / 0 | 75 / 74 / 26 |
| Carlos Alcaraz | 8575212323123 | 70 / 49 / 31 | 50 / 49 / 51 |
| Chautauqua | 9376016105779 | 50 / 49 / 51 | 2 / 1 / 99 |
| Chef Curry | 8900605870387 | 90 / 73 / 11 | 74 / 73 / 27 |
| CR7 Collector | 8141102711091 | 10 / 9 / 91 | 81 / 80 / 20 |
| Ronaldo Free Kick | 9001283387699 | 101 / 76 / 0 | 77 / 76 / 24 |
| Ronaldo Siuuu | 8866756165939 | 101 / 74 / 0 | 75 / 74 / 26 |
| Daniel Ricciardo | 8106693984563 | 90 / 55 / 11 | 56 / 55 / 45 |
| Dennis Rodman | 10069937357107 | 101 / 76 / 0 | 77 / 76 / 24 |
| Design Your Own | 9942590357811 | 60 / 59 / 41 | 1 / 0 / 100 |
| Maradona | 8146485117235 | 101 / 48 / 0 | 49 / 48 / 52 |
| Dwyane Wade | 8894611030323 | 85 / 66 / 16 | 67 / 66 / 34 |
| Giannis | 8361636167987 | 90 / 64 / 11 | 65 / 64 / 36 |
| Jack Brabham | 9743477637427 | 101 / 60 / 0 | 61 / 60 / 40 |
| Jaylen Brown | 9357445923123 | 101 / 76 / 0 | 77 / 76 / 24 |
| Joel Embiid | 8807794704691 | 101 / 35 / 0 | 36 / 35 / 65 |
| King James | 8946605523251 | 101 / 65 / 0 | 66 / 65 / 35 |
| Messi Fight Dream | 8889835192627 | 101 / 73 / 0 | 74 / 73 / 27 |
| Messi Barca | 8198420136243 | 101 / 75 / 0 | 76 / 75 / 25 |
| Marcus Rashford | 8286069227827 | 101 / 53 / 0 | 54 / 53 / 47 |
| Michael Jordan Dunk | 8135329382707 | 101 / 71 / 0 | 72 / 71 / 29 |
| Neymar | 8872588509491 | 92 / 74 / 9 | 75 / 74 / 26 |
| PSG Back To Back | 10207406784819 | 80 / 56 / 21 | 57 / 56 / 44 |
| Roger Federer | 9434618265907 | 85 / 88 / 16 | 89 / 88 / 12 |
| Shane Warne | 8116473790771 | 10 / 9 / 91 | 101 / 100 / 0 |
| Stephen Curry Golden | 8183144907059 | 101 / 81 / 0 | 82 / 81 / 19 |
| 1992 Finish | 10087020724531 | 101 / 72 / 0 | 73 / 72 / 28 |
| 93rd Minute Beckham | 9358793736499 | 91 / 66 / 10 | 67 / 66 / 34 |
| East Tatum Giannis | 10143162925363 | 101 / 71 / 0 | 72 / 71 / 29 |
| Era Bonds Griffey | 10134744203571 | 101 / 90 / 0 | 91 / 90 / 10 |
| Final Crown Spain | 10323221905715 | 11 / 0 / 90 | 1 / 0 / 100 |
| New Kings Crosby | 10139335328051 | 101 / 46 / 0 | 47 / 46 / 54 |
| Titans Ruth Gehrig | 10115562111283 | 65 / 79 / 36 | 80 / 79 / 21 |
| Victory Burns Logano | 10332449046835 | 50 / 49 / 51 | 1 / 0 / 100 |
| Without A Fight Melbourne Cup | 8106660692275 | 101 / 80 / 0 | 81 / 80 / 20 |

## Shopify-evidence Shane Warne dry run

The evidence available without direct production Supabase credentials gives:

- Verified paid, customer-issued allocations to preserve: 9 (`#092`–`#100`).
- Suspect invalid allocation precursor requiring live certificate/manual review:
  1 (`#091`, historical `#SC2762`, with no current Shopify customer-certificate
  evidence).  It is not safe to archive automatically from Shopify evidence alone.
- Verified allocations for `#001`–`#090`: 0.
- Verified sold count: 9.
- Mathematical remaining count: 91 of 100.
- Highest preserved customer edition: 100.
- Safe next edition: none. Going to `#101` violates the limit; going to `#001`
  or `#010` resets/moves backwards; renumbering `#092`–`#100` violates the
  preservation rule.
- Proposed automatic write: none. Allocation must remain frozen until the
  Supabase dry run identifies the exact live rows, surfaces any handle-only
  identity candidates, and a human verifies every issued certificate.

The production dry-run command is:

```powershell
.\.venv\Scripts\python.exe scripts\reconcile_edition_ledger.py --product-gid gid://shopify/Product/8116473790771
```

It writes a sanitized immutable snapshot and a hash-bound proposal under
`output/edition_ops_reconciliation/`.  Apply mode requires that exact report
hash, rechecks that the ledger has not changed, archives every removed row, and
records a repair audit.  Rollback requires the generated repair key and refuses
to run if later allocations exist.  The script never mutates Shopify.

## Production sequence when explicitly authorized

1. Pause order allocation workers, but continue accepting/storing webhook
   receipts for retry.
2. Run the Shane dry run and the same report for all 37 audit products.
3. Review paid status, source identity, quantities, certificates, refunds and
   marketplace mappings.  Resolve every `manual_review` item.
4. Take the Supabase backup/snapshot represented by the dry-run artifacts.
5. Review and install `migrations/20260825_atomic_edition_allocation_ledger.sql`.
   Its unique indexes intentionally fail if any duplicate remains, so any
   blocking duplicate must first receive a separately approved, audited repair.
6. Apply only an approved, blocker-free product repair report using its exact
   SHA-256. The incident-specific Shane tool verifies the atomic migration
   prerequisites before writing.
7. Deploy the code and resume workers. Pending/failed Shopify mirrors are
   retried from the committed ledger without reallocating.
8. Verify Supabase counters, all canonical and legacy Shopify metafields,
   Edition Ops, and the storefront widget for each repaired product.

No migration, apply command, deploy, OAuth change, record deletion, commit or
push was performed as part of this work.
