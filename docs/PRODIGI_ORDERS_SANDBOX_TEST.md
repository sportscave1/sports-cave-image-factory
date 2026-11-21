# Orders action and isolated sandbox acceptance

Task 20261121-d2531542, owner codex-prodigi-orders-sandbox-20261121.
The user requested a visible Orders action and a removable sandbox test with
customer details. Saving the separate sandbox API key on the existing primary
Render service was explicitly approved. No new Render service or Blueprint
change is required.

Orders now always shows the administrator's Prepare for Prodigi toolbar action
when preparation is enabled. It is disabled until exactly one numbered unit is
selected, then opens the existing guarded preparation panel. It does not start
an upload on selection or change Download JPG.

The separate Prodigi sandbox test section creates an app_settings test row from
one selected unit. It reads that unit's existing supplier order, verifies the
customer address, product, frame and quantity, and copies its customer details
into a separately labelled SC-SANDBOX draft. The numbered JPG stays bound to the
original retained production archive; no new edition is allocated. A separate
test identity is used for the sandbox order/item. No Shopify or Edition Ops
records are inserted, changed or deleted.

The paired Orders worker processes these records only after the normal queue
has no pending job. It uses PRODIGI_SANDBOX_API_KEY exclusively. Sandbox mode
never falls back to PRODIGI_API_KEY, rejects live-prefixed credentials and
rejects the configured live key even if its prefix is changed. Draft creation
hardcodes submit=false and has no payment, submit, resume or release operation.

Create intent and artwork intent commit before supplier writes. Draft creation
uses a stable idempotency key. An uncertain create is reconciled by the same
unique reference; it never creates another draft automatically. Artwork uses
the existing same-item write fence and readback checks. A changed allocation,
ambiguous item, non-draft order or charge stops processing. Missing certificate,
packing-slip or other QA evidence remains Needs QA; successful attachment is
not presented as a fully verified print order.

Remove sandbox row from app is available after processing stops. It hides only
the explicitly labelled sandbox test record, preserving a server-only audit.
It does not delete the supplier draft or alter the source order. Sandbox drafts
remain unpaid and cannot enter production through this implementation.

The historical Requires attention order inspected on 21 November 2026 had no
selected product and Submit was disabled. It was inspected read-only. It is not
a complete artwork-upload fixture; an existing completed unit with a retained
numbered JPG provides the positive sandbox source instead. No historical order
was completed, cancelled, paid or submitted as part of diagnosis.

Live acceptance found that the retained Captains export is marked test_only,
without a production approval. Sandbox can use this exact retained export for
attachment testing, without changing its classification. Its one-file link is
valid for at most 24 hours, requires the matching active sandbox row on every
fetch and is revoked by removing the test row. Live preparation still requires
a production-approved export, and QA never marks test-only pixels print-ready.

Offline tests use synthetic names/addresses and disposable PGlite. They cover
the real toolbar dialog, customer/test-row display and removal, separate keys,
forbidden production actions, unchanged source identity, uncertain responses,
durable intent, duplicate requests and preservation of live preparation rows.
