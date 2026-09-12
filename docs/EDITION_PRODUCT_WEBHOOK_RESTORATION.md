# Edition Ops activation repair — local implementation

Date: 12 September 2026. No push, deployment, production webhook, subscription change,
reconciliation, database migration, or production data write was performed.
Read-only Shopify, Render and public storefront inspection was authorized.

## Confirmed findings and remaining delivery question

- Render's existing `sports-cave-os-webhooks` (`srv-d9146onlk1mc739nrm7g`) runs
  `python webhook_server.py` at `https://sports-cave-os-webhooks.onrender.com`.
  Commit `0abe413` was live at 22:50:23 UTC on 11 September, before the batch's
  approximately 23:01 UTC activation. The primary OS service remains
  `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`). No topology files were changed.
- Product routes and registration helpers already exist. Git `362a309` added the
  product webhook work. Registration is an explicit developer action, not a
  Render startup/deployment step. Deploying Python alone does not register topics.
- The inspected Render logs show order processing but no product receipt/processing
  entries during the activation window. This establishes a delivery/observability
  gap, **not proof of a missing subscription**. The connector's empty subscription
  result belongs to its own app; it cannot establish Sports Cave OS's app-owned
  subscriptions. An OS-configured inspection command is still needed to distinguish
  missing subscriptions, wrong callbacks, and Shopify delivery failures. Production
  product HMAC configuration and actual Supabase rows were not directly verified.
- The deployed product processor trusted webhook snapshots rather than refetching
  canonical product data. Its ACTIVE-only gate had no wall-art classifier. The manual
  path also lacked a classifier; the shared gate now derives from the existing
  Product Uploads contract: Sports Cave vendor, Framed Art type, collector tags.
- Git `0c5e81f` deliberately disabled automatic initial metafield mirroring and
  marked new rows Pending configuration. Both manual and webhook paths still passed
  `sync_inserted_metafields=False`. Thus registering a row did not complete the
  Supabase-to-storefront mirror flow.
- Pull New Products scans by creation time and an immutable-ID boundary. It is not
  sufficient recovery for older drafts activated after that boundary. The new
  explicit recovery command scans the full catalogue, without a creation watermark.

## Auston Matthews archived symptom: exact cause

Shopify product `10442291151155`, handle `auston-matthews-wall-art`, is ACTIVE,
published with an Online Store URL, and has no `sports_cave` metafields. Its vendor,
type and tags match the collector contract. All 17 named batch products were found
ACTIVE with that contract; no product identities are hard-coded in the repair.

Read-only inspection of the live main theme (`187940634931`) and the public page
confirmed that `snippets/variant-picker.liquid` sets `sc_missing_edition_meta=true`
when enabled/total are missing, or both remaining/next are missing. That branch
sets **Edition archived / Collector run closed** and disables its purchase button.
The sticky bar uses a different guard and displays Limited Run for the same product.
This is a missing-mirror fallback, not evidence that the product sold out.

The repair does not edit the theme or its labels. A genuinely new registration now
supplies the required fields from committed Supabase state. Historical products are
not reopened: existing closed/disabled rows are not mirrored by this initializer,
and historical mirror evidence without a matching ledger record requires review.

## Canonical flow and data safety

`register_shopify_products_for_edition_ops` in `supabase_backend.py` is used by
Pull New Products, full manual reconciliation, both product webhooks, and the new
missing-product recovery command:

1. Existing raw-body HMAC verification and durable webhook receipt.
2. Refetch current Shopify product by stable ID, including vendor/type/tags,
   publication URL and a dedicated Sports Cave metafield connection. Incomplete
   edition metadata fails closed. Sparse webhook bodies need only a numeric ID.
3. Shared eligibility: ACTIVE, published Sports Cave Framed Art, collector tags;
   exclude internal/private/test/upsell/apparel/certificate/fulfilment tags and
   the configured framed certificate product. Collections are not required, avoiding
   dependence on collection mutation order. Missing publication/classification on
   an otherwise candidate webhook returns a retryable failure. Later retries refetch.
4. Reuse the existing serialized identity/history transaction. Only a genuinely
   missing product is INSERTed at total 100, next 1, sold 0, remaining 100, with
   a new active run. DRAFT does not initialize; later ACTIVE update does.
5. Commit Supabase before attempting its initial Shopify mirror. A dedicated
   Pending automatic mirror marker makes interrupted attempts resumable.
6. Lock/read the current product row before the initial mirror; use its counters,
   never cached defaults. A closed/disabled row is skipped without any mirror write.
   A successful mirror changes only its mirror acknowledgement fields. Failure
   retains the pending marker, logs clearly, and returns HTTP 500 for retry.
7. Edition Ops reads Supabase normally. The prior repair's 180-second refresh on
   normal reruns remains; unsaved edits are preserved. Idle browsers do not receive
   a push refresh. No polling job or extra button was added.

Existing rows match by stable Shopify identity and the existing safe legacy rules.
Counter/limit/enabled/status fields are absent from metadata UPDATE assignments.
The next=1 assignment exists only in guarded INSERT. Before that INSERT, existing
edition orders, runs and allocation tombstones block initialization. Historical or
nondefault mirror evidence can veto initialization but never supplies ledger numbers.
No existing allocations, certificates or audit records are written by this path.

The existing SHARE ROW EXCLUSIVE table lock serializes identity lookup and insertion
across processes, alongside existing database uniqueness and receipt deduplication.
It is released before Shopify calls. The initial mirror separately holds a row lock
through its request to serialize with edits/allocations; slow requests can delay
writes to that one product. Successful duplicate deliveries do not mirror again.
**The repaired registration/webhook paths cannot reset an existing Edition Ops
product to #1: they never assign its edition counter fields.**

## Files changed in this repair

- `shopify_sync.py`: canonical fetch completeness, eligibility and history veto.
- `supabase_backend.py`: shared registration, safe initial mirror, retry diagnostics.
- `webhook_server.py`: sparse-body validation and accurate result status.
- `scripts/register_shopify_product_webhooks.py`: app-scoped callback diagnostics.
- `scripts/reconcile_missing_edition_products.py`: read-only preview / explicit apply.
- `tests/test_product_activation_sync.py`: 19 focused activation/mirror/recovery tests.
- `tests/test_product_webhook_restoration.py`: current-state fixtures and mirror SQL double.
- `tests/test_shopify_sync.py`, `tests/test_edition_ops_new_product_pull.py`: adapt older
  fixtures and replace the superseded pending-until-manual-configuration expectation.
- This report. Edition Ops editing/UI and Render configuration are unchanged.

## Verification

- Backend/product/webhook/edition/Supabase group: **345 run, 311 passed, 34 existing
  retired-allocator skips**.
- Edition Ops table editing in a separate process: **12 passed**.
- Broader Orders/certificate/Render group: **242 run, 239 passed, 3 failures**.
  All three reproduced with unchanged HEAD runtime files: the Mockups prompt-card
  source assertion, order badge cache test (15 versus 1), and old top-bar refresh
  source assertion. Unrelated code was left intact.
- All **9 changed Python files** pass `py_compile`; `git diff --check` passes.
- Canonical Shopify product query passes Shopify schema validation. Existing Render
  topology validator passes. No Blueprint sync or preview was applied.
- Tests use mocks/stateful SQL doubles, not a real PostgreSQL concurrency/load test.
  The entire unrelated repository suite was not run.

## Production follow-up, only after separate approval

Required topics and routes on the same existing webhook service:

- PRODUCTS_CREATE / products/create → `/webhooks/shopify/products-create`
- PRODUCTS_UPDATE / products/update → `/webhooks/shopify/products-update`
- ORDERS_PAID / orders/paid remains unchanged.

No publication topic, duplicate app or startup registration is added. Shopify stores
subscriptions independently of Render deployments. Their actual OS-app presence is
still unverified. In the existing OS-configured Render shell, inspect without writes:

```sh
SPORTS_CAVE_WEBHOOK_BASE_URL=https://sports-cave-os-webhooks.onrender.com python scripts/register_shopify_product_webhooks.py
```

Only if inspection shows missing topics and Nathan separately approves registration,
repeat with `--apply`. The script creates missing matching subscriptions; it never
deletes/replaces others. Use existing OS credentials, never paste credentials here.

Plan on one safe reconciliation after deployment for missed activations; the preview
identifies exactly which of the 17 (and any other eligible products) are missing.
It does not assume every named product is absent from Supabase. In the existing
OS-configured environment:

```sh
python scripts/reconcile_missing_edition_products.py
```

Review `would_create`, `would_resume_initial_mirror`, `skipped`, and `review_required`.
The preview uses a READ ONLY database transaction. After separate approval:

```sh
python scripts/reconcile_missing_edition_products.py --apply
```

Apply refetches and rechecks identity/history under the lock, creates only missing
rows, and resumes only unfinished initial mirrors from this repair. Existing edition
records are otherwise untouched, including their metadata. It never bulk mirrors the
existing catalogue. Pull New Products remains a safe fallback but is not guaranteed
to discover old drafts behind its creation watermark.

SAFE FOR NATHAN TO TEST LOCALLY: YES — using fixture-based tests. This does not claim
production delivery is fixed or authorize a production reconciliation.
