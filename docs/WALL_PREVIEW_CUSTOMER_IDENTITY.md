# Wall Preview customer identity (Issue #5)

The existing binary JPEG/PNG POST `/api/wall-previews` now requires
`customer_email`, `customer_name` and `identity_source` (`guest` or `logged_in`)
alongside the existing product/permission query parameters. A claimed
`shopify_customer_id` is ignored. This endpoint archives previews, never creates
customers or subscribes them to marketing. Its public response does not disclose
whether an email matches Shopify or its consent state.

Email is trimmed/lowercased, independently exact-matched against the existing
fresh Shopify customer search (bounded to three pages). Exactly one match supplies
the canonical ID/email/name and read-only consent snapshot. No match, ambiguity,
incomplete pagination or provider failure keeps the entered guest identity with
`UNKNOWN` marketing state. Social permission remains independent and controls
approval/use. Campaign consent/suppression checks are unchanged.

New files live directly in:
`/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox/<normalized-email>/`.
Path-unsafe characters are percent-encoded (including literal percent signs to
avoid collisions). Filenames contain a safe product handle, microsecond UTC
timestamp and 16-character image hash. No new year/month folders are created.
The submitted archive bytes are stored without adding any branding. Same-email
retries reuse the original archive/identity/consent; different emails have separate
records even when image bytes match. Existing records/files are not relocated and
no customer identity is invented for legacy uploads.

`20261004_wall_preview_customer_identity.sql` adds six bounded identity columns,
customer-scoped uniqueness and two prefix-search indexes. The SHA-reviewed startup
manifest applies it after the base migration, before the listener starts, then
verifies the committed schema. RLS and server-only grants remain enforced. The
legacy Render pre-deploy command alone is insufficient; the existing main server
startup is the canonical reviewed deployment path.

Inbox search is a literal, case-insensitive name/email prefix (wildcards escaped),
bounded to 48 displayed rows. Current Shopify marketing state uses one existing
45-second cached batch read for visible matches. If unavailable, the snapshot is
clearly labelled "at save". Only admins get the configured Shopify customer link.
Non-admin staff still cannot view private previews. Uvicorn access logs for this
route are suppressed because the established query contract contains identity;
safe record-ID/type logs remain, with no email/name/customer payload logging.

The Shopify widget is maintained separately. Public source inspected on
2026-10-04 at the Cristiano Ronaldo product page confirms this order:

1. `buildCompositeCanvas(true)` -> JPEG -> local `downloadBlob(savedBlob)`.
2. `buildCompositeCanvas(false)` -> clean JPEG -> `archivePreview(archiveBlob, identity)`.
3. Archive exceptions preserve "Saved to your device".

No widget, calibration, size/frame selection, camera, cart or artwork-rendering
code was changed here. Static verification confirms the clean/watermarked and
independent-download contract; it does not replace an interactive visual save
test on a physical device.
