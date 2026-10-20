# Product Upload prompt repair — local verification

Task: 20261020-181c19ae; owner: codex-copy-repair-20261020.
Worktree was created with Studio, then fast-forwarded locally to the existing
Product Upload release snapshot cf424ef4 (the Studio default was older and did
not contain this workflow). No commit, push, merge commit or deployment created.

## Findings and limits

Save completion applies its receipt only when the intake and save token still
match, then reruns Streamlit. The page gates the handoff on completed export,
no running jobs and a valid saved_source_version. Its key contains visit/intake,
not the save revision; no save-triggered key churn was found.

The handoff used the entire workflow component. Its HTML referenced
/product-upload-mapping.js and /product-uploads.js; both handlers authenticate
before serving JavaScript. Mapping initialization precedes componentReady. A
failed script request therefore prevents the handshake and removes access to
copy, despite a successful save. The existing JS files are tracked source assets,
not missing npm build output. Production registers the root handlers in
sports_cave_server.py; there is no frontend build step for this component.

The regression browser test reproduced rejected (403) root script requests and
absence of componentReady. This establishes a bootstrap failure mechanism, NOT
that production returned 403 in the reported incident. No live console/network
trace or deployment artifact was available/inspected. Network latency/proxy is
not a confirmed cause. No independent JavaScript syntax failure was found.

## Repair

Workflow scripts now use ./mapping.js and ./app.js, resolved by Streamlit's
component asset handler from the same packaged directory as index.html.
Copy Upload Prompt is an independent single HTML asset with inline JS and no
mapping/API/bootstrap dependency. Its click synchronously invokes writeText on
already prepared text; success says Copied ✓ briefly. Clipboard errors remain
retryable. Native Retry copy controls remounts only that control and can recover
an asset load failure without refreshing the page or changing saved state.

The prompt endpoint and Streamlit share precisely the same prompt composition,
using current_source and existing saved receipt metadata. Prompt wording and
instructions are unchanged. Preparation uses no image downloads or folder scans.
Cache identity includes actor, intake, mode and saved version. Server revalidates
after prompt composition; browser revisions fence late completions and timers.
Copy acknowledgement validates the current version again. Existing gallery,
image copy, generation and save code is unchanged.

## Checks actually run

- python scripts/verify_product_upload_copy_mount.py: passed in headless Edge
  with real Streamlit 1.66 component serving and real browser clipboard/paste.
  Synthetic save receipt/in-memory store; no real Dropbox save or production API.
  Verified save -> enabled copy -> Copied ✓ -> Ctrl+V (57,591 characters), second
  save updates metadata, product switch removes old prompt, denied clipboard
  retains Saved and retries, delayed old completion cannot update new revision,
  blocked component HTML can recover through native Retry copy controls.
- Workflow mapping.js/app.js returned 200 under /component/...; ready/render ran
  even with API unavailable in the fixture. Fixed flow had no page JS exceptions.
- Old root-script 403 reproduction: no ready handshake.
- python -m pytest tests/test_product_upload_source.py
  tests/test_product_upload_package.py -q: 35 passed, 3 skipped (database fixture).
- Python compileall, node --check workflow JS, git diff --check: passed.

Assets must ship with the application source, including the new
components/product_upload_prompt_copy/index.html. No CDN or frontend build is
needed. This is an uncommitted LOCAL implementation. Live end-to-end save and
production cause verification remain outstanding; deployment is not claimed.
