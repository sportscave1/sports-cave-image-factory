# Companion 1.7.33 — same-address consolidation

## Admission and preservation

The worker groups separately purchased orders only with the same independently
saved Shopify customer ID, complete delivery recipient/address (including unit,
state/province, postcode, country and company), and Standard/Express intent.
Names and email addresses alone never qualify. Missing or ambiguous identities
stay separate. Every item needs its own allocated edition and verified JPG.
The oldest eligible supplier creation timestamp wins; timestamps are compared
in UTC. Paid orders, production history, shipments, supplier issues and pending
submission/readback leases exclude a candidate. Maximum combined size is the
supplier's 100-item limit.

The paired worker must advertise consolidation support, and owner-authorised
submission must be enabled. Older clients cannot start the new flow. Admission
coordinates with the existing submission fence and rechecks locked records
before recording a merge, so ordinary submission/status reads cannot overwrite
an active merge or race past its admission decision.

Original Shopify orders, line items, allocation IDs, numbered JPGs and customer
certificate destinations are retained. A per-item supplier binding records the
new root/item ID without changing the independently resolved original snapshot.
The interface groups shared supplier roots, retaining each original order label.

## Workflow

1. For a draft duplicate, keep it unsubmitted throughout copying. For an already
   paused duplicate, the owner explicitly approved **Pause indefinitely on the
   duplicate only** on 2026-11-22. A source-scoped server permit precedes that
   action; live UI readback and independent unpaid API readback must confirm it.
   The retained countdown and global Prodigi settings are never changed. No
   duration is parsed or compared; no automated Resume or Send now is added.
2. Commit an Add intent, select the exact existing Fulfilment SKU/frame through
   Add another item, then independently identify precisely one new blank item.
   Existing products/artwork/address must remain unchanged. An uncertain Add is
   only read back; it is not clicked again. Late API visibility has a bounded
   reconciliation window.
3. Upload the immutable original numbered JPG using the existing verified
   browser path. Live artwork PATCH remains blocked. Every Save rechecks the
   original source, destination, customer/address and unpaid state.
4. Run one combined QA batch across all items, including product/frame/size,
   artwork/edition/full fit, Excellent quality, customer address, cheapest
   Standard or required Express shipping, tax and observed inserts. Any failed
   item stops consolidation without cancelling its source.
5. Persist one cancellation intent, cancel only the redundant unpaid supplier
   order, and read back cancellation. A lost acknowledgement never causes a
   second cancellation POST. Until cancellation is confirmed the duplicate is
   still an unsubmitted draft or is held indefinitely, preventing duplicate
   automatic production. The OS keeps a warning and reconciles the same order.
6. After confirmation, bind each original edition to the combined supplier root.
   Already-paused targets remain Submitted with no repeat submit. Draft targets
   proceed through the existing one-order submission fence. Actual production
   still triggers a separate certificate for every original allocation/account.

Further purchases can join that same oldest eligible root. Target/source fences
serialize each merge. Active or uncertain operations stop for review; Retry merge
reruns QA for verified copies without recopying or repeating cancellation.

## Performance and evidence

Only worker-created exact-order tabs are reused across upload and QA. Navigated
or closed tabs are never reclaimed. Duplicate hold controls refresh only a
worker-owned tab with no open editor. The visible Orders table patches changed
rows; filter/regroup changes rebuild the table while retaining selection/scroll.
Stage durations are stored as bounded backend metadata, not extra UI controls.

Orders pairing authentication is a read-only credential/permission check, with
its own paced heartbeat. It does not wait on the shared Design desktop row lock.
No supplier API key or customer address is added to extension storage.

Offline synthetic tests cover two- and three-order sequences, address/customer
mismatches, paid/history rejection, original certificate identities, source-only
holds, exact Add permissions, post-add combined QA, readback leases and uncertain
cancellation. A genuine eligible live repeat-customer pair is still needed for
the first end-to-end native acceptance; unrelated live orders are never used as
temporary test items or cancelled to manufacture that case.

References: https://www.prodigi.com/print-api/docs/ and
https://www.prodigi.com/faq/ordering/ . The API adds items to drafts; additions
inside a paused edit window use the native dashboard.
