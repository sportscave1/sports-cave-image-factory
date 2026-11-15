# Universal Open PSD — local validation

Task 20261012-5849050d, owner codex-psd-01a12ffa. Verified retained INTEGRATIONS
worktree: C:/Dev/SportsCaveWorktrees/sports-cave-integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
Branch: codex/task/integrations-dropbox-psd-links-edition-ops-orders-20261012-5849050d.
Starting HEAD 12177da83058a5394f96532ea4c6800f730bb07c; clean before editing.

## Behavior and preservation

Edition Ops and Orders keep their existing Open PSD links and table layout. Both
open the same compact responsive four-option page. Supabase remains authoritative;
there are no schema, mapping, import, catalogue, allocation, Shopify or PSD writes.
The 282 existing mappings and 51 missing records remain untouched. Existing
snapshot tests still validate 282 approved matches and 40 review exclusions.

- Windows Desktop: original one-click Photoshop 2026/v10 workflow retained.
  Capability negotiation enables optional default PSD application opening in the
  updated existing v10 helper. Both native actions use the same root-constrained,
  content-hash-verified local master/hydration path; neither downloads a duplicate.
  Older v10 builds keep Photoshop and disable the optional default-app choice.
- macOS: existing helper gains a verified master URI mode. Server metadata supplies
  only the approved relative path, size and Dropbox content hash. Helper restricts
  that mode to the approved main folder, resolves symlinks under the configured
  local root, reads in 4 MiB blocks for verification/hydration, then uses /usr/bin/open
  for the default PSD application. Legacy helper actions remain compatible.
- iPhone/iPad/Android: responsive menu, lightweight preview, authenticated original
  download, and authorised Dropbox navigation. Open in App gives supported Dropbox
  Open with/share guidance or Files/Downloads opening instructions. No invented
  application schemes, automatic full-file download or heap-buffered master share.
- Windows browsers/Linux/ChromeOS/other modern browsers: same preview/Dropbox/download
  options, with default-app/file-manager guidance. Browser cannot reliably detect
  installed apps or open arbitrary applications.

Preview requests only a bounded Dropbox-generated JPEG thumbnail (1024x768,
maximum 2 MiB); unavailable preview offers Dropbox or original download. It does
not flatten or parse the original master. Dropbox navigation uses the freshly
verified account-folder path with the exact filename selected; it requires the
user's own authorised Dropbox account and creates no shared link. Native app or
share actions offered by Dropbox itself vary by OS/account and installed apps.
Dropbox's website navigation convention must be checked during approved release
smoke testing; no real account navigation was performed locally.

Original download rechecks signed-in Files permission, mapping, stable Dropbox ID,
current approved location and revision on every request. SDK download is pinned
by ID/revision, response metadata is checked again, and chunks stream at 256 KiB.
No public link, temporary Dropbox URL, reusable browser download grant, new
storage copy or browser master Blob is created. Existing secret-header native
transfer/origin controls are retained. Upstream closes on completion, failure or
client cancellation. Interrupted originals need a fresh download; resumable Range
requests are not provided. Long real transfers still depend on deployment proxy
timeouts, connectivity and sufficient device storage.

## Diagnostics

The previous files_unavailable path depended on sharing preview metadata that is
not available for ordinary unshared PSDs. New actions resolve ordinary file
metadata by stable ID with include_preview=False. Safe diagnostics retain stage,
exception classes, allowlisted provider tags and support reference only. Known
missing-file and Dropbox-auth/permission errors now have actionable messages.
The precise historical live exception was not recorded by old logs and cannot be
reconstructed; see PSD_PHOTOSHOP_OPEN_LOCAL.md for the prior read-only evidence.

## Files changed

- components/psd_open/index.html: shared adaptive four-option interface.
- files_upload_api.py: describe/preview actions, authenticated original stream,
  safe missing-file/access diagnostics.
- dropbox_integration.py: ID/revision-pinned streamed original and bounded thumbnail.
- desktop_helper/SportsCaveFilesDesktop.cs: optional verified default-app action,
  preserving HelperVersion 10 and existing Photoshop behavior.
- desktop_helper_macos/SportsCaveFilesHelper.py: verified master/default-app mode.
- tests/test_psd_universal.py and tests/test_psd_universal_ui.cjs: new validation.
- tests/test_psd_open_ui.cjs, tests/test_psd_native_windows.py and
  tests/test_desktop_helper.py: existing compatibility coverage extended.
- docs/PSD_UNIVERSAL_OPEN_LOCAL.md: this report.

## Tests and performance

Focused Python regression suite passes, including real compiled Windows helper,
read-only >4 MiB hashing, actual Photoshop executable discovery and launch argument
construction; no real Photoshop process/master opened. Representative export IDs
and multi-line Orders retain distinct correct links. Missing/review/stale files,
permission/origin failures, unavailable Photoshop/default app, preview fallback,
Mac hash/default-app/missing-file logic and stream cleanup covered.

Intercepted Chromium tests: 10 desktop/browser cases + 11 universal platform/fallback
cases passed. Existing manual PSD Add/Search/Select/Confirm/Save/Open/replace/cancel
flow also passed. No live services/customer data or production credentials used.
Platform tests emulate capability/user-agent branches, not physical Mac/mobile OSes.

Synthetic 2 GiB chunk stream: 0.031 seconds, peak Python allocations 0.50 MiB,
256 KiB chunks. This measures bounded-memory stream iteration, not internet speed.
Existing synthetic snapshot benchmark: 282 matches plus 2,820 projections in 0.0312s.
Orders 100-row preparation remains below 1 ms in the mock test. Page-loading code
and cached batch mapping queries are unchanged; added table-row Dropbox requests: 0.
No production timing or real >1 GiB transfer claimed.

## Release readiness and remaining activation

Locally implemented/tested; uncommitted. No push, deployment, installation,
production backfill/migration or live Shopify/Dropbox modification performed.

Installed Windows helper is still version 7.0.0.0 (read-only check), so it needs an
owner-authorised update using the existing v10 package after an approved code
release. Existing v10 Photoshop-only builds keep working; new default-app action
requires the refreshed v10 package. Mac verified mode requires updating the existing
Mac helper package and configuring its synced Sportscave Team Folder. No software
was installed in this task.

Exact next steps, separately authorised: review local diff; approve app release;
release these code files to the existing canonical service without changing mappings
or database; update existing helper packages on devices as needed; perform owner
smoke tests for Windows Photoshop/default apps, Mac protocol/default apps and cloud
placeholders, mobile Files/Dropbox flows, authenticated Dropbox navigation and a
large real transfer through deployed proxy limits. Supabase activation steps: none.
