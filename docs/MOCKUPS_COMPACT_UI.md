# Mockups compact desktop workspace

Visual-only changes in `app.py` and new page-scoped `mockups_page.css`. Generation, image processing, prompt/randomisation rules, file paths, widget keys, upload callbacks and export/Dropbox services are unchanged by this UI task. Existing social prompt cards remain removed; historical export category handling is preserved.

- Compact heading and concise description, 14px below the 64px shell header.
- Setup controls and 260px artwork thumbnail share desktop width, stacking on narrow screens.
- All five generated images use a row-major gallery: 3 columns on wide workspaces, 2 on medium, 1 on narrow. Thumbnails use contain sizing and a 240px height cap; full-resolution source loading is unchanged.
- Three original lifestyle cards retain their titles, copy/edit controls, upload keys and saved-image actions.
- Neutral 36px secondary/upload controls, restrained primary gold, 6px radii and consistent Segoe/system copy-button typography. Copy success feedback fits inside the component.
- Repeated guidance consolidated, compact cards and upload areas. No wizard, new backend services or migrations.

## Measurements

Same local fixture, five synthetic square previews, no initial artwork selected or lifestyle uploads. Measured content block height, not a production speed claim:

| Viewport width | Before height | After height | Reduction |
|---|---:|---:|---:|
| 1920 | 3433px | 2033px | 40.8% |
| 1440 | 3554px | 2087px | 41.3% |
| 1280 | 3577px | 2658px | 25.7% |
| 390 | 4486px | 4085px | 8.9% |

Heading Y: 160px → 78px. First preview image Y at 1440px: 986px → 712px, 274px higher. Thumbnails: 380px → 240px. Mobile intentionally uses one column instead of cramped columns, so its reduction is smaller. Real height varies with image aspect ratios, uploads, errors and expanded full-resolution images.

Screenshots in `artifacts/mockups-ui`: `before-1440.png`, `after-1440.png`, `after-lifestyle-1440.png`, `after-setup-uploaded-1440.png`, `before-390.png`, `after-390.png`; numeric evidence is in `before.json` and `after.json`. These show the real page renderer inside an isolated synthetic shell, not a production session.

## Verification

- 32 tests in `tests.test_mockup_prompt_preview`: initial load, upload validation, generation gate, session/navigation preservation, restored packs, lifestyle uploads and ZIP inclusion. One source-order assertion updated for the consolidated generation heading; the assertion now targets the actual Generate button.
- 38 tests in `tests.test_mockup_product_variations`, `tests.test_mockup_reels`, `tests.test_mockup_eight_image_manifest`: random selections/persistence, assets, export manifests and mocked Dropbox behavior.
- `tests/test_mockups_compact_ui.cjs`: Chrome and Edge at 1920×1080, 1440×900, 1280×800 and 390×844; all five previews, four upload slots, responsive column count, neutral 6px upload buttons, no horizontal overflow, full-resolution show/hide and all three real clipboard copies. Additional local synthetic artwork upload verified side-by-side setup preview.
- Python compilation and `git diff --check` passed.

Native Windows WebView2 was not available for direct verification. Edge uses the same browser engine but is not a substitute for native-host testing. No production Dropbox/Shopify writes or new generation benchmarks were performed. Existing generation logic was not modified. No deployment or push.

## Files for this UI task

- `app.py`
- `mockups_page.css`
- `tests/test_mockup_prompt_preview.py`
- `tests/fixtures/mockups_compact.py`
- `tests/test_mockups_compact_ui.cjs`
- `docs/MOCKUPS_COMPACT_UI.md`

Run the local fixture with `.venv/Scripts/python.exe -m streamlit run tests/fixtures/mockups_compact.py --server.port 8895 --server.headless true`; run the browser test with Playwright available in NODE_PATH and `MOCKUPS_PHASE=after`. Set `MOCKUPS_BROWSER=msedge` for Edge. The fixture disables cloud saves and uses temporary synthetic data.
