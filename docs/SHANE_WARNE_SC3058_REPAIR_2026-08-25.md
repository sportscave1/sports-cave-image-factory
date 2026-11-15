# Shane Warne and #SC3058 repair — 25 August 2026

## Status

The permanent code changes, database migration, regression tests, and two
hash-bound production repair tools are prepared locally. No production rows,
Shopify metafields, orders, certificates, deployments, OAuth settings, or
services were changed.

The production repair was not applied because this workstation has no Supabase
credentials and the available Render workspace has not yet been confirmed. The
repair tools deliberately refuse to proceed from Shopify evidence alone.

## Immutable Shopify evidence

The affected Shane Warne product is
`gid://shopify/Product/8116473790771`.

| Order | Shopify order GID | Shane line-item GID | Required edition |
|---|---|---|---:|
| #SC3047 | `gid://shopify/Order/7368742928691` | `gid://shopify/LineItem/17467698807091` | derived target `#006` |
| #SC3050 | `gid://shopify/Order/7370333913395` | `gid://shopify/LineItem/17470527865139` | derived target `#007` |
| #SC3055 | `gid://shopify/Order/7372735545651` | `gid://shopify/LineItem/17475102212403` | authorised `#008` |
| #SC3056 | `gid://shopify/Order/7372755468595` | `gid://shopify/LineItem/17475132326195` | authorised `#009` |

The `#006` and `#007` targets follow the paid-order chronology of the requested
nine-order sequence; the script does not assume them from the order numbers. It
checks the complete sequence and refuses to write if the production ledger,
paid states, quantities, product GIDs, line-item GIDs, or active run differ.

The separate Michael Jordan line in #SC3056 is
`gid://shopify/LineItem/17475132293427`, product
`gid://shopify/Product/8452870799667`. Its row fingerprint is included in the
dry run and must be byte-for-byte unchanged after apply.

There is a material evidence conflict which requires the Supabase dry run:
Shopify also shows #SC2905 and #SC2930 as paid, fulfilled Shane Warne orders with
customer certificate/allocation metadata. The authorised repair tool treats any
valid Shane allocation outside the exact nine-row target as a blocker. It will
not discard those rows merely to make the counter equal nine.

The missing eBay order is:

- Order: #SC3058, `gid://shopify/Order/7373639811379`
- Source: `ebay-au`, Shopify Marketplace Connect / eBay Australia
- State: paid, unfulfilled, non-test, not cancelled
- Line: `gid://shopify/LineItem/17476720886067`, quantity one
- Product: Muhammad Ali, `gid://shopify/Product/8887274373427`
- Variant: `gid://shopify/ProductVariant/48821710029107`
- SKU: `MALIAMOTIVATIONALA4B`

This proves the canonical product and variant without title matching. The next
Muhammad Ali edition must still be read from the valid Supabase allocation
ledger. Shopify's current counters are not allocation authority.

## Proven Shane Warne cause

The first observable bad allocation was historical order #SC2762. On 22 June it
copied the editable Shopify product cursor `91` into an order allocation through
the former `order_allocator.py` metafield allocator. The later Supabase flow
trusted that promised number and used `MAX(edition_number) + 1` as a permanent
floor, propagating `#092` through `#100`.

Production logs previously showed that the unique allocation-key index failed
to create because duplicate keys already existed and the schema helper
continued. They also showed #SC3047 and #SC3050 each allocated once, with
reconciliation finding existing assignments. Certificate generation read the
existing allocation rows. Thus duplicate delivery, reconciliation replay, and
certificate regeneration did not create #099/#100; the poisoned cursor/maximum
floor did.

The exact actor that originally set the editable cursor to `91` is not present
in retained evidence and is not guessed.

## #SC3058 failure boundary

The deployed webhook health endpoint reported the same commit as the local
HEAD. That code contains no channel allowlist excluding eBay and stores an order
snapshot before product allocation. A persisted-but-unmatched eBay line should
therefore be visible in a review state. Because #SC3058 is absent from the
Orders table, the failure is before durable order persistence: webhook delivery
was missed, processing failed before persistence, or reconciliation did not
successfully recover it.

The exact branch cannot be distinguished without the webhook/reconciliation
logs and Supabase receipt/order rows. The local implementation does not claim a
more specific cause.

## Permanent controls

- Canonical Shopify orders use Shopify order GID and line-item GID. Channel is
  retained as metadata, so Online Store, Shop, Etsy, `ebay`, `ebay-au`, and eBay
  Australia all enter the same paid-order pipeline.
- Direct marketplace events use a channel-qualified source-unit identity:
  `source_channel + external_order_id + external_line_item_id + unit_ordinal`.
- Database uniqueness protects both source units and
  `(Shopify product GID, edition number)`.
- Allocation is a single transaction protected by transaction advisory and row
  locks. Quantity is allocated atomically and contiguously; `#101` is rejected.
- Counters are derived from valid ledger rows. Product sync cannot reset them.
- Historical reconciliation stores rows without allocating unless a separate,
  approved, hash-bound backfill is used.
- Shopify-hosted marketplace lines resolve first by exact product and variant
  IDs, then exact approved SKU or marketplace mapping. A supplied variant-ID
  mismatch cannot fall back to product-only matching. Direct marketplace lines
  require approved SKU/mapping. Title and handle similarity are never used.
- Unmatched marketplace lines are persisted in quarantine/review without
  blocking valid sibling lines or allocating any product.
- Shopify metafields are mirrored only after commit. GraphQL transport errors
  and `userErrors` leave a retryable mirror task and never reallocate.
- Reconciliation uses a bounded overlapping lookback plus durable order/line
  idempotency, so webhook, polling, manual retry, restart, and concurrency
  converge on the same allocation.

## Hash-bound production dry runs

Run these only in the authenticated production service environment after the
atomic-ledger migration has been reviewed and installed. Both commands are
read-only by default and write sanitized snapshots/reports to local output.

```powershell
.\.venv\Scripts\python.exe scripts\repair_shane_warne_editions.py
.\.venv\Scripts\python.exe scripts\recover_sc3058.py
```

Apply requires the exact generated report path and SHA-256, re-reads all
production evidence, takes an advisory lock, archives before-images, scopes the
write to the approved identities, verifies readback, and records an audit row.
The Shane tool supports guarded rollback. The #SC3058 tool calls the normal
ingestion pipeline and proves that a second run is a no-op.

No apply command can be safely completed until a blocker-free production dry
run has established the live Shane and Muhammad Ali ledgers.
