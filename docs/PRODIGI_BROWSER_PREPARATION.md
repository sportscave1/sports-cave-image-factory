# Prodigi artwork preparation

Select one Orders unit. Beside its JPG link, **Send to Prodigi** queues the exact
retained, production-approved numbered JPG. This prepares the existing supplier
draft; payment and production release remain manual in Prodigi.

## Why the browser handles Save

On 21 November 2026, sandbox v5 item artwork PATCH returned success while clearing
the selected SKU. Resending SKU/catalogueVariantId did not preserve it. Live item
PATCH is therefore blocked in the adapter regardless of legacy acceptance flags.
The browser opens the exact existing draft, uploads the JPG, chooses its
orientation and full-image fit, and saves only the image editor. It has no Submit,
payment, login or production-release operation.

## Worker ownership

This is the paired **Edge companion**, not a Docker Orders worker. Edge downloads
the pinned file, checks SHA256 in both the background worker and upload context,
and performs the upload/editor actions. Render retains provider keys, serializes
handoffs, checks the allocation and draft before Save, and performs supplier
readback/QA. No supplier API key, customer address or password goes into a handoff.

Versions 1.7.13–1.7.16 add content scripts only on exact Prodigi order detail pages.
It requests no cookie/network interception permissions and never accesses login
pages. New supplier-site access requires the owner's approval and extension reload.

## Evidence and recovery

- One unique filename and pinned SHA256 identify each handoff.
- A committed single-use permit precedes editor Save. Changed order details,
  existing artwork and ambiguous identical product/frame rows stop for review.
- A worker interruption reads back the same supplier item; it never repeats an
  uncertain Save automatically.
- Supplier render URLs identify their image-library source and placement. QA
  checks orientation, rotation, border, translation and full-image fit.
- Asset detail identifies the source transform; the bounded recent-asset list
  supplies original file metadata. The immutable asset ID joins both. File name,
  original byte count and dimensions must agree with the pinned worker upload.
- When the supplier exposes original bytes, Render additionally checks SHA256.
  Prodigi currently reports some original URLs that return 404. In that case the
  evidence explicitly records worker SHA256 plus supplier asset identity and
  metadata; it never claims an independent supplier-byte checksum.
- Missing production approval, certificate, packing slip or other QA evidence
  remains unresolved. An upload does not manufacture an approval.

The sandbox queue is separate from Shopify and Edition Ops. Its source can be a
retained test export without changing live print eligibility. Removing the test
row revokes the temporary source capability. Sandbox drafts are never submitted.

Live browser claiming additionally requires
`SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED=true` and a request explicitly made through
the new workflow. The old API write flag remains false. Changing the browser flag
cannot activate legacy requests.
