# Compact PSD modal and Open from Files — local completion

Verified category entry point C:/Dev/SportsCaveWorktrees/sports-cave-integrations
(codex/category/integrations), then retained owned task worktree
C:/Dev/SportsCaveWorktrees/sports-cave-integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d,
branch codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d,
task 20261012-5849050d / owner codex-psd-01a12ffa. Starting HEAD
3dfef913240dd92d6503bdfbc3f15c07e552ef0a was clean. Category files were not edited.

## Implemented

The existing zero-height PSD attachment component, already mounted by both tables,
now intercepts Open PSD anchors and canvas/window.open links. It opens the existing
universal PSD interface inside a compact native dialog over the current page.
The four existing API/native/preview/Dropbox/download actions remain available.
The five options occupy two paired rows and one full-width Open from Files row.
Helper guidance is hidden until Open in App is requested. In the modal, no file
metadata/native launch is requested merely by displaying the menu; direct legacy
PSD URLs retain their previous Windows auto-open behavior.

Dialog has X, Escape (including iframe focus), outside-click dismissal, subtle
backdrop and focus restoration. Content height adapts on demand (e.g. preview),
with bounded viewport scrolling. Closing does not emit a Streamlit component value
or rerun/reload Orders or Edition Ops. Only the existing attachment-save path emits
its established rerender event. Host WebView2 bridge is reused by the embedded menu
and Files screen; origin/server authentication and transfer protection are retained.

Open from Files loads the existing Files interface in the same dialog, expanding
only for that existing file manager. A new product-entry query parameter is resolved
through the same authenticated PSD endpoint with action files. Server reads the
Supabase mapping, resolves current Dropbox metadata by immutable ID, and validates
identity and approved location. Files loads that folder with refreshed metadata,
including subsequent pages, clears restored search filtering, and selects/focuses
exactly one matching Dropbox ID. It never selects by filename or guesses an absent
or duplicated identity. If Desktop openFile is supported, existing Files Open is
invoked once; otherwise the exact item stays highlighted with Open/Download enabled.
Normal Files startup, browsing, toolbar actions and internal dialog Escape handling
remain intact. Opening the linked Files screen does not require Desktop.

No mapping/schema/import changes. All 282 mappings, 51 missing records, edition
numbers, allocations, orders, certificates, customers and Shopify data remain
untouched. Dropbox remains master storage. No new file manager, dependency, copy,
helper installation or PSD modification. Windows/Mac helper source is unchanged.

## Changed files

- components/psd_picker/index.html: reuse launcher for PSD modal, close/focus/size.
- components/psd_open/index.html: fifth action, compact embedded presentation,
  lazy action details, host bridge and dismissal cleanup.
- components/files_window/index.html: mapped-product entry, ID-only selection and
  existing optional Open action, embedded host bridge access.
- files_upload_api.py: authenticated files resolution action, no transfer grant.
- tests/test_psd_universal.py: resolver identity, missing and permission coverage.
- tests/test_psd_modal_files_ui.cjs: intercepted modal/Files/native integration tests.
- docs/PSD_MODAL_FILES_LOCAL.md: this report.

## Validation and limits

Focused existing PSD API, universal, Files API, desktop helper, Orders and Edition
Ops tests pass. Existing 10 Windows/browser, 11 cross-device, and attachment picker
browser scenarios pass. New modal/Files cases cover both table entry points on
390px mobile and desktop, all five labels, compactness, no initial metadata reads,
multiple folder pages, similar names, missing ID, permissions, focus restoration,
Escape/outside/X dismissal, no page reload, existing Files native Open, ordinary
Files startup and host-only WebView2 bridge Photoshop handoff. All browser requests
intercepted; test data and metadata mocked. No production credentials/live data.

Files reads are lazy: one PSD resolution plus existing folder pagination only after
Open from Files. No new per-table-row request, polling, or underlying data reload.
Actual mounted Streamlit/native-device and authenticated Dropbox operations still
need owner release smoke testing; local fixtures exercise the actual launcher and
page sources rather than running an unsafe production-connected preview. Existing
platform/download/helper installation limitations remain as documented in
PSD_UNIVERSAL_OPEN_LOCAL.md. Existing native Files Open behavior is reused.

Local-only and uncommitted, ready for review after recorded tests. No commit, push,
deployment, software installation or production change was performed. Activation
requires only separately approved code release to the existing canonical service;
no mapping/database migration or backfill is needed.
