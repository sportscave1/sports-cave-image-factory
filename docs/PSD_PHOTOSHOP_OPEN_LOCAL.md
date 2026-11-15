# Open PSD → Photoshop — local completion

Task 20261012-5849050d; owner codex-psd-01a12ffa; retained INTEGRATIONS task branch
codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
The worktree path, branch, ownership and clean starting state were verified before
editing. All changes are local and uncommitted.

## Error diagnosis and evidence

The owner authorized read-only Render diagnostics in Nathan's workspace on the
existing sports-cave-os service srv-d8kl4on7f7vs73dvavv0. Logs show the two failing
Open PSD requests at 2026-10-12 21:28:56 and 21:29:10 UTC, with duplicated 503 access
entries. All 57 application log entries in that interval were checked; none contains
an exception class or traceback for this failure. No raw logs/customer data or
credential strings were copied into this report.

The old endpoint called psd_open_metadata with its default include_preview=True.
A plain FileMetadata with no preview_url therefore invoked sharing_get_file_metadata.
An SDK exception was wrapped as DropboxApiError, then swallowed by _response_error
into files_unavailable. A missing preview URL alone would instead have produced a
FilesUploadError response, so the reported files_unavailable specifically indicates
an unlogged non-FilesUploadError. The exact original live exception cannot be
recovered from these logs. The SDK ApiError → DropboxApiError → generic failure path
is reproduced locally; no assumption about the live error's exact provider tag is
presented as a confirmed fact.

The new flow never requests sharing-preview metadata. Failures now log only a
controlled stage, exception/cause class names, allowlisted SDK union tags and a
support reference. No exception message, traceback, token, grant secret, URL,
Dropbox path or product identity is logged. This will distinguish mapping, auth,
Dropbox context, metadata-by-ID, scope and native-grant failures after release.

## Implementation

The existing Open PSD link and /api/files-psd-open endpoint are preserved. GET
returns a human-readable launch page, not raw JSON. In Sports Cave OS Desktop,
the page checks the existing WebView2 capability handshake, then POSTs only the
product link and allowlisted openPhotoshop action. Existing authentication, Files
permission and same-origin checks run before mapping or Dropbox access.

The server reads the authoritative Supabase mapping, retrieves current metadata by
stable Dropbox file ID with include_preview=False, checks the matching ID and
approved main-folder location, then issues an existing native transfer ticket. The
master-only manifest includes its Dropbox ID and content hash. Credentials remain
server-side; native requests retain allowed-origin, secret, expiry and path checks.
No arbitrary client paths or public Dropbox sharing links are accepted/generated.

The existing Windows host gains openPhotoshop, not a second application. It requires
one verified master manifest, validates the approved root-relative PSD path, reads
the configured locally synced file and requests cloud-placeholder hydration through
normal Windows reads. It checks the physical resolved path, size and Dropbox content
hash before starting Photoshop.exe explicitly with a quoted path, without shell
association. The hash follows [Dropbox's documented algorithm](https://docs.dropboxapi.com/dropbox-api/docs/technical-reference/content-hash).

The PSD action does not download a separate cache copy or silently open a stale
file. Missing sync/root/file, wrong bytes, hydration failure, local permission errors,
unavailable Photoshop and native-origin failures produce actionable messages.
Existing drag/copy/openFile transfers retain their existing cache behavior.

Normal browsers show guidance to open the same product/order in Sports Cave OS
Desktop and offer the existing helper package. Older/nonresponsive helpers display
update/restart guidance. Retry/cancel and a bounded hydration timeout are provided;
there is no polling. Table loading performs no additional work.

## Preserved data and functionality

No changes to psd_mapping_store.py, psd_directory.py, Edition Ops, Orders, database
schema, backfill scripts or any mapping rows. The existing 282 production mappings
are used as-is. No migration or import is needed. No edition numbering, allocations,
certificates, Shopify records, Photoshop master bytes or table layouts changed.

## Files changed

- files_upload_api.py — friendly launch page, metadata-only native grant, diagnostics
- components/psd_open/index.html — desktop handshake/handoff and browser/error guidance
- desktop_helper/SportsCaveFilesDesktop.cs — verified local master and explicit Photoshop
- desktop_helper/Install.ps1 — existing package version 10
- tests/test_psd_open.py — metadata/grant, real exported identities, permissions/log safety
- tests/test_desktop_helper.py — updated capability/version contracts, unchanged old flows
- tests/test_psd_native_windows.py — real Windows file/hash/path and launch-spec integration
- tests/test_psd_open_ui.cjs — desktop/browser/error/cancellation workflow
- docs/PSD_PHOTOSHOP_OPEN_LOCAL.md — this report

## Validation

152 focused Python tests passed:

```
python -B -m unittest tests.test_psd_open tests.test_psd_native_windows tests.test_desktop_helper tests.test_files_upload_api tests.test_psd_directory tests.test_psd_picker_api tests.test_edition_ops_stability tests.test_edition_ops_table_editing tests.test_orders_compact tests.test_dropbox_integration
```

The existing helper compiled and ran its disposable background-host test on Windows.
A native harness compiled the actual source, resolved a temporary approved path,
verified a >4 MiB file with the documented block hash, detected stale/missing/review
files and unsafe paths, and validated real installed Photoshop.exe discovery and
launch arguments. Temporary fixture bytes remained unchanged. Photoshop was not
started with any real master. Existing Windows protocol validation also passed.

Three representative identities from the approved 282-file export were tested with
mocked Supabase/Dropbox metadata, including renamed files and distinct links for
multi-product Orders. No production Dropbox file or database was accessed.

Both browser tests passed using intercepted network fixtures:

```
node tests/test_psd_open_ui.cjs
node tests/test_psd_picker_ui.cjs
```

Use the bundled runtime node_modules as NODE_PATH. Scenarios cover normal browser,
old helper, one-click grant handoff, missing local sync, unavailable Photoshop,
permission failure, non-JSON upstream errors, cancellation, and existing manual linking. No new dependency.
Studio/static and git diff whitespace checks passed. The table source is unchanged;
there are no new mapping/Dropbox requests per row. Native content verification adds
read/hash work only after an explicit Open PSD click.

## Existing Windows installation and release requirements

Read-only inspection found Photoshop 2026 installed and the existing per-user
SportsCaveOSDesktop.exe reporting version 7.0.0.0. It has not been replaced or
reconfigured. This feature requires the existing helper's version 10 package.

After separate owner approval:

1. Release this tested backend/asset change through the existing approved workflow
   to canonical sports-cave-os. No database migration or mapping backfill.
2. Download/extract the updated existing Windows helper package and run Install.cmd
   to upgrade in place. Preserve/confirm the configured locally synced Sportscave
   Team Folder and approved Sports Cave OS origin. No new desktop application.
3. Restart Sports Cave OS Desktop, sign in normally, keep Dropbox Desktop running,
   and click Open PSD in Edition Ops or Orders.

Remaining live validation: real cloud-only Dropbox hydration and an actual linked
master launch after the approved release/update. The exact old server exception
was not logged and remains unknown; new safe stage/class/tag diagnostics provide
that evidence for any remaining live issue. Native manifest tickets retain the
existing short-lived process-local transfer architecture and its expiry behavior.

No commits, pushes, deployments, helper installation, production data changes,
Dropbox contents modifications or public sharing links were performed.
Local status: Tested; owner-approved release/update pending.
