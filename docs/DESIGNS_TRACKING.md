# Edition Ops designs tracking

At the bottom of Edition Ops, open **Designs tracking**. The table includes
all Edition Ops products created from 1 September 2026 (Sydney time) onward.
New products appear on reopening the panel or selecting **Refresh designs**.

- **Product** and **First order** are read-only, matched by immutable product IDs.
- Staff with Edition Ops access can enter **Designed by**.
- Only an active admin can enter or clear **Bonus**, a date recording when the
  first-sale bonus was paid. Both manual fields start blank.
- Press **Save design tracking** to persist edits. Refreshing or closing the
  panel discards unsaved edits. Conflicting saves ask the user to refresh.

The first order is the earliest non-test, non-cancelled recorded order from
Shopify order lines or valid edition allocations, across the product's full
recorded history. An order need not already have an edition allocation to
appear. Cancelled/test Shopify orders and invalid edition allocations are
excluded. Data freshness follows the existing order sync; the tracker does
not call Shopify or start a new sync job.

Saving a paid date verifies the displayed first order against current stored
orders, then retains its ID and name with the payment receipt. That displayed
order remains fixed while paid, even if historical orders are later imported.
Clearing the paid date also clears that receipt and returns to the current
first-order lookup. Editing a designer preserves the payment receipt.

Storage is one sparse row per manually edited product in
`edition_design_tracking`, with a primary key preventing duplicate bonuses
per product. No catalogue copies, order payloads, customer data, periodic
snapshots or background jobs are added. Reads happen only while the panel is
opened/refreshed, with a stable per-session editing snapshot. An index on the
existing allocation ledger's product GID avoids repeated ledger scans.

The table has RLS enabled and no client grants/policies. Only the trusted
server database connection accesses it. Every backend read/write rechecks
the persisted OS account, session version and Edition Ops permission; bonus
changes additionally require the persisted admin role. Product-row locks and
version checks prevent first-insert races and lost updates; batches commit
atomically. Only the current editor and bonus author are retained, rather
than a growing audit history.

Migration: `migrations/20260927221221_edition_design_tracking.sql`, included
in the SHA-reviewed startup migration manifest. No Render topology changes.

Tests: `python -m unittest tests.test_design_tracking -q` includes real
Streamlit editor submission/reload tests and backend permission, stale-write,
payment-order association and transaction rollback checks.
