# Automatic Shopify edition onboarding

Implemented in task 20261019-de02ab2d, based on released main ad218aff. The EDITIONS category worktree was inspected and left unchanged; all work is isolated in its Studio task worktree.

## Diagnosis and behavior

Both product topics already reached the webhook service. New products carrying an sc-upload correlation tag were skipped pending manual MAP, even with an explicit edition limit. Requests also processed synchronously. The existing registration/allocator is retained: verified new products may pass the MAP hold, with the confirmed total supplied to the existing transactional initializer. Existing identities, runs, allocations, cursor overrides, historical mirrors and tombstones are never reinitialized.

The HTTP handler validates raw-body HMAC and the configured shop, commits an existing webhook_events receipt, then acknowledges. The existing always-on worker consumes receipts under a durable expiring database lease (short transactions, safe with transaction poolers), fetches current Shopify data, and retries pending/failed work with exponential backoff (30 seconds to one hour). Ineligible or incomplete products remain pending. Shopify order-history failures fail closed; products older than 59 days require read_all_orders. Order line pagination requiring manual reconciliation remains pending. No inventory-derived counters, new allocator, customer sale, or certificate is created.

Every five minutes the worker scans a bounded updated_at window (50/page, four pages/cycle), resumes pagination, overlaps ten minutes, and advances the checkpoint only after successful processing or durable metadata deferral. The initial window is 24 hours. This intentionally is not a historical catalog backfill. Existing initial mirror logic writes only pending edition mirrors. Subscription inspection is read-only at startup; scripts/register_shopify_product_webhooks.py remains the explicit configuration tool. No live subscription change is included.

After persistence a revision marker invalidates the existing Edition Ops snapshot on the next 15-second fragment refresh, preserving unsaved edits. Onboarding does not depend on the Windows companion or browser.

## Verified target

Peter Brock — King of the Mountain, Shopify gid://shopify/Product/15428753948979, created 2026-10-19T09:28:59Z. Handle: peter-brock-king-of-the-mountain-wall-art. Artwork: peter-brock-king-of-the-mountain-black-framed-v8-supercars-wall-art.webp. Sixteen size/frame variants, explicit sc-edition-limit-100. This is separate from the older Peter Brock Tribute design. Read-only live checks found no matching Edition Ops product/run/order/tombstone and no Shopify order for this product in the complete post-creation window. The onboarding service repeats those checks before initializing.

## Local validation

44 isolated SQL tests passed across onboarding and upload mapping, using the existing PGlite PostgreSQL fixture and actual edition allocator migrations. Covered targeted Brock registration (one product/run, next 1/sold 0/remaining 100), no certificate/sale, duplicate and stale events, metadata completion, API retry, missed-event checkpoint recovery, pagination/overlap, historical refusal, existing cursor preservation, and duplicate first-order allocation. Concurrent test threads use the fixture's serialized database transport; this is not a multi-connection production PostgreSQL load test.

227 focused unit/UI tests passed (34 pre-existing database-dependent skips). Updated older mocks for the queued webhook contract and current read-connection pool. UI tests check that onboarding refresh preserves unsaved edits. Render topology validation passed. No real orders were created.

## Release verification

Initial commit 69d7210e reached all three existing Render services. Live startup confirmed both product subscriptions already point to the correct product-create/product-update webhook URLs; no change was needed. Production verification exposed session-lock incompatibility with the database pooler, corrected with a renewable ten-minute durable lease. Added SQL regression coverage for competing consumers and expired-lease recovery. Classification review warnings remain pending without blocking the incremental scan. Exact-target receipt edition-targeted-brock-15428753948979-20261020 was durably enqueued; no counters were directly edited. Live result verification follows the corrected release. Other 337 product counter tuples remained unchanged (digest 0740d67bc9dc09d4763a91eaf931b24c). Windows companion process was present, but native UI automation could not obtain a foreground process ID; no successful Edition Ops desktop interaction is claimed.


### Brock live reconciliation blocker

The exact-target live import correctly rolled back when the existing shopify_products unique handle was found on a different stable identity: gid://shopify/Product/15428059398451, created 2026-10-19T03:39:28Z, with the same title/artwork/handle. Shopify now returns null for that earlier product. No local edition product/run/order/tombstone exists for either identity or the handle. The cached prior identity is preserved; the new service explicitly retains this as pending identity/history reconciliation instead of repeatedly attempting an insert or changing another product. The verified new identity remains gid://shopify/Product/15428753948979 (created 09:28:59Z). No live #001 claim, forced counter update, sale or certificate is made. Reconciliation of the earlier cached identity is outside the narrowly authorized new-product sync.
