# Wall Preview deliberate-save captures

Each call to the visualizer's existing `queuePreviewSave` now creates a random
`client_preview_id` for that capture. The browser session ID stays unchanged.
The ID and product/identity/consent metadata are snapshotted before queuing;
all network retries use that exact snapshot. A second intentional save gets a
new ID even when its image bytes and product are identical.

The existing API, `wall_previews`, `wall_preview_archive_jobs`, worker, and
Dropbox integration remain in use. Each capture owns one row and one job, so
an earlier pending image cannot be overwritten by a later capture. No migration,
new queue, or uniqueness-constraint change is required. Capture IDs cannot be
reused to replace different image/product data. Existing clients retain their
legacy overwrite behaviour during rollout; deploy the backend before updating
the local reviewed Shopify snippet. No deployment was performed by this change.

## Storage and visibility

New capture paths are:

`/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox/<email>/<product-slug>-<product-key>/history/<capture-uuid>.jpg`

For unknown identity, `<email>` becomes `Anonymous/<session-uuid>`. Product
keys derive from product ID (falling back to handle/URL). UUID filenames are
independent of timestamp resolution. The worker overwrites only retries of that
same capture. Existing legacy paths/files are not migrated.

Every capture is visible through the existing Inbox listing, ordered newest
first. The newest record for a customer/product is its latest capture; there is
no extra mutable `latest.jpg` copy. This prioritises retaining all images and
avoids an older delayed worker job overwriting a newer latest file.

Identity priority is explicit Download identity, logged-in Shopify email, then
the existing session identity voluntarily collected by Download. A valid known
email does not require an accompanying name. No subscriber databases or unrelated
browser storage are searched. Unknown identity remains anonymous. Each capture's
explicit Download image-reuse choice remains separate from identification;
automatic PLACE does not grant marketing permission.

Download finishes locally and releases its button without awaiting the archive
request. API acceptance is still queued, not archived. A worker failure retains
the image/job and existing retry/recovery behaviour. Subsequent captures remain
independent. The existing public rate limit is retained; CORS exposes Retry-After
and client retries honour the cooldown using the same capture ID. Before backend
acceptance, retries still depend on the page remaining open; this is not an
offline browser upload service. Exhausted retries log a safe warning, never a
false Dropbox success.

## Local verification

- Disposable loopback PostgreSQL with actual migrations/API/store/worker SQL;
  Dropbox and customer lookup boundaries mocked, no real customer sends/writes.
- Same/changed image, repeated product, A/B/C/D/A, anonymous visitors, 12 rapid
  captures, exact-request retries, worker failure/recovery, separate permission.
- Actual JavaScript metadata/queue/retry functions, identity fallback and cooldown.
- Existing 16 responsive browser journeys with mocked backend.

An actual Dropbox round trip is not asserted by these local tests. Production
must receive both backend and snippet updates before the new capture contract
is active end-to-end.
