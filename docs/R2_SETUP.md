# Cloudflare R2 Setup

Cloudflare R2 is used by Sports Cave OS for private object storage only. Supabase remains the source of truth for products, Shopify orders, limited edition numbers, certificate records, and file metadata.

Google Drive links are still supported and remain the human working area for PSDs and product folders. R2 adds internal storage for generated or archived files; it does not replace Drive.

## Required Render Environment Variables

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_ENDPOINT
R2_BUCKET_CERTIFICATES=sports-cave-certificates
R2_BUCKET_ASSETS=sports-cave-assets
R2_BUCKET_BACKUPS=sports-cave-backups
R2_BUCKET_PSD_ARCHIVE=sports-cave-psd-archive
R2_PRESIGNED_URL_EXPIRY_SECONDS=3600
```

Do not commit these values to GitHub. Store them only in Render or your local private environment.

## Buckets

```text
sports-cave-certificates
sports-cave-assets
sports-cave-backups
sports-cave-psd-archive
```

Buckets should stay private. Sports Cave OS generates presigned download links only when a user needs temporary access.

## What Goes To R2

Certificate PDFs:

```text
certificates/{shopify_handle}/{shopify_order_name}/edition-{edition_number}.pdf
```

Certificate PNG previews:

```text
certificates/{shopify_handle}/{shopify_order_name}/edition-{edition_number}-preview.png
```

Generated mockups and WebPs:

```text
mockups/{shopify_handle}/{frame_type}/{filename}
```

ZIP exports:

```text
exports/{date}/{filename}
```

Final approved PSD archive copies:

```text
psd-archive/{shopify_handle}/{filename}
```

Backup test upload:

```text
test/sports-cave-os-r2-test.txt
```

## Supabase Metadata

Run `migrations/create_file_assets_table.sql` if you want to apply the schema manually. The app also creates the same table and columns additively during Supabase schema checks.

R2 object metadata is stored in `file_assets` with:

```text
asset_type
bucket
object_key
filename
mime_type
size_bytes
related_shopify_product_id
related_shopify_order_id
related_shopify_handle
related_edition_order_id
source
status
```

Certificate R2 pointers are also saved back onto `edition_orders` and `certificates`:

```text
certificate_r2_bucket
certificate_r2_key
certificate_preview_r2_bucket
certificate_preview_r2_key
```

Existing `certificate_file_url`, `certificate_shopify_file_id`, `shopify_file_url`, and Google Drive fields stay in place for backward compatibility.

## Testing From The App

1. Open `Developer`.
2. Expand `Cloudflare R2 Storage`.
3. Confirm the app shows R2 configured and endpoint configured.
4. Click `Test R2 connection`.
5. Click `Test R2 upload`.
6. Confirm the uploaded object key is `test/sports-cave-os-r2-test.txt`.
7. Open the temporary download link.

If Supabase is missing or `file_assets` has not been created yet, the upload can still succeed. The app will show a warning that metadata was not saved.

## Troubleshooting

If R2 is not configured, confirm these Render variables are present and not blank:

```text
R2_ENDPOINT
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET_BACKUPS
```

If the connection test fails, confirm the key has access to the bucket shown in the panel.

If test upload succeeds but no metadata row is saved, run:

```sql
\i migrations/create_file_assets_table.sql
```

or open the app once with a valid `DATABASE_URL` so the additive schema setup can run.

## Security Notes

- R2 secrets must never be logged or committed.
- Buckets stay private.
- Use presigned download URLs for temporary access.
- Supabase remains the source of truth for order, product, edition, and metadata records.
- Limited edition allocation logic must not depend on R2.
