# Auto Editions V7 — scoped SC3287 continuation

## Read-only Prodigi safety audit (14 October 2026)

Compared V4 8e285a5b through current 9ea32613, including the V4 Photoshop
entry points and V6 cloud/setup/store/queue paths. No supplier HTTP client,
Prodigi API credentials, order submission, product/SKU mutation or Shopify
fulfilment mutation is introduced by Auto Editions. Shopify integration,
webhook and render.yaml files are unchanged in this comparison. Existing
Prodigi UI/reference/manual-dispatch code is not part of the generation path.
The existing web service starts one internal edition worker; its persistent
writes are limited to generated Dropbox assets and the five V6 tables.
Render service start commands remain the existing OS, webhooks and SEO worker.
No new supplier service or configuration was introduced. No live Prodigi
orders were accessed, and no supplier configuration was changed.

No evidence connects SRFE-GLOBAL-CFP-A1-503, SRFE-GLOBAL-FAP-A3-503 or
SRFE-GLOBAL-FAP-A4-503 to these changes. Their actual cause remains unknown;
no speculative Shopify–Prodigi repair or integration removal was performed.

## Resolution preparation

Actual SC3287 staged source header, prepared PNG and downloaded JPG all report
2835 × 2004 pixels. V6 did not downscale or use a thumbnail; it intentionally
prepared native pixels. V7 adds explicit native/2×/3× TEST preparation to the
existing setup. Photoshop resizes only its disposable layered copy using
Bicubic Smoother; editable text/shapes remain layered during rendering.
Original PSDs and the registered reference are never saved or changed.

SC3287 provisional 3× geometry is 8505 × 6012, preserving source aspect ratio.
This is not a Prodigi size or a claim of recovered photographic detail.
The master excludes only the selected editable edition text. Small opaque
number patches retain Photoshop typography and the actual individual plaque
position. One master plus small patches is persisted, not 100 full JPGs.
Independent enlarged Photoshop reference composites and the enlarged original
prove no compositor changes outside the number. Administrators must review
enlargement quality before TEST approval. No PRINT READY transition exists.

The cloud compositor never resizes its approved master. A 60 MP bound and
shared render/reference lock limit concurrent memory use on the existing
standard Render instance. Native V6 packages and approvals remain compatible.
Existing source mappings, allocations, certificates and manual fulfilment
remain untouched. New assets have new content identities; old masters remain
available for rollback until the exact variant receives explicit approval.

## Acceptance evidence

SC3287 source revision remains 0165dc199b9adba000000036d367e13 and Dropbox
content hash 6019ee6383d53139f48c97aa3b0720dd7a0055597d9eb84fd1bf82eda68c8ce9.
Mapping count 284; aggregate before/after digest e8a0ae48a536af625295544fa06fc920.
Allocation 659 remains #005/100; SC3284 allocation 655 remains #002/100.
The user explicitly approved the enlarged image for TEST use on 14 October.

Prepared master 8505 × 6012; lossless PNG 24,567,934 bytes; all 100 small
patches together 5,460,659 bytes. Photoshop references #1, #5 and #100 match
the compositor pixel-for-pixel; original enlarged composition outside the
number region is exact. Faces, sponsor logos, lettering, plaque and borders
were visually inspected at detailed crops. Raster detail remains source-limited.
The original PSD and staged input hashes were verified unchanged.

Actual Render Linux validation generated #005/100 in 1.57 seconds with peak
reference-validation RSS 699,560 KiB. JPG 22,619,646 bytes, 8505 × 6012,
SHA256 0054abec3932fcde3c927a772c679c8f283a13943b99c4a3c73ec14c341e0814,
identical to local export. Live activation/download is recorded separately in
the task acceptance artifact after deployment. No physical PC shutdown is
needed by the renderer; Photoshop is solely a one-time preparation dependency.
