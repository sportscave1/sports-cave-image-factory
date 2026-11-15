# Product Uploads local Edition Ops lookup repair

## Confirmed cause

Comparison of 14e3a4f2 with its parent confirms the previous change removed the onboarding sync step but did not change `_identity`. Both revisions still used Shopify catalogue/tag lookup and fresh product reads before consulting Edition Ops. The screenshot message is raised when the remote search returns no exact current-operation tag match, not when the local Edition Ops row is missing. Earlier mapping revision 90fd2351 also used this remote lookup. A repeat upload can have a different operation tag even though its PSD already has an authoritative product relationship. Fresh status/online-store checks could additionally reject a valid local identity.

The exact production record was not queried; no claim is made that its specific tags, status or mapping were inspected. The confirmed defect is the remote lookup dependency and failure to resolve the existing local file relationship.

## Narrow repair

- `_identity` now resolves existing Edition Ops records by saved Shopify ID, authoritative PSD file-ID relationship, or exact operation tag in locally ingested edition/product data. IDs are canonicalised; conflicting identities and ambiguous candidates require resolution. No title-only matching.
- No Shopify catalogue/search/product call or syncing occurs during mapping. Shared sync/webhooks and numbering code are unchanged.
- Missing records show `Waiting for product in Edition Ops` and explicit lookup retry. Existing consistent active edition/run state remains required; mapping never creates that state or assigns numbers.
- Existing move/rename/link finalisation and lost-response/retry protection are unchanged. Already complete operations return their verified state; another operation for an already linked PSD reuses its stable relationship.
- Two mapping UI labels now identify Edition Ops as the lookup source. Sync remains absent.

## Implementation scope

Category entry checkout verified clean: C:/Dev/SportsCaveWorktrees/sports-cave-products on codex/category/products.
Task worktree verified clean before edits: C:/Dev/SportsCaveWorktrees/sports-cave-products-local-edition-ops-mapping-lookup-repair-20261020-754d6744.
Branch: codex/task/products-local-edition-ops-mapping-lookup-repair-20261020-754d6744.
Baseline: 14e3a4f2063a5b8824059c2037763c8ce1c01255. Owner: codex-local-map-20261020.

Only mapping handler/UI, their focused tests and this report are edited. Other worktrees and changes are preserved. Initial implementation and validation were local only. The user subsequently authorised committing, pushing and deploying this patch to the existing canonical Render service. Production records and artwork are not changed for testing.

## Verification

The focused suite uses disposable local PGlite PostgreSQL with mocked Dropbox writes and Shopify methods that raise if called. Coverage includes newly ingested rows, absent rows then retry, explicit stable IDs without tags/cache, exact cached array/comma-separated tags, conflicting/ambiguous identities, same-title rejection, existing PSD relationship on a new operation, completed mapping retry, unchanged numbering, and existing movement/link failure recovery. JavaScript lifecycle tests cover waiting/retry and the two-step UI. Final local result: 48 mapping tests passed, JavaScript mapping UI tests passed, Studio verification and git diff checks passed.
