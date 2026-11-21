# One-click Prodigi draft preparation

Orders has a compact Send/status column immediately after Edition JPG. Text
wraps instead of being clipped. Twenty rows per page, a bounded internal scroll
and collapsed unit details keep the page short. Selection and actions carry
stable allocation identities, never just a displayed row position.

Send queues one existing supplier draft. If required, the normal Auto Editions
worker first generates the allocated numbered JPG. The paired Edge companion
uploads and saves the artwork; Render performs the API checks and document
work. This does not add a Docker Orders worker. Payment and Submit stay manual.

## QA and documents

After the single-use Save permit and artwork readback, one background pass:

- Revalidates the current layout/source, independent pixel proofs, edition,
  archived bytes, RGB JPEG encoding, ICC profile, native resolution and supplier
  catalogue/asset validation.
- Generates the existing Sports Cave certificate template for this exact unit
  and archives its PDF by immutable hash/revision. In this workflow the custom
  packing slip **is the numbered certificate**, matching the existing Fulfilment
  convention. The original layout is fitted to one A4 landscape sheet with safe
  margins. It does not claim that a draft's fee has already been paid.
- Uses Companion 1.7.19 to upload the checksum-pinned certificate PDF through
  Add packing slip on the exact unpaid draft. The sandbox API document PATCH
  returned HTTP 500 on 21 November; the automatic flow does not use that write.
  A durable single-use permit precedes the browser upload. An uncertain result
  is re-read, never uploaded again. Existing different slips are preserved.
- Rechecks all business fields, artwork, certificate and supplier slip status.
  Green Ready appears only when every check passes. The link opens the exact
  supplier order for manual review/payment/submission.

Existing different packing slips and orders with multiple numbered items stop
for document review. No certificate is silently replaced. Sandbox does not
publish certificates to Shopify or alter live allocations/orders.
The optional synthetic-recipient sandbox mode tests transport and QA machinery
without reading or copying a live supplier recipient. It is labelled in Orders
and never approves the real customer's address. Normal customer-copy tests keep
their exact address-match guard; a street mismatch still blocks them.

## Honest print approval

The draft print certificate records automated technical evidence. It does not
forge `human_visual_approved` or rewrite Auto Editions' historical TEST flags.
The original layout/pixel approvals must already exist. An enlarged pixel count
does not prove more native detail. Native resolution below the supplier's
recommendation remains a warning that blocks Ready.

A higher-resolution original master is required when native resolution fails.
This workflow has no automatic resolution exception. The owner specifically
required a higher-resolution master for #SC3522; neither a larger export nor a
manually ticked answer can make that artwork Ready.

## Bounds and activation

The table does one batched local status read; it never calls Prodigi per row.
Only visible active work polls (ten seconds). Expensive file validation is
cached as immutable job/checksum evidence; pending slips only need readback.
Certificates use expiring opaque URLs bound to the active preparation and
current allocation. Hiding a sandbox row revokes its JPG and PDF capabilities.
The supplier attachment is bound to its unique library asset ID, filename,
PDF byte count and companion-verified source checksum. If Prodigi's original
download returns 404, raw supplier byte verification is explicitly false.
`NotYetDownloaded` means attached for manual release, not already printed or
downloaded; the UI records that distinction. Errors never pass packing-slip QA.

Full QA is enabled for sandbox by default; `SPORTS_CAVE_PRODIGI_FULL_QA_ENABLED`
can disable it. Live draft preparation additionally requires the explicit
`SPORTS_CAVE_PRODIGI_FULL_QA_ACCEPTED=true` acceptance gate. The existing browser
gate also applies. Live **item artwork PATCH remains hard-blocked**. Supplier
keys stay on Render; no login, credential, cookie or authentication settings
are changed.
