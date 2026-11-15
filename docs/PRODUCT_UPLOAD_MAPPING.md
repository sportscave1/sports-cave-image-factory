# Product Upload → Edition Ops mapping

Released from the existing PRODUCTS task branch with explicit user authorisation
on 19 October 2026. The verified-source migration was applied to the documented
authoritative Supabase project and its trigger/privileges read back successfully.
Code was pushed to the task branch and main for the existing sports-cave-os service.
No Shopify product or original Dropbox PSD was modified during release verification.

## Existing services retained

The page already persisted `product_upload_intakes`, captured Dropbox metadata,
prepared/exported images and had a name-based Shopify handoff. Edition Ops already
provided locked product registration, active-run creation, history checks, verified
Shopify edition-metafield mirroring, PSD mapping/audits and a durable Companion
preparation queue. The older handoff could rename/move source files and waited for
publication. MAP uses the existing edition/mapping/queue services without invoking
that file lifecycle, product creation, publication, allocation or fulfilment.

## Identity and recovery

`upload_operation` is server-owned JSON in the existing private intake row. It pins
the operation UUID, Dropbox provider/file ID, revision, content hash, name and path.
Export binding records the eight-image manifest, folder and available verified
Dropbox receipts/IDs; the existing save checkpoint retains file hashes. Mapping
captures an immutable `mapped_output`, product ID/handle, edition/run IDs, lease,
completed steps and read-back verification time.

The copied **Shopify creation/update** prompt prepends `sc-upload-<UUID hex>` and
requires that tag in the initial creation request. The installed Shopify creation
connector supports tags, but does not expose a creation metafield argument. Hence
this implementation does not promise an unsupported metafield write. It requires a
confirmed `sc-edition-limit-N` tag (or an existing canonical edition limit). If absent,
the dialog asks for the confirmed limit; it never guesses one. Lifestyle prompts
are unchanged. Saved creation-prompt overrides still receive the correlation block
at the authenticated API boundary.

MAP searches all returned catalogue pages, includes drafts, checks the exact tag,
then fetches the resulting stable product ID afresh. Normal catalogue/webhook
registration defers new correlated products to MAP, preventing a race with its old
default edition limit. Once resolved, the persisted ID governs retries even if tags
are later edited. Titles, filename prefixes and sport are only selector suggestions.
Ambiguous/uncorrelated results require an explicit candidate selection. For legacy operations only, an existing
exact file-ID mapping is also valid recovery evidence. A new correlated upload can
never be redirected to an older product merely because it reuses the same PSD.

An owner-authenticated recovery link uses `/?page=product_uploads&upload=<intake UUID>`.
It is consumed once; starting another upload does not inherit the previous status.
The normal selector remains empty for a genuinely new upload.

### Current Peter Brock recovery evidence (read-only, 19 October 2026)

- Completed intake: `e1b09c2a-080a-4354-8a65-96a64edcd45c` (DRAFT, exported images).
- Saved product output: `/Sportscave Team Folder/04_OUTPUT/product-images/V8 Supercars Wall Art/peter-brock-king-of-the-mountain`.
- Exact PSD: `id:u1tYiAa2O-AAAAAAAABw7A`, revision `0165e259b3e1a01000000036d367e13`.
- Source path: `/Sportscave Team Folder/02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/99_PSD_NEEDS_REVIEW_DO_NOT_DELETE/peter-brock-king-of-the-mountain.psd`.
- Size: 217,337,232 bytes. Saved content hash: `ca52a834e47ac923d9f16b269b583987e1f9ecc8e428fa83dad7c235c520a20b`.
- A fresh Dropbox metadata lookup by permanent ID confirmed that ID, revision,
  name, path and size. The connector does not return a content hash; the hash above
  is saved upload evidence, not a newly downloaded hash.
- App catalogue: `gid://shopify/Product/15428059398451`, `Peter Brock — King of the Mountain`,
  handle `peter-brock-king-of-the-mountain-wall-art`, DRAFT. No existing edition/PSD
  mapping was found in the read-only checks. A newer incomplete intake for the same
  file is not substituted for the completed exported operation.
- The Shopify connector returned Product not found for the supplied GID. This does
  not prove absence from the application's configured store. MAP must fetch it
  through the app's own Shopify service before any registration. Live Shopify
  read-back and live mapping of this recovery case remain unverified/unperformed.

These values are documentation for this case only, not application constants. After
an approved release, reopen the completed intake, use MAP's exceptional selector
for the supplied stable product ID, and confirm a limit only if the product has no
confirmed limit metadata. Mapping cannot publish the draft or move its PSD.

## Safety and release dependency

- Intake row locks and an attempt lease serialize duplicate clicks;
  short database checkpoints bracket provider I/O. Product registration and mapping
  use existing table locks; worker product IDs and mapping file IDs remain unique.
- New records receive a run with next number 1 without allocating it. Existing
  records, runs, orders, counters and certificates are never reset. History conflicts
  and conflicting PSD links require Edition Ops resolution.
- Worker registration is the existing persisted queue/audit, with the captured
  source revision pinned transactionally. Worker processing/Cloud Ready status is
  separate from mapping completion and does not grant order eligibility.
- Green requires a fresh Shopify read, exact source/mapping, active configured run,
  matching verified edition metafields and persisted worker source. A failed GET is
  Status unavailable, never Unmapped. Refresh only reads those records.
- The dialog uses the host document's native modal, with content-driven sizing,
  focus restoration and cleanup on Close, Escape, selection change and iframe
  unmount. It never changes body overflow or creates a permanent page layer.

Apply `supabase/migrations/20261019070000_product_upload_verified_psd_mapping.sql`
**before deploying this feature**, only with release authorization. The current
database constraint permits main-folder PSDs only. The migration allows a direct
Review-folder PSD only when a private persisted upload proves the product/file
binding; its trigger uses invoker permissions and no public execution grant.
Standalone mapping/reset rules stay unchanged. Companion grants and technical
completion accept this same exact persisted proof, without moving the original.

## Changed files

- `product_upload_identity.py`, `product_upload_mapping.py`: correlation, resumable
  orchestration, authoritative read-back and exact-source worker proof.
- `product_upload_api.py`, `components/product_uploads/{index.html,app.js,mapping.js}`:
  prompt envelope, scoped API operations, MAP/status/dialog and lifecycle cleanup.
- `product_upload_dropbox.py`, `product_upload_mockups.py`,
  `product_upload_mockups_ui.py`, `product_upload_prompts.py`: source/export evidence,
  explicit saved-upload reopening and the new handoff instructions.
- `supabase_backend.py`, `shopify_sync.py`, `psd_mapping_store.py`: canonical
  registration with a confirmed limit, correlation deferral, narrow source proof.
- `auto_editions_onboarding_api.py`, `auto_editions_technical.py`,
  `auto_editions_bulk.py`: verified Review-source support through existing worker
  grants and completion checks.
- The migration above, focused tests/fixtures and this report.

## Verification

Focused tests use disposable PostgreSQL (PGlite), real registration/mapping/queue
services and synthetic Shopify/Dropbox boundaries. Coverage includes drafts,
confirmed limits, initial 001 without allocation, existing numbering, duplicate
clicks, catalogue pagination/delay/ambiguity, explicit legacy selection, source
changes, conflicting mappings, partial sync/worker retry, read-only refresh,
authentication, the database Review-folder guard and native transfer grants.
Technical completion was exercised with real local PNG/ICC fixtures and persisted
Review-source proof; original files and production providers were not used.

Desktop checks use `python -m tests.fixtures.product_upload_mapping_ui`: actual
component JavaScript, route implementations with a synthetic authorised account,
and disposable SQL within
an isolated representative page shell. Verified MAP, Pending sync on simulated
failure, retry to verified Mapped without changing next 001, reopening persisted
status, Escape/Close/focus and controls above/below the dialog. Narrow container and
enlarged text checks are fixture checks, not a claim of live browser-zoom coverage.
Node lifecycle tests cover source-switch stale responses and unmount/timer cleanup.
Real Streamlit `__main__` startup/routing/authentication regressions remain covered.

No real Photoshop/Companion run, live Shopify creation/tag write, live metafield
write or production full-page end-to-end generation was exercised. One existing
Edition Ops pagination test expects 50 rows but receives 120; the same failure was
reproduced using the unchanged HEAD backend. It is unrelated and left unchanged.

Focused final checks: 66 Python cases plus 14 parametrized subtests passed across
mapping, real entry-point routing, mockup exports, product activation/webhooks and
onboarding API suites. The expanded mapping suite then passed 20 cases, including
new-upload PSD reuse versus legacy recovery. Three focused technical/bulk completion
cases passed, including persisted Review-source proof. Node mapping lifecycle,
existing selection-state and independent copy-feedback checks passed. Earlier
intake/Dropbox/mockup regression run: 69 passed. These runs overlap; counts must not
be added as unique tests. Studio verification and `git diff --check` passed.
