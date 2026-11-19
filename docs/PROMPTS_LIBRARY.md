# Prompts library

Admin navigation: Prompts, beside Design Studio. Three categories expose deployed source templates and instruction blocks without importing generation modules. Full prompts assembled for products still contain runtime context and existing module-level saved overrides; this library does not delete those overrides. Once a directly mapped Design or Upload template is activated, its released source takes precedence over the legacy override and its old module editor directs further edits to Prompts. Unreleased templates retain their existing behavior. It is not a catalogue of historical generated/customer prompts.

## Save and publish

Configure PROMPTS_GITHUB_TOKEN (Contents read/write for sportscave1/sports-cave-image-factory) and RENDER_API_KEY server-side. Connections run in the background; the Prompts page has no credential inputs. Codex connector credentials are not available to the app. No credentials are committed or returned in provider errors.

Drafts live on codex/prompt-library-drafts, outside main. First save preserves the deployed source as v1.0. Subsequent versions are append-only records with author, note, timestamp and source hash. Git Contents SHA checks reject stale concurrent saves. Downloads work without credentials. The session retains unsaved text across prompt selections.

Select a saved version, compare it, then Activate version and confirm publication. The source replacement permits only text in a catalogued template; Python interpolation expressions are retained as immutable slots. Placeholders and source hashes are checked. An atomic Git tree contains the changed source and prompts/releases.json only. A non-force main ref update rejects concurrent releases. The candidate SHA is saved before updating main, so an interrupted response remains traceable. There is no automatic retry after an uncertain publish. Make a new draft after inspecting a rejected/failed attempt.

Render status is polled every 15 seconds for the selected release. Live requires a live deployment manifest with the matching version ID and text hash. Later commits retaining that version also qualify. API errors remain Unknown/unavailable rather than becoming Live. Existing service ID srv-d8kl4on7f7vs73dvavv0 is fixed and verified; no Blueprint sync or service creation occurs. Supporting services retain their existing auto-deploy configuration.

This is a narrow Git-backed prompt release adapter. Developer Studio's general candidate executor remains simulation-only; this change does not enable arbitrary code publication from that screen. Template validation is not a prompt-quality test. The reference image's past-brief generation runner is not included: running one would need an isolated generation fixture and explicit integration design.

## Verification

python -m unittest tests.test_prompt_library tests.test_prompts_page tests.test_sidebar_navigation_cleanup
python scripts/validate_render_topology.py

Tests use synthetic credentials and mocked providers. AppTest mounts only the prompts page with stub account authorization, without starting the application or touching production data. All 94 catalogued templates were syntax-round-tripped without executing their application modules.

Account regression check: 80 tests ran with six failures; the same six failures reproduced with the unchanged f6cbb674 app source (legacy account UI, owner-only access assertion, Home UI and Files/upload fixtures). No new account failures identified.

## Entire category editor

Each category defaults to Entire prompt - all sections. The full editor and individual section editors share unsaved session buffers in both directions. SECTION and END headings identify each block; leave these headings and every template placeholder intact. Invalid/incomplete combined text remains in the full editor with an error and cannot be saved or activated. Downloads and a full preview remain available, with expandable individual section previews below.

Save draft stores one immutable category version containing the full text and the changed sections with their original source hashes. No live content changes until the saved category version is activated. Activation validates every changed section against current Git, folds multiple changes to the same source file together, then publishes all source files and their individual release manifest entries in one commit and one non-force main update. A conflict prevents the whole release. Existing individual draft histories remain intact; deployed individual editors load the new section text after deployment. The full category view includes all deployed templates, not a product-specific runtime prompt. Search filters selector choices without truncating the entire editor.

## Copy a product-applied draft

Open Prepare prompt to copy and enable Select a product. Choose a workflow and load its read-only input list, or enter a product URL. There is no product-details field. Ads automatically loads a searchable Edition Ops product dropdown (names and URLs only), cached for the session with a Refresh products button. Selecting an edition fills its URL. Upload and Edit design retain the Design Studio dropdown; Design workflows retain Home/Refresh suggestions.

The full current editor draft is immediately assembled with the selected product context. Known product placeholders are substituted in a single pass; missing values and runtime slots remain intact. All sections are preserved. A prominent Copy full prompt button copies the complete text, with a browser clipboard fallback. The long text is collapsed under an optional preview. The main library also opens on Copy full prompt, with editing in a separate tab. Editing the product or draft automatically refreshes it; nothing is saved or activated by copying.

There is no OpenAI request, API key requirement, generated answer, image download or test job. Custom URLs are included as supplied without fetching them or requiring catalogue membership. Attach the source artwork yourself when manually testing image-based workflows.

Verification: python -m pytest tests/test_prompt_tests.py tests/test_prompts_page.py tests/test_prompt_bundle.py tests/test_prompt_library.py tests/test_sidebar_navigation_cleanup.py -q
