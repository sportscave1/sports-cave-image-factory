# Limited Editions Phase 2

Sports Cave OS now keeps limited edition tracking inside Supabase instead of relying on the legacy Google Sheet.

Supabase remains the source of truth for edition counts, order allocations, and audit history. Cloudflare R2 is only for file/object storage. Google Drive links still remain available for PSD and production files.

## Core Tables

- `edition_products` stays as the Shopify product registry and compatibility mirror.
- `edition_runs` stores the active edition counter for a product.
- `edition_orders` stores allocated customer/order editions and now supports `edition_run_id` and `edition_name`.
- `edition_adjustments` stores manual counter and total changes made through the app.

## Daily Workflow

1. Open `Limited Editions`.
2. Use `Sync Product Updates` to bring Shopify product changes into Supabase.
3. Review the `Edition Tracker` grid.
4. Edit `Edition name`, `Latest sent`, `Next edition number`, `Total editions`, or `Status`.
5. Click `Save Tracker Changes`.

Changing `Latest sent` saves `next_edition_number = latest_sent + 1`.

## Restarting at 1/100

Do not lower an existing run back to `1`.

Use `Start New Edition Run` when a product needs a new `1/100` sequence. Sports Cave OS archives the current run, creates a new active run at `#1`, updates `edition_products.active_edition_run_id`, and keeps old orders/certificates intact.

## CSV Import

Use `Import Limited Edition CSV` for the old Google Sheet.

Supported column names include:

- `Shopify Product ID`
- `Shopify Handle`
- `Product Title`
- `Edition Name`
- `Latest Sent`
- `Current Number`
- `Next Edition Number`
- `Total Editions`
- `Edition Total`
- `Status`
- `PSD Link`
- `Prodigi Link`

Import is preview-first. The app shows matched products, createable products from Shopify sync, unmatched rows, and old/new counter values before applying changes.

Title-only matching is intentionally disabled. Match by Shopify product ID first, then Shopify handle.

## Safety Rules

- Duplicate edition numbers are blocked per `edition_run_id`.
- Historical allocations are not deleted.
- Old customer/order records are not overwritten.
- Lowering a counter below the highest allocated number in the active run is blocked.
- Manual next-number or total changes create `edition_adjustments` rows.
- R2 is not used for edition counts.
