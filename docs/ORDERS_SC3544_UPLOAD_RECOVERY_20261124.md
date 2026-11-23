# SC3544 upload wait and companion recovery

Task 20261123-532903e4; owner codex-order3544-20261124. The owner explicitly
requested diagnosis, stronger automatic recovery and a live release on 24 November.
The task preserves the currently deployed fca015fc revision and other worktrees.

## Evidence and cause

Allocation 979 stopped at artwork.uploaded after approximately 648 seconds.
The retained JPG was 37,117,093 bytes at 11340 x 8016 pixels. The durable Save
permit remained unissued (started=false), no submission existed, and supplier
business readback reported no changed fields. This was a pre-Save UI wait,
not a failed edition allocation or an uncertain paid submission.

Read-only supplier inspection and an unsaved editor inspection found the exact
original handoff filename in the image library. Selecting that entry opened the
correct-dimension editor with an Excellent rating. The editor was cancelled
without saving. The library briefly rendered Invalid JWT token / HTTP 401 and
then recovered. The original failure stored only a generic control timeout, so
that later authentication error cannot be asserted as the original trigger.

The companion waited only for the picker to close automatically after a file
upload. It had no exact-file selection fallback when the uploaded original
remained in the library. Its existing processing-timeout recovery additionally
required a verified product-selection or Reset receipt. SC3544 already had a
configured product and neither receipt, so polling permanently skipped it.

## Recovery and preservation

Companion 1.7.54 selects only one matching handoff filename with matching
dimensions. Recovered uploads also pin the supplier asset ID visible in its
thumbnail path. Persistent library authentication errors receive a precise
failure after a short grace period; temporary errors can settle without replay.

The new capability permits server recovery for any unchanged empty target,
including already configured products. Fresh allocation/JPG, recipient, variant,
quantity, assets and whole-order business checks precede retirement of the unused
token. A used Save, submitted order or changed source never enters this path.
Retirement and the replacement proof commit atomically.

When available, the original library asset must match its unique name, byte count,
MIME type, dimensions and downloaded SHA256 before reuse. The identity is checked
again at claim and immediately before Save. A missing/unreadable original uses
the retained numbered JPG through the existing upload path. Conflicting metadata
or ambiguous assets stay stopped. No replacement order, allocation or JPG design
is created. Every Save retains its single-use permit and independent readback.

Known pre-permit download, transfer, readiness, sign-in and unavailable-permit
errors use the same unchanged-empty-item proof. A lost permit response whose
permit was actually committed cannot qualify, because started=true stays fenced.
Repeated pre-permit transient waits back off from one minute to fifteen minutes,
without exhausting into an abandoned job. Unavailable/changed recovery candidates
yield to other orders. Changed business state still requires review. Supplier
sign-in must remain valid; automation cannot guarantee external availability.

Completion evidence is now durable in desktop storage until OS acknowledgement.
A lost finish response replays the same readback receipt and QA evidence, never
the upload or Save. New handoffs require the explicit new companion capability;
an older desktop cannot claim the recovery authority.

## Verification and release

Synthetic disposable-database tests cover ordinary configured items without
Reset, token revocation, original-file reuse, missing originals, cooldowns,
metadata/hash/identity changes, source/address/quantity/shipping changes,
consumed permits and submission fences. Browser tests cover completed files left
in the picker, delayed rendering, ambiguous/wrong assets, persistent JWT errors,
the complete reused-file page flow and lost QA completion acknowledgement.

Run scripts/check_orders_release.py with disposable PGlite for the full Orders,
Inbox, QA, submission, notification, package and topology gate. Actual release
and live order receipts are recorded separately in Studio evidence. No schema,
Render topology, supplier account preference or customer automation changes.
