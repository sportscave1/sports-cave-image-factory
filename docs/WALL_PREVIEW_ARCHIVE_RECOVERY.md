# Wall Preview archive recovery

The archive runs inside `sports-cave-seo-worker` (`sports_cave_worker.py` →
`crm_worker.py` → `wall_preview_archive.tick`), not the web service. Its environment
must include the existing server Dropbox configuration:

- `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`; or the supported
  `DROPBOX_ACCESS_TOKEN` fallback.
- `DROPBOX_ROOT_PATH` where configured by the existing Dropbox integration.

The canonical destination remains `/Sportscave Team Folder/03_ASSETS/11 Wall Preview Inbox`.
On 2026-10-06 the existing four web-service settings were securely copied into the
dedicated Render group `sports-cave-dropbox` and linked to the existing worker.
No primary service/Blueprint was created or changed. Keep secrets in Render only.

## Recovery procedure

1. Verify worker authentication and root visibility without printing tokens.
2. Inspect only archive job IDs/version/state/reason/image presence. Do not dump
   image bytes, customer emails, or credentials into logs.
3. Existing queued jobs retry normally. For exhausted jobs, review specific IDs:

   `python scripts/recover_wall_preview_archives.py PREVIEW_UUID [PREVIEW_UUID ...]`

4. Add `--apply` only for reviewed IDs. This locks preview then job and requeues
   only `failed` / `archive_unavailable` jobs whose current version still has image
   bytes. It does not process email/customer jobs or upload anything itself.
   A second run makes no changes. Never run a bulk historical email worker to
   recover archives.
5. The normal worker processes them. `wall_preview_archive.tick(preview_id)` can
   process one explicitly selected due archive without running any email logic.
6. Confirm job `done`, persisted nonempty file ID, and actual Dropbox metadata
   matching that ID. An HTTP 200/`queued` response alone is not completion.

## Retry and identity semantics

PLACE and Download use the same composite/client preview ID. An identical request
repairs a failed/missing archive job without changing the preview version. Healthy
queued jobs retain backoff/attempts. Only a confirmed file plus a completed current
job is reported as `archived`; `accepted` and `queued` are distinct.

The worker derives the destination from the current persisted email using the
existing customer-folder escaping convention. It overwrites the stable filename,
then atomically moves an existing Anonymous file into that folder. The old DB path
is retained until Dropbox succeeds. A failed move retains the sole valid copy;
a move-success/DB-commit-failure retry recognises the destination. An unexpected
source/destination collision fails closed. No delete/copy-based cleanup is used.
Image reuse permission is still recorded only by its separate consent contract.

No migration, new queue, or new storage integration is required. Release the
local backend retry/relocation changes before relying on these new recovery
semantics in production; environment repair alone does not install code.

## Verified 2026-10-06

- Existing worker runtime: no missing auth keys, auth resolved, team folder and
  Inbox visible. Disposable JPEG create/upload/overwrite/metadata checks passed.
- Synthetic PLACE API submission `d80aa21d-cfa0-4b47-baa7-a0c8844e1ca1` reached a
  completed archive job and matching actual Dropbox file ID.
- Synthetic Download API submission `5965247f-2044-4427-abb9-a5483ad09195` reached
  a completed archive and synthetic email folder with marketing permission false.
- All six outage jobs plus these two diagnostics are `done` with file IDs. No
  exhausted jobs remained to requeue manually; no direct production SQL writes
  were used. Archive-only processing did not invoke email/customer workers.
- The new `_upload` helper was additionally executed in isolation against only
  the disposable Dropbox image: atomic relocation retained the file ID, removed
  the old source, and a stale-path retry made no duplicate. Deployed source files
  were not replaced by this test.
- `CRM_TEST_POSTGRES=1 python -m unittest discover -s tests -p 'test_wall_preview*.py' -q`:
  165 passed against the disposable local PostgreSQL fixture/mocked providers.
- `node tests/wall_preview_completion_ui.cjs`: 16 responsive journeys passed.
- Queue/composite, CRM adapter, and analytics Node tests passed; Python compile
  checks and `git diff --check` passed. Test-only fixture normalizes CRLF/LF.

Synthetic files are clearly labelled diagnostics and are not customer images.
The live Shopify theme was not edited; the new browser state change is local.
