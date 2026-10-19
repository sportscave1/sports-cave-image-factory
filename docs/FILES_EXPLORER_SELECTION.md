# Files Explorer selection — local implementation

19 October 2026. Studio task `20261019-689394db`, owner
`codex/files-selection-01a1532d`. Branch
`codex/task/core-files-explorer-selection-and-exact-origina-20261019-689394db`.
Approved base: `59b609728b182c6c997f02ed0a8786fff0483095`.

## Isolation

The supplied `sports-cave-files-performance-v1` checkout was clean, but its
registered owner/task is an earlier Files Performance task. The CORE category
checkout exists and is clean, but is an idle entry point under Studio rules.
Studio New allocated this separate CORE task. Neither existing checkout was
edited. No application server, provider connection, credentials, helper, worker,
commit, push, merge, or deployment was used.

## Findings and remaining limitation

The card handler called `setFilesClipboard("copy")`, stored internal path
references, and only for one image called `copyOriginalImage`. Multiple selected
files produced an internal-only success message without writing native files.
The preview handler `copyImagePixels` used the same `FilesOriginal.copy` service
with a relative-path download URL; the card supplied an absolute-path download
URL. The authenticated download endpoint supports both forms and streams source
bytes with an attachment filename.

The old shared service fetched the source and converted WEBP/JPEG/etc. through
`createImageBitmap` and canvas into `image/png`. Its preview success therefore
proved decoded image copying, not preservation of original filenames, formats or
bytes. Chrome 155.0.8059.80 locally reproduced PNG clipboard success from BOTH
old handlers on the approved base. The reported card-only failure was **not
reproduced**; its environment-specific cause remains unresolved. It would be
incorrect to attribute that report to a confirmed URL or permissions bug.

The confirmed clipboard limitation is the web runtime itself: it exposes the
browser Clipboard API, without a Files native file-list bridge. Chrome rejects
`image/webp` with "Type image/webp not supported on write" and two ClipboardItems
with "Support for multiple ClipboardItems is not implemented". PNG pixel data
has no original filename and is not a Windows file-list transfer. The shared
service now rejects exact-file Copy before any fetch or clipboard mutation. It
never substitutes PNG, a custom format, a URL, an internal reference, or a subset.
No native bridge was introduced or reconnected.

Native original-file copying remains unavailable for one or multiple files.
ChatGPT paste and Windows Explorer paste were **not verified**: native desktop
control is unavailable in this session, and the source file clipboard operation
cannot be produced by this web runtime. Browser Clipboard API success/readback
is explicitly not used as proof of a destination receiving original files.

## Implemented behavior

- Click selects; double-click opens the existing embedded preview. Ctrl toggles,
  Shift ranges, Escape clears, selected cards have a highlight and checkmark.
- Empty-space pointer drag draws a translucent rectangle in any direction.
  Intersection includes virtual cards scrolled out of the DOM. Coordinates use
  scroll offsets and viewport-to-layout scale; edge scrolling and manual scroll
  work during selection. Pointer cancellation, capture loss, blur, and view
  changes release capture, the rectangle and animation frame.
- Ctrl+A and Ctrl+C require file-view focus; inputs/contenteditable controls keep
  their shortcuts. Buttons, menus, cards, the details header and scrollbar do not
  begin a rectangle. Touch scrolling remains unchanged.
- Compact Copy/Copy N files snapshots immutable IDs, names, revision and original
  URLs. Selected-card context Copy uses the selection; unselected-card context
  Copy selects that card alone. Pending state is Copying; unsupported runtime
  reports Copy unavailable and resets the button after two seconds. There is no
  real clipboard-success path in this runtime.
- The error offers explicitly labelled Download Original for the captured files.
  The existing authenticated streamed downloads preserve original names and bytes
  and release temporary frames after 120 seconds. Browsers may request permission
  for multiple downloads. Copy and selection fetch no originals; no bitmap or
  object URL resources are allocated by Copy.
- Existing internal copy/paste is explicitly labelled Copy in Files; Cut/Paste,
  uploads, rename, delete, navigation and previews remain available.
- Fixed repeated-toast deduplication retaining an old action closure: each new
  copy failure now updates its fallback to the latest captured selection. Toast
  timeouts also honor their requested duration.

## Local validation

Bundled Playwright, installed Chrome 155, synthetic assets and intercepted routes
only; all unexpected host requests fail. No production imports/startup.

- `node tests/test_files_originals.cjs`: baseline handler tracing, real clipboard
  capability rejection, click/Ctrl/Shift, focused Ctrl+A/C, input exclusion,
  Escape, rectangle intersection against card geometry at 80%, 100%, 125% CSS
  zoom, both axes/directions, 400-card virtualization and autoscroll, five
  nonvirtual views, preview open/close, pending-state immutable snapshots,
  repeated fallback updates and original download checks. Two distinct valid
  WEBPs downloaded together retain exact source bytes and filenames; single
  download also verified. This tests downloads, not native paste.
- `python -m unittest tests.test_files_window`: 60 passed, including authenticated
  original download contracts and existing file operation contracts.
- `node tests/test_files_premium_ui.cjs`: four platform journeys passed (Chrome
  with Win32/Mac/iPhone/WebView platform fixtures), including internal copy/move,
  create/rename/delete/search, JPG/PNG/WEBP/PSD/PDF embedded previews and zero helper
  traffic. Internal copy uses the explicitly labelled Copy in Files action.
- `node tests/test_files_compact_layout.cjs`: passed; seven widths 320–1920,
  five views, 2,000-item virtualization, keyboard navigation and DPR3 touch layout.

Reproduce browser checks with `NODE_PATH` set to the bundled runtime's
`dependencies/node/node_modules`. JSON evidence and screenshots are generated
under `test-results/files-selection` and `test-results/files-compact` (ignored).
Changes are intentionally uncommitted. Studio cannot report clean committed
review readiness. Local selection/fallback implementation is complete; the native
clipboard requirement and reported card-only failure remain unresolved as above.

## Release authorization

The user subsequently authorized pushing to Git and Render. The seven task files
were committed and integrated with the latest origin/main without conflicts.
The local-only statements above describe the initial implementation phase;
clipboard limitations remain unchanged. Re-run focused checks against the
integrated revision before pushing to the existing main/Render deployment path.
