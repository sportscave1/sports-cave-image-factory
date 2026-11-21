# Live Orders / Prodigi QA

Send attaches the exact archived numbered JPG to the existing unpaid Prodigi
order using the paired Edge companion. It never creates a replacement order,
pays or submits to production. Saved artwork and full-image fit are verified
against the pinned supplier asset and edition. Completed orders remain complete.

Companion 1.7.22 then runs one dashboard QA pass. It checks the exact mapped
SKU, size and frame; the saved design and allocated edition proofs; Prodigi's
visible **Excellent** image-quality rating; and the full structured customer
shipping address against the authoritative Shopify order. Excellent is the
owner-requested quality criterion; it is not a claim of 300 native PPI.

No certificate PDF is uploaded to Prodigi. The companion opens Inserts > View &
edit, reads the saved insert assets, previews SC EDITION BRANDING without saving,
and compares its exact round packaging sticker and colour packing-slip assets.
It cancels that preview and reopens the order's saved inserts to verify they did
not change. A selected dropdown or unsaved preview alone cannot pass. Missing,
different or unavailable inserts remain a failed check. The worker never assigns
paid inserts or silently replaces them. Local certificate features remain intact.

For Standard shipping the worker selects the lowest current quoted shipping
price. An already-cheapest tied option is retained. Express orders require
Express. Mixed currencies, missing prices and ambiguous services stop for review.
A single-use server permit pins the exact draft before any shipping change; API
readback must confirm it, and all other artwork/product/address/inserts fields
must remain unchanged. An interrupted shipping change is reconciled before a
new pass. There is no automatic re-upload of artwork or certificate.

Only all passing checks produce **Ready in Prodigi**, beside an **Open** link to
the exact draft. Payment and Submit are always manual. Unknown evidence fails;
no check is manufactured from a missing status. Failed attempts retain their
stage and time. Existing saved artwork can be rechecked with Check all QA again;
the obsolete certificate-upload failure does not trigger another document job.

The Orders table shows 50 edition units per page, preserves selection/page/scroll,
uses batched local statuses and polls only active visible work. The browser QA
hands back compact DOM evidence; supplier credentials remain on Render. This is
Edge plus Render processing, not a Docker-only Orders worker. No login, cookie,
credential or payment settings change. Legacy certificate uploading is disabled
for live orders unless separately enabled for isolated compatibility tests.
