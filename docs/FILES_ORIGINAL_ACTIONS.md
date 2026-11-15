# Files original Copy and Download â€” local implementation

Status: Implemented locally. Not committed, pushed or deployed.

Task: 20261014-650d846c, owner codex/files-original-20261015.
Isolated branch: codex/task/core-files-original-copy-and-download-20261014-650d846c.
Implementation base: f31b8cef6fc859f97ae8167fff4aef8ecd49bdd9 (the user-targeted committed Files V6).
The existing Files Performance worktree and its unfinished/review state were preserved.

## Changes

- `components/files_original_actions.js`: shared on-demand original fetch and clipboard conversion. PNG bytes are supplied directly; supported JPEG/WebP/static GIF/BMP originals are decoded and encoded as lossless PNG at native dimensions. No preview pixels, thumbnail fallback, upscaling or source writes.
- `components/files_window/index.html`: Copy Image context action in all five layouts; single-image Copy and Ctrl/Cmd+C also copy original pixels while retaining the existing internal file clipboard reference. Folder and multi-file internal copy/paste remain unchanged. Copy failures offer Download Original.
- `components/files_image_viewer/index.html`: toolbar, Ctrl/Cmd+C and custom image context menu use originals, including embedded and legacy previews. Download Original retains the existing responsive toolbar. Copy does not replace or resize the displayed preview. The 1:1 control now displays preview pixels without fetching an original.
- `files_upload_api.py`: existing authenticated, root-scoped download route now streams unmodified Dropbox original bytes, using its original metadata filename and attachment disposition. Shared clipboard script is authenticated. Streams are closed and responses are private/no-store. Saved Edition downloads retain their existing original endpoint.
- `tests/test_files_originals.py`, `tests/test_files_originals.cjs`: original byte, pixel, dimension, filename, permission and browser acceptance tests.
- `tests/test_files_window.py`, `tests/test_files_upload_api.py`, `tests/run_files_performance.py`: update download/clipboard contracts and include the new regression tests in the offline runner.

## Validation

All tests use synthetic artwork/provider responses. Python runner removes inherited provider secrets and denies external network connections. Browser requests are intercepted; no application server, production credentials or customer assets are used.

162 focused Python tests passed:

```text
python tests/run_files_performance.py tests.test_files_originals tests.test_files_window tests.test_files_upload_api tests.test_files_preview_v6 tests.test_files_performance_v2 tests.test_files_thumbnails_v4 tests.test_files_preview_v3 tests.test_files_preview_v5
```

Executed with the existing Files Python 3.13 environment (system Python lacks project dependencies).

Chromium acceptance:

```text
node tests/test_files_originals.cjs
```

Uses the bundled Playwright package via NODE_PATH. Real browser clipboard write/read proves a 256-pixel preview copies a 2400 x 1600 original, including a digest comparison of every decoded JPEG pixel. Checks PNG, WebP, static GIF/BMP, all five folder views, Copy and Copy Image, right-click viewer menu, embedded preview, unchanged downloaded bytes/filename, denied originals, unsupported clipboard access, and animated/unsupported format rejection. Ordinary browsing makes no original requests.

`git diff --check` passes. Local test logs are in `test-results/original-regression.log` and `test-results/original-browser.log` (ignored runtime evidence).

## Limits and performance

Clipboard formats are browser/OS dependent. Lossless PNG conversion preserves decoded native-size pixels, not the original file container, metadata, layers, animation or higher bit-depth/color-profile capabilities of external editors. PNG is supplied directly, but browsers may sanitize clipboard data. Animated GIF/APNG/WebP and undecodable formats show a limitation with Download Original; no silent first-frame or preview substitution. Browser memory/clipboard limits may prevent very large image copies; original download remains available. Other browser engines and live Dropbox have not been exercised.

Folder downloads were already unavailable and remain so; file actions in folders use originals. Folder copy/paste continues to operate on original file references.

Thumbnail and progressive preview loading are unchanged. A small shared script is loaded by Files/viewer. Original transfer and decoding happen only on explicit Copy/Download. Copy temporarily needs the full original plus decoded pixels in browser memory. Downloads now use bounded server streaming instead of a provider redirect, adding server bandwidth per download without buffering/recompressing the full file. Source files and production services are unchanged.
