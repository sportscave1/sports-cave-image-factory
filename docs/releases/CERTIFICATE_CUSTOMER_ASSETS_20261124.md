# Restore certificate print and preview uploads

The owner authorized fixing production certificate uploads and repairing all
new-template orders on 24 November 2026 (Sydney). The current final master and
Source Serif typography remain the source for newly generated JPG/WebP assets.

The Orders worker receives a prebuilt PDF from the database-backed generator.
That bypassed the engine's image generation; the uploader previously uploaded
only image paths already present. Existing PDF records also returned early,
and saving a repaired existing record discarded its new image links.

The uploader now completes the images even with a prebuilt PDF. Existing-record
retries fill missing print/preview files and save their account links. Successful
partial uploads are saved before reporting an incomplete upload, so retries
preserve those files. Existing PDF URLs, certificate identity, edition numbers
and unrelated certificates are preserved. Account and legacy order metafields
are mirrored using the existing compare-digest protection. No schema, allocator,
customer-account extension or Render topology changes are required.

`scripts/repair_certificate_customer_assets.py` is a dry-run by default and
requires explicit order IDs. `--apply` fills only missing images on issued
certificates, saves without schema work and reads the result back. It cannot
allocate editions or generate replacement PDFs. The intended repair set is
SC3539–SC3543 (six certificates). SC3544–SC3545 were unissued at the initial
audit; their normal generation must use the repaired workflow.

Validation: the collection/certificate release suite passed 191 tests plus 17
subtests with disposable PGlite; native account tests passed 49 tests and account
TypeScript checking passed. The new cases exercise current-template 3508×2480
print output, existing-PDF repair, no-op retry, partial-failure recovery,
prebuilt-PDF upload and merging assets while preserving a sibling certificate.
The topology validator passed. Three older manual-certificate tests fail
identically with the unchanged live engine/job modules; the baseline failures
are recorded separately in Studio evidence and do not arise from this repair.

Detailed commands, release-gate output and live repair verification are retained
in Studio runtime `20261123-57800a50`. Release/backfill status must be verified
against production rather than inferred from this implementation note.
