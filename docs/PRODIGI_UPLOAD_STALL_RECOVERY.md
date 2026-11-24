# Original upload stall and automatic recovery — 1.7.57 follow-up

This follow-up is separate from the released 1.7.56 missing-page recovery fix.

## Evidence and limits

The first SC3551 receipt stopped at `uploaded`, waiting for the picker to return
an image to the editor. Its Save permit was unused and the supplier item was
still empty. Read-only inspection subsequently found the original receipt's
exact filename in Prodigi's image library: `SC-986-…-f2034cc5`, asset
`afc77beb-641d-4597-b6d5-8bd6ee956668`, with the expected 11340 × 8016 pixels.
The numbered source was 45,245,405 bytes. Thus the original file reached the
library; its attachment/confirmation in the order editor did not complete.

No original request trace or selection acknowledgement was retained. The
evidence cannot establish whether the supplier was still busy, ignored a
selection click, or completed after the browser wait had expired. It does not
justify claiming a particular HTTP, authentication, bandwidth or memory error.

The Companion had a reproducible defect at this boundary: it selected a
matching tile once, immediately marked it selected, and never retried if the
supplier ignored that click. It could click while the picker still displayed
“Uploading…”. Busy and ignored-click fixtures reproduce the same generic
ten-minute timeout in the released code. A later failed page-opening attempt
also replaced the filename used by recovery, so the original completed upload
was overlooked and another 45 MB upload was issued.

## Change

The picker waits for its upload control to settle before selecting the exact
filename/dimensions. It allows at most three selections of that same image,
spaced five seconds apart, rechecking order identity each time. It never sends
another file or clicks Save from this loop. A completed tile with a busy flag
lasting sixty seconds, or three ignored selections followed by thirty seconds
without confirmation, produces a specific recoverable cause. The original
ten-minute allowance remains for an upload whose file is still transferring.
Dimension, asset-identity, ambiguity and order-identity failures remain fatal.

Server recovery recognises those causes and retains completed uploads across
page-only failures. It searches one asset listing using at most the current
receipt, the previous recovery and eight retained history entries. Candidates
must belong to the same allocation/job filename namespace and an unused
pre-Save receipt. Recorded source hashes must match. Legacy history entries
also require full original-byte SHA-256, byte-count, dimensions, media-type and
unique asset-ID verification before reuse. Claim and Save permission recheck
that asset independently. Existing changed-order, used-permit and submitted-
order fences remain in place.

The new error messages distinguish upload timeout, a stuck picker busy flag,
missing library evidence and ignored selection. This preserves the cause in the
existing durable browser receipt rather than collapsing every stall into
“control did not finish loading”. Future transient stalls can recover through
the existing same-item workflow without a manual Reset.

## Verification

`tests/test_prodigi_upload_stall.cjs` covers busy/ignored selections, bounded
retries, timeout causes, dimensions and order identity. The existing upload
suite still checks one file/Save and normal automatic selection.
`tests/test_prodigi_upload_recovery.py` adds delayed original completion across
a page-only failure, legacy history, one listing per recovery, retired tokens,
used permits, source/allocation/job boundaries and full metadata/checksum
rejection. All database fixtures use disposable PGlite and synthetic orders.

No real order is changed to reproduce a failure. Release and installed-client
activation require the current repository's explicit release authorization.
