# Shopify → Edition Ops sync and Mapping repair — 21 October 2026

Task `20261021-a8315c3f`, owner `codex-sync-repair-20261021`.
The user explicitly authorized pushing to Git/Render. Original Windows worktree
`C:/Users/hello/Documents/sports-cave-image-factory` was verified on `main` at
`7b84f2c5`, with unrelated unfinished changes. It was not edited, reset or stashed.
Developer Studio allocated this task on remote main `6ddadfd3` after a transient
registry lock cleared. The preliminary clean investigation worktree is retained.

## Verified production failure

Product `gid://shopify/Product/15432135377203`, Tempted — Conquering Everest
Wall Art, handle `tempted-conquering-everest-wall-art`.

Render webhook service `srv-d9146onlk1mc739nrm7g` logs show create event
`1b8f7f5e-835f-5aa9-b4a9-1a8c2e24b3df`, triggered at 02:26:05 UTC and
received at 02:26:07 UTC (13:26 Sydney), with a verified HMAC.
Authoritative Supabase project `ceyzbfpuwuuxaiqwiltz` retained that receipt at
02:26:08 UTC. The create and seven updates were pending, repeatedly processed
with `Product registration pending: verified edition limit is missing.` There
were zero matching Edition Ops records. The Shopify display cache contained the
active, published Sports Cave / Framed Art product, its upload correlation tag,
and no edition-limit tag or sports_cave edition_total metafield.

The stop is `shopify_product_onboarding.verify_new_product`, introduced by
`69d7210e`: it required explicit limit metadata for all new identities. This
replaced the canonical default of 100 with a pending state. It is not a missing
webhook delivery, authentication failure or missing PSD. The earlier
`93a9d65e` upload-tag gate also deferred catalogue registration to MAP; the
onboarding path later bypassed it with `_onboarding_verified`.

## Repair

Missing explicit limits use the established default of 100. Explicit conflicting,
invalid or unsupported limits still require review. Current-state eligibility,
complete order-history verification, historical mirror vetoes, locked identity
checks, allocator ownership and retry/deduplication remain intact. Existing
products bypass new initialization and retain counters, runs and PSD mappings.
The upload-tag gate is removed; PSD and mapping holds are not import criteria.
Existing pending receipts retry automatically; no bulk receipt reset is required.

Product Uploads keeps the Mapping label. Its button performs a read-only local
lookup and opens the existing `/?page=edition_ops` workspace using the existing
top-level navigation pattern. Stable ID or available title selects the existing
Find product picker. Missing/ambiguous records are reported honestly. The map
API no longer creates a worker, attaches a PSD, moves files or acquires holds.
Legacy worker/recovery implementation remains to protect already admitted work;
new Mapping requests cannot start it. Prompts and help text describe manual
Add / Attach PSD.

## Legacy holds and manual recovery

Read-only production inspection found one retained hold, operation
`48fe3e9a-ceb0-4589-8585-95f05eaed54d`, product `15430466666803`.
It is already `Manually mapped`, has no lease and its database completion
function returns true. No unresolved production holds were found and none were
changed. The manual takeover terminal guard is installed.

The existing Add / Attach PSD save flow supports explicit administrator takeover
of an inactive failed operation. It locks intake rows NOWAIT before mapping locks,
rejects a live lease, provider mutation lock, conflicting identity, preparation,
rendering job or retained asset, preserves progress, and atomically saves the
manual link with a terminal retry fence. A failed save rolls back both. Do not
bulk-delete holds or override an active worker. No new recovery implementation,
schema migration, folder restructuring or file migration is needed.

## Verification

Disposable PostgreSQL/PGlite and simulated provider fixtures only. Focused checks
cover a new correlated eligible product without PSD, explicit limit or completed
mapping (even with a legacy hold), duplicate delivery and unchanged edition
numbers/runs, signed webhook rejection and durable receipt failures, title/ID
navigation, read-only Mapping API, manual PSD save/readback, inactive takeover,
active-worker rejection/rollback and existing mapping preservation.
JavaScript navigation lifecycle checks verify top-level Edition Ops navigation,
pending state, no mutation request, stale-response fencing and error handling.
Render topology validator passes; render.yaml is unchanged and no Blueprint sync
or resource creation is part of this release.
