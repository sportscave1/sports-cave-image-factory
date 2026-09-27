# Edition Ops designs tracking

Open **Designs tracking** at the bottom of Edition Ops.

- Edit Product, Date created, First order and Designed by directly in the grid.
  Editing Product changes the tracker label only; it does not rename Shopify products.
- Paste cells or use Enter/Tab to commit edits. Changes save automatically, without
  a separate Save click. Only admins may edit the Bonus paid date.
- **Add product** creates a saved tracker row, sets Date created to today in Sydney
  by default, and fills Designed by from the signed-in account's persisted name.
- Products created in Edition Ops from 1 September 2026 onward are also discovered
  when the tracker loads. A webhook has no OS account identity, so automatic
  imports leave Designed by blank instead of crediting whoever opens the tracker.
- First order is fully manual. Existing first orders were preserved once during
  migration. Subsequent order sync never fills or replaces the cell. Clearing it
  stays cleared.
- Date created initially uses the product's Edition Ops creation date (Sydney).
  Manual rows use the date entered on Add product. Both are editable.
- The existing bonus dates and payment receipts are retained. Staff edits to other
  cells cannot change Bonus or its historical receipt. To mark a new bonus paid,
  the admin enters a date after a First order has been entered; that order does not
  need to exist in Shopify. The payment receipt records the order as entered.
- Existing rows cannot be deleted through the table. Refresh discovers new rows,
  and normal reruns refresh after 60 seconds when there are no unsaved drafts.

## Persistence and concurrency

All rows live in the original `edition_design_tracking` table. The spreadsheet
upgrade adds a UUID row key, optional unique Edition Ops product link, editable
title/date/order and creator ID. No order payloads or customer data are copied.
The old product-ID unique key keeps the prior app compatible during deployment.

Saves contain only edited fields. Short transactions lock rows in stable ID order.
Edits to different cells merge; edits to the same changed cell are rejected without
overwriting another user's data. Multi-cell pastes commit atomically. Repeated
save requests and Add product retries are idempotent.

The browser session retains a failed-save draft when collapsing, navigating, or
requesting Refresh. **Retry saving** retries it; **Discard unsaved edits and reload**
explicitly discards only the draft. A failed save is visibly marked unsaved:
only successful saves are durable across a browser/session restart. A different
login never inherits another account's draft.

Authorization rechecks the stored OS account, session version and Edition Ops
permission for each backend read/write. Bonus changes require the database's
admin role. RLS remains enabled and public/client grants are revoked.

## Migration and verification

- Base: `20260927221221_edition_design_tracking.sql`.
- Upgrade: `20260927223857_edition_design_tracking_spreadsheet.sql`.
- Both are included in the SHA-reviewed deployment manifest.
- The upgrade keeps all existing rows and receipts in place and snapshots the
  existing displayed orders exactly once. It is safe to replay without replacing
  edited values.
- Run `python -m unittest tests.test_design_tracking -q` for permission, concurrency,
  idempotency, real Streamlit autosave/reload, Add product and failed-draft tests.
