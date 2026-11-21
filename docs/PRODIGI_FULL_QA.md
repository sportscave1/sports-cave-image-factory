# Live Orders preparation

Orders keeps the existing certificate, PSD, JPG and Fulfilment actions. The
compact table groups the customer with the order and the variant with the
artwork. Dates and shipping remain visible. It displays 50 edition units per
page, preserves stable selection identities across pages, and filters locally
by saved status. The table makes one batched status read, with no supplier call
per row. Only active, visible preparation polls for status.

Send attaches artwork to the exact existing unpaid Prodigi draft without a native-resolution quality review. The current source, allocation and supplier target still have to match. Print-quality checks run in the later QA stage after upload. Auto Editions generates
the allocated numbered JPG when required. The paired Edge companion uploads
and saves it; Render validates the supplier identity, artwork, dimensions,
frame, shipping, edition, certificate and packing slip. The certificate uses
the existing template on an A4 landscape sheet and is attached by Companion
1.7.20 using a checksum-bound, single-use permit. Live API item PATCH remains
blocked. This uses Edge plus Render processing, not a Docker Orders worker.

Payment and Submit always remain manual. Green Ready opens the exact supplier
order only after every QA check passes. It does not mean the order is paid or
in production. Supplier files marked NotYetDownloaded are attached for manual
release; raw supplier byte verification is reported separately when available.

The original layout and archived bytes must match their saved approvals.
Enlarging an export does not prove more native detail. Native resolution and
embedded colour-profile failures block the later QA production approval, not Send. #SC3522 still requires a
higher-resolution master to pass that QA; no owner quality exception has been recorded. Exact
recipient/address matching stays mandatory and neither address is silently
rewritten to resolve a mismatch.

Failures retain their stage, timestamp, error type and message on the preparation
record, with history events and a review prompt. A staff recheck can renew a
certificate handoff only if its permit was never used, the original source and
supplier business fields are unchanged, and no packing slip exists. Used or
uncertain upload permits are never reset. Existing different artwork/slips and
multiple numbered items stop for review rather than being replaced.

Only the live Orders queue is processed in normal operation. Test controls have
been removed from Orders; previous test rows were stopped and hidden. The
legacy test adapter defaults off and cannot claim work unless explicitly enabled
for isolated offline tests. Interrupted test receipts are acknowledged without
accessing Prodigi so they cannot block the live desktop worker.

Live preparation uses the existing SPORTS_CAVE_PRODIGI_PREPARE,
SPORTS_CAVE_PRODIGI_BROWSER_ACCEPTED and SPORTS_CAVE_PRODIGI_FULL_QA_ACCEPTED
flags. Credentials stay on Render and existing browser sign-in settings are
unchanged. Live checks must retain the actual failed result; a real test is not
permission to pay, Submit, waive quality evidence or create a replacement order.
