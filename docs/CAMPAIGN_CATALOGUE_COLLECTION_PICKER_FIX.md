# Campaign catalogue collection picker fix

Local implementation, 10 October 2026. No commit, push, merge, deployment, Shopify mutation, published-campaign change, or customer email delivery was performed.

## Confirmed defects

1. **Duplicate collection titles selected the wrong collection.** The authorized read-only Shopify query returned 42 collections, including four named `THE GIFT EDIT`. The picker used titles alone as `st.selectbox` formatted labels. Streamlit's `create_mappings` and `SelectboxSerde` map these labels back to options; the last duplicate wins. Before the fix, selecting fixture Collection/1 with the same title as Collection/2 caused `Catalogue.search` to receive Collection/2. This was reproduced before editing and passes after the fix. Duplicate titles now include the collection's numeric ID; ordinary titles and `All collections` remain unchanged. No additional Shopify request or query field was introduced.

2. **A checkbox update could be lost when the collection changed in the same rerun.** The old implementation updated its basket while rendering the new result rows. A simultaneously selected product from the previous collection was no longer rendered and was never captured. Before the fix, an AppTest submitting a checkbox change and collection change together produced an empty basket. Checkbox callbacks now capture the old product before Streamlit replaces the results. The regression also checks selecting across collections and deselecting while switching filters. A production-version 320px browser run additionally exposed a checked control with a zero basket count. Render-time basket writes were removed; callbacks now own selection changes and checkbox state is synchronized from the basket. The same narrow-screen save/reopen journey then passed. This observed local symptom does not establish the cause of every reported live freeze.

3. **Product loading failures hid the action controls.** Cancel, the selected count, and Add selected were inside the product-loading try block. They are now independent of loading. Shopify verification failures have a separate message and retain the basket without modifying the draft.

4. **Modal dismissal did not restore the original trigger focus.** An inspected 320px run returned focus to the composer iframe but not its Select products button. Add, Cancel, and the Streamlit dismissal callback now issue a one-time section-specific focus request. The composer opens that section and restores its button focus without accessing the parent DOM. Browser assertions cover Add, Cancel, Escape, and the native close button. Verification failures keep the modal open and do not issue a focus request.

## Production-specific investigation

Read-only Render diagnostics identified the canonical service `sports-cave-os`, its `python sports_cave_server.py` entry point, and live commit `ae3baaeb55a42710edf9518443dac582544a7c5c`. The local checkout was `b526c1d0dc3735599ee0b3ad6410f4f1ba1017e8` and has substantial pre-existing local work. The deployed picker function was inspected through GitHub; its selection code matched the original local picker, although other editor implementation details differ.

Production installed **Streamlit 1.65.0**; the shared local virtual environment contains **1.58.0**. An isolated copy of 1.65.0 was installed under this chat's work directory, without upgrading the shared environment. The final local server serves `index.CKCTizkM.js`, matching the production main frontend asset. Browser selected-value assertions account for 1.65.0's input-based display; a failed assertion against container text was a test compatibility issue, not evidence of an application failure.

The existing authorized live browser session showed zero drafts. Investigation there remained read-only; no live draft was created and no Add selected operation was applied to live content. Relevant Render picker-error log searches returned no matches. The connected Shopify app successfully retrieved the actual collection list and a filtered V8 Supercars product page, using the existing picker queries without mutations. Those connector credentials are not proof that the application's own credentials have identical scopes.

## Files changed

- `crm_section_ui.py`: unique collection labels, pre-rerun basket callback and synchronized checkbox state, loading-independent controls, explicit verification failure message, modal dismissal focus handoff.
- `components/crm_sections/composer.js`: restore focus to the intended Catalogue selector once after modal closure.
- `tests/test_crm_picker_selection.py`: exact-ID duplicate-label regression, simultaneous checkbox/filter regression, loading and verification failure checks.
- `tests/fixtures/crm_collection_picker.py`: real Campaigns workspace, email editor, shared application CSS, synthetic Shopify adapter, and disposable loopback SQL.
- `tests/check_crm_collection_picker_browser.py`: real browser journey through existing draft, Catalogue, collection selection, three-product basket, Add selected, autosave, and close/reopen.
- `tests/check_crm_collection_picker_edges.py`: duplicate-title selection, empty/unavailable collections, pagination, search, Active only, limit, Cancel, reopening, keyboard, Escape, hit targets, and mobile touch taps.
- `docs/CAMPAIGN_CATALOGUE_COLLECTION_PICKER_FIX.md`: this report.

## Behavior and performance preserved

Collection IDs remain the actual selector values and `Catalogue.search` filter arguments. A collection is only a picker filter; it never automatically inserts the whole collection. Existing filter-change pagination reset, dialog fragment reruns, lightweight searches, cached collection/product loading, 80px source thumbnails, batched fresh product resolution on Add selected, snapshot artwork, autosave, draft recovery, preview rendering, catalogue CTA settings, and the 12-product apply limit remain in place. The cache and GraphQL service files were not changed. Checkbox callbacks perform only local basket updates; focus callbacks also update local session state without service requests.

Add selected still resolves the basket's IDs with `fresh=True`, commits only to the intended catalogue section, and follows the existing autosave path. Controlled browser tests confirmed products 1, 2, and 3 in the editor after applying and after closing/reopening. Cancel after extra selections retained the original three saved products. Missing/unavailable collection results do not fall back to unrelated collections. Verification failure tests confirm no draft mutation.

## Verification

The required journey uses browser clicks, visible dropdown options, checked product controls, and persisted SQL-backed drafts, not a selectbox-existence assertion. It chooses two products from Motorsport, one from Tennis, returns to Motorsport, verifies both previous selections, applies all three, verifies the applied products, closes the email, and reopens it. The edge script additionally chooses both duplicate-title collections and checks that their distinct result sets appear. Dropdown hit-target checks verify that an option's center belongs to that option rather than a modal overlay.

The focused unit/AppTest suite ran 28 tests on both Streamlit 1.58.0 and 1.65.0: 24 passed and four pre-existing tests requiring their separate PostgreSQL configuration were skipped. The browser tests independently use the repository's actual CampaignStore and disposable PGlite SQL fixture for save/reopen verification. The earlier 1.58.0 saved-draft journey passed all six browser/width combinations; the final 1.65.0 matrix passed both complete journeys for all six combinations:

| Browser | Width | Choose → Add → autosave/reopen | Edge cases |
|---|---:|---|---|
| Chrome | 1440 | Pass | Pass |
| Chrome | 390 | Pass | Pass |
| Chrome | 320 | Pass | Pass |
| Edge | 1440 | Pass | Pass |
| Edge | 390 | Pass | Pass |
| Edge | 320 | Pass | Pass |

Edge cases include duplicate labels, empty/unavailable collections, pages, search, Active only, a 13-item basket disabling Add, Cancel retaining the saved three products, modal reopening, keyboard selection, Escape, native close, and focus restoration. Narrow-width edge journeys use touch taps on options; core journeys use mouse clicks. AppTest separately checks simultaneous/rapid checkbox and filter updates and actual verification failures.

`failure-first-selection.png` is retained as pre-final-fix evidence, not a passing screenshot. The `chrome-*.png` and `msedge-*.png` files show the successfully reopened three-product catalogue; `dropdown-*.png` files show visible options.

## Evidence and limits

Screenshots of the open options and saved three-product catalogue are saved in the chat's `outputs/picker-evidence-165` directory. Broken fixture image icons are expected: browser requests to external hosts are blocked; synthetic artwork URLs remain in the saved product snapshots.

No CSS stacking, hidden-option overlay, clipping, or focus-trap root cause has been confirmed. No speculative z-index changes were made. The confirmed duplicate-label mapping defect is present in actual Shopify data; it is not proof that every reported freeze or failure to open had that same cause. The local harness runs the actual Campaigns workspace/editor and extracted shared application styling, not the full authenticated production startup and its external services. Full published-campaign or live draft mutation testing was intentionally excluded by the local-only instruction. This report does not claim that a new release is live or that every production-only symptom was directly reproduced.

Multiple Shopify collection pages are covered by the existing cached-service regression. Collection types remain unfiltered by the existing GraphQL query, so manual and automated collections are supported through the same ID-based path. Full physical-device testing is not established by these headless browser tests. The original trigger-focus failure was subsequently repaired; final browser assertions require the Select products button to receive focus after Add, Cancel, Escape, and native close. The same inspection confirmed a separate rendered email preview contains all three selected product titles. The browser regressions now also assert those titles in a non-composer preview frame after reopening.

## Additional composer checks

An expanded Python suite on both Streamlit 1.58.0 and 1.65.0, including composer presentation and component JSON checks, ran 37 tests: 31 passed and six environment-dependent tests were skipped. JavaScript syntax checking passed.

`test_crm_section_history.cjs` passed its 10 history checks. `test_crm_component_origin_ui.cjs` passed with the bundled Playwright packages available through `NODE_PATH`: restricted-origin handshake received without page errors. Its first invocation lacked the Node Playwright dependency; the successful rerun used the existing bundled dependency without repository installation.

`test_crm_sections_component.cjs` remains failing because its extracted VM snippet does not define `pendingCopyInputs`. The identical failure was reproduced against untouched HEAD composer source in scratch files, establishing that it predates this fix. This unrelated older test was not edited. Its initial mouse/sorting assertions passed before the failure.

## Reproduction commands

The application's existing launch command is `.venv\Scripts\python.exe sports_cave_server.py`, with `PORT` defaulting to 8501. Its startup includes storage preparation and service integrations, so it was not run against live configuration for this local-only investigation.

From the repository, the offline browser harness uses two terminals:

```powershell
$env:CRM_FIXTURE_SQL_PORT='8897'
node tests/crm_postgres_server.mjs
```

```powershell
$env:CRM_FIXTURE_SQL_PORT='8897'
# For production-version verification, set PYTHONPATH to the isolated
# Streamlit 1.65.0 installation; leave it unset for the existing 1.58.0 env.
.venv\Scripts\python.exe -m streamlit run tests/fixtures/crm_collection_picker.py --server.port 8546 --server.address 127.0.0.1 --server.headless true --global.developmentMode false
```

Then run, in a third terminal:

```powershell
$env:CRM_FIXTURE_SQL_PORT='8897'
$env:PICKER_URL='http://127.0.0.1:8546'
$env:PICKER_BROWSER='chrome' # repeat with msedge
$env:PICKER_WIDTH='320'     # repeat with 390 and 1440
.venv\Scripts\python.exe tests/check_crm_collection_picker_browser.py
.venv\Scripts\python.exe tests/check_crm_collection_picker_edges.py
.venv\Scripts\python.exe -m unittest tests.test_crm_picker_selection tests.test_crm_picker_performance tests.test_crm_modular_catalogue
```

The fixture requires the repository's existing PGlite fixture dependencies and Playwright browser integration. Both browser scripts block remote requests and operate only on synthetic drafts in loopback SQL. They do not use production credentials.