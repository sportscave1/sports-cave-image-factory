# Email Editor V6 — local implementation, measured results and release review

10 October 2026. **No V6 commit, push, merge, Render deployment, production editor mutation, production publication, scheduling change or real email send was performed.** All mutations and publication tests used disposable local fixtures. Production was not inspected during V6. LIVE email version 9 was not accessed or changed by this work; its production runtime has not been reverified.

## Baseline and working-copy protection

The implementation started from `a1a8cdab6f8213c1b393fd7923a124c0747d0bf2`, both actual HEAD and fetched `origin/main`, in the already-attached `codex/automation-live-stages` worktree. The primary working copy was at `b526c1d` with substantial unrelated changes. Those source files and its index were left intact. V6 is uncommitted in the isolated worktree; an exact, checksummed release archive supplies the manual release below.

The previous `docs/EMAIL_PERFORMANCE_V5.md` and deployed shared composer/render/save tests were reviewed first. The 305/359 ms warm opening, 823 ms first cold opening and 2–3 ms Hide figures in the request are **historical**, not new V6 measurements. A fresh opening baseline and backend restriction benchmark were collected before application edits. Later full-journey comparisons ran identical harnesses against an exported, untouched `a1a8cda` source tree and V6. No baseline was reconstructed by disabling V6 features inside the new code.

## Customisation audit and outcomes

| Area | Reproduced restriction or existing behaviour | V6 outcome |
| --- | --- | --- |
| Immediate Hide/Show, Move, Delete, Duplicate, Add | Already local-first at `a1a8cda` | **Already live and preserved.** Existing state, event batching, IDs and Undo remain. |
| Autosave, retries, stale responses and unsaved recovery | Already deployed | **Already live and preserved.** Failure/retry and out-of-order response browser tests pass. |
| Sibling Shopify offer context and hidden legacy HTML | Already fixed | **Already live and preserved.** 29 server/browser composition cases still agree. |
| Code-free discount creative | Amount-only, text-only and unfinished bound creative produced preview validation errors | **New in V6.** Drafts and previews accept code-only, amount-only, text-only, unbound and unfinished HTML. Delivery validation remains separate. |
| Hide/Delete disconnected the selected offer | `commit_middle` inferred selection from visible discount blocks | **New in V6.** Email association is independent. Connect/Change use verified server-side Shopify rows; Disconnect explicitly clears it. Deleting the final creative does not resurrect it on reopen. |
| Campaign discount presentation | Add Discount immediately required the checkout picker | **New in V6.** Both editors create an editable presentation locally. Actual recovery-offer application still requires an abandoned-checkout automation and its original recovery URL. |
| Template source | Reopening the library passed source through the send renderer, losing comments/classes/CSS; insertion flattened visible blocks | **New in V6.** Source remains authored text; structured templates retain hidden sections, types, order and settings. Inserted copies get fresh IDs. They cannot silently connect the template's old checkout offer. The library edits individual HTML sources without flattening other sections. |
| Styles | Inline allowlisted styles worked; simple class rules were dropped | **New in V6.** Newly added/edited sections opt into `css_version:1`: simple tag, class, ID, tag.class, tag#id and comma selectors are inlined on a rendering copy. Source is unchanged. Legacy sections, including immutable published snapshots, retain their original rendering rules. |
| Draft size | A roughly 95 KB authoring-source budget also rejected unfinished drafts | **New in V6.** Source budget is 1,000,000 UTF-8 bytes; document budget 2,000,000 bytes. The independent 95 KB rendered delivery guard is unchanged. |
| Rapid revert | Type, then revert before the 180 ms debounce: unchanged value left a pending draft entry and permanent Unsaved status | **New in V6.** The no-op clears that entry, restores current preview/status and sends no redundant save. Both browser engines verify it. |
| Active/unsupported content | Safe preview and send allowlists | **Blocked by genuine delivery safety.** Scripts, active elements, unsafe links and unsupported CSS cannot execute or escape the content wrapper. Source remains editable; nonblocking feedback explains exclusions. |
| False offer copy | Manually written amount/type claims cannot be verified | **Blocked by genuine delivery safety.** Drafts may retain them, but publishing/sending still rejects unsupported amounts, types, mismatched literal codes and unbound promotional claims. Use verified value/code variables for actual offer facts. This is a conservative rule set, not a semantic guarantee about arbitrary prose. |
| Advanced CSS | Media queries, descendant/pseudo selectors and arbitrary web CSS | **Still open.** Kept in source, not rendered. A style block containing an at-rule is currently ignored as a whole. Inline styles remain supported. |

Campaigns and Automations use the same composer, section model and safe preview contract. Recovery-checkout association is the only feature-specific distinction above. Header/footer defaults, consent, unsubscribe, suppression, duplicate prevention, checkout identity, tracking, immutable publication selection and worker scheduling were not redesigned.

## Measured bottlenecks and implemented speed changes

1. **Unneeded product media on the preview path.** Plain text drafts with a selected two-item checkout fetched two galleries even without lifestyle content and prepared banner fragments. V6 requests these only when the corresponding content needs them. With 75 ms simulated latency per gallery, the eliminated calls account for most of the cold improvement.
2. **Repeated whole-document copies for isolated sections.** Each section deep-copied every other section before replacing them. V6 copies only the shared context plus the current section. The warm 30-section result improves without changing the cache, save protocol or full-draft discount context.
3. **Rapid revert pending-state defect.** Fixed as a reliability issue, not counted as an opening speed improvement.

No extra architecture rewrite was justified. Already-fast local actions were measured and preserved. Normal template metadata remains cached; product/discount pickers and fresh delivery validation retain their existing lazy boundaries. Dynamic assets first introduced into a previously plain draft may need the next hydration/save acknowledgement before appearing; no claim of instantaneous remote-asset availability is made.

## Measurement method

Windows, the project's Python 3.14 virtual environment, Node 24, installed Chrome and Edge, Playwright, Streamlit and the existing loopback PGlite SQL fixture. Main browser requests outside the local fixture are blocked; Shopify/Resend operations are mocked. Tests use synthetic contacts/checkouts, never customer records. Publication workers operate only on local test data. Optional thumbnail prewarming is disabled in the Python regression/publication measurements to isolate delivery state and counters.

Measurements are **p50 / p95 milliseconds**, nearest-rank p95. With 12 samples, p95 is the maximum; six-sample control audits are particularly small and should not be treated as production tail estimates. Final performance comparisons ran without another regression/browser suite running. Functional matrix timings are separate Playwright tool-wall observations and are not used to claim a speed win.

Boundaries are intentionally separate:

- Local processing: synchronous component event handler and preview update; no network/persistence.
- Local frame: action to the next animation frame; frame cadence contributes about 16.7 ms.
- Typing preview: input event to visible preview text, including the 80 ms preview debounce.
- Browser opening: DOM click to visible fields or preview iframe attachment. Iframe attachment is not proof all remote images painted.
- SQL/backend: Python call boundaries including the local fixture bridge, not production PostgreSQL latency.
- Publication readiness: local request, worker tick and verified database readback; excludes UI polling and actual delivery.
- Picker services: real service code with 75 ms per synthetic provider call; does not claim click-to-product-insertion latency.

### Preview-model backend, identical three- and 30-section documents

| Context | a1a8cda p50 / p95 | V6 p50 / p95 | Gallery calls before → after |
| --- | --- | --- | --- |
| 3_cold_context | 158.09 / 164.94 | 6.86 / 13.18 | 24 → 0 |
| 3_warm_context | 1.93 / 2.17 | 1.97 / 2.23 | 2 → 0 |
| 30_cold_context | 218.72 / 232.61 | 50.49 / 51.89 | 24 → 0 |
| 30_warm_context | 7.14 / 8.81 | 3.54 / 3.75 | 2 → 0 |

Each row has 12 samples. Warm gallery counts include the single warm-up. Both versions use the same two-item pinned context and 75 ms gallery delay.

### Browser-local interactions

| Sections | Boundary | a1a8cda | V6 | Samples each |
| --- | --- | --- | --- | --- |
| 3 | hide_processing_ms | 1.30 / 2.70 | 1.25 / 2.50 | 12 |
| 3 | hide_frame_ms | 16.70 / 67.10 | 16.60 / 17.00 | 12 |
| 3 | move_frame_ms | 16.60 / 18.30 | 16.65 / 17.10 | 12 |
| 3 | typing_preview_ms | 97.15 / 100.10 | 94.85 / 100.10 | 8 |
| 3 | add_frame_ms | 16.70 / 16.80 | 16.55 / 16.70 | 12 |
| 3 | duplicate_frame_ms | 14.85 / 15.30 | 15.20 / 21.60 | 12 |
| 3 | delete_frame_ms | 16.65 / 16.80 | 16.60 / 16.70 | 12 |
| 3 | undo_frame_ms | 16.70 / 16.70 | 16.70 / 16.80 | 12 |
| 3 | template_insert_frame_ms | 15.20 / 15.40 | 15.05 / 15.40 | 12 |
| 3 | section_panel_frame_ms | 19.25 / 35.00 | 15.40 / 24.10 | 12 |
| 30 | hide_processing_ms | 1.70 / 3.40 | 1.65 / 3.10 | 12 |
| 30 | hide_frame_ms | 16.70 / 18.20 | 16.60 / 17.60 | 12 |
| 30 | move_frame_ms | 16.65 / 16.80 | 16.70 / 16.90 | 12 |
| 30 | typing_preview_ms | 97.10 / 100.60 | 96.95 / 100.90 | 8 |
| 30 | add_frame_ms | 13.95 / 16.70 | 16.60 / 22.70 | 12 |
| 30 | duplicate_frame_ms | 14.30 / 14.70 | 14.30 / 25.10 | 12 |
| 30 | delete_frame_ms | 16.70 / 16.80 | 16.70 / 16.90 | 12 |
| 30 | undo_frame_ms | 16.70 / 16.80 | 16.70 / 16.80 | 12 |
| 30 | template_insert_frame_ms | 14.20 / 14.60 | 14.35 / 14.60 | 12 |
| 30 | section_panel_frame_ms | 19.40 / 26.90 | 19.80 / 25.40 | 12 |

The typing input contains 800 repeated HTML paragraphs. Functional tests also repeatedly edited approximately 24 KB sections inside 30-section documents. Hide processing remains about 1–2 ms median: that is preservation of the deployed architecture, not a newly invented V6 speedup. Frame-level Add and Duplicate tails increased slightly in the 30-section run but remain far below 100 ms; no claimed improvement for these actions.

### Full Campaign opening / Send Test journey

This comparison adds an unsent Send Test open/close before returning to the list. It is a different interaction history from the initial baseline and historical V5 opening-only test. Both columns below use the same extended sequence, 12 fresh browser contexts, cold then warm opening per context; the last context is 390 px wide. Other contexts are 1440 px. No test email is submitted.

| Opening context | Boundary | a1a8cda | V6 |
| --- | --- | --- | --- |
| cold | firstUsefulMs | 814.75 / 847.00 | 828.55 / 849.30 |
| cold | previewReadyMs | 818.00 / 849.40 | 832.00 / 1057.00 |
| cold | editorTabMs | 221.40 / 344.70 | 232.15 / 365.40 |
| cold | previewSwitchMs | 106.55 / 170.00 | 117.90 / 154.30 |
| cold | templatesMs | 183.85 / 247.50 | 202.90 / 271.70 |
| cold | sendTestSetupMs | 257.55 / 414.20 | 249.90 / 421.40 |
| cold | backMs | 296.90 / 406.70 | 314.10 / 416.40 |
| cold | dbWaitMs | 34.91 / 216.21 | 17.71 / 234.46 |
| warm | firstUsefulMs | 384.75 / 840.10 | 401.05 / 836.90 |
| warm | previewReadyMs | 415.40 / 843.60 | 443.80 / 839.10 |
| warm | editorTabMs | 227.60 / 323.90 | 222.30 / 281.20 |
| warm | previewSwitchMs | 99.00 / 215.90 | 115.55 / 206.30 |
| warm | templatesMs | 146.95 / 232.60 | 196.35 / 220.40 |
| warm | sendTestSetupMs | 217.75 / 320.70 | 209.70 / 236.40 |
| warm | backMs | 292.75 / 509.40 | 286.60 / 355.40 |
| warm | dbWaitMs | 24.86 / 40.63 | 37.40 / 78.73 |

The fuller workflow **does not meet the 300 ms warm-opening median target**. Its median is slightly slower in V6 and both versions have roughly 0.8-second tail observations. Template-tab and device-switch medians also increase in this run; device-switch p95 exceeds 150 ms. These are recorded regressions/variance to investigate, not removed from the dataset. First-session cold fields are approximately 828 ms baseline / 849 ms V6; first preview iframe is slower in V6. The small sample does not establish a causal regression, and no V6 opening-speed win is claimed. The initial pre-edit baseline, without the extra Send Test lifecycle, remains in `email-v5-v6-baseline.json` for comparison rather than being mixed into these columns.

### Local save, validation and publication readiness

Twelve revisions of a synthetic abandoned-checkout flow; no send transport. Each revision is explicitly published only inside the disposable test database.

| Call boundary | a1a8cda | V6 |
| --- | --- | --- |
| reopen_database_ms | 3.26 / 19.08 | 2.68 / 19.57 |
| draft_save_database_ms | 6.14 / 31.16 | 4.59 / 24.48 |
| safe_preview_backend_ms | 3.44 / 13.36 | 3.37 / 10.92 |
| readiness_backend_ms | 2.99 / 5.65 | 2.87 / 5.41 |
| publish_request_database_ms | 13.56 / 35.08 | 14.14 / 40.37 |
| publication_worker_ms | 63.10 / 122.43 | 49.04 / 116.76 |
| publication_readback_database_ms | 3.21 / 3.89 | 2.51 / 16.28 |
| request_to_verified_local_live_ms | 81.66 / 150.66 | 71.07 / 144.49 |

These small local SQL differences are not claimed as production database or publication optimisations. Browser autosave still debounces persistence by 650 ms and does not block local editing.

### Product and discount service boundaries

| Boundary, 12 samples each | a1a8cda | V6 |
| --- | --- | --- |
| discount_search_cold_service_ms | 226.25 / 226.62 | 226.15 / 226.54 |
| discount_search_cached_service_ms | 0.03 / 0.03 | 0.02 / 0.04 |
| discount_apply_fresh_service_ms | 150.81 / 151.08 | 150.49 / 150.84 |
| product_collections_cold_service_ms | 75.47 / 78.08 | 75.40 / 76.25 |
| product_search_cold_service_ms | 75.39 / 75.83 | 75.38 / 75.74 |
| product_search_cached_service_ms | 0.04 / 0.04 | 0.04 / 0.11 |
| product_insert_fresh_service_ms | 75.60 / 88.51 | 75.46 / 85.84 |

Cold discount search makes three synthetic provider calls. Cached search makes no extra calls. Fresh offer application retains its scope/offer verification calls. Collection search and fresh product facts are measured separately; no Shopify latency improvement is claimed.

### Campaign control audit, six samples per version

| Playwright tool-wall boundary | a1a8cda | V6 |
| --- | --- | --- |
| page_to_list_tool_wall_ms | 1018.03 / 1607.21 | 1061.90 / 1580.35 |
| list_to_editor_shell_tool_wall_ms | 822.02 / 1649.85 | 1019.13 / 1116.66 |
| review_shell_tool_wall_ms | 294.91 / 399.49 | 251.13 / 414.28 |
| return_to_list_tool_wall_ms | 298.71 / 336.00 | 328.16 / 351.29 |
| different_email_open_tool_wall_ms | 583.49 / 1051.29 | 590.46 / 680.83 |

Page-to-list includes local fixture setup/seeding and is not an application-only cold-start number. Editor-shell timing waits for its tab, not final content paint. The V6 discount shell includes creating/saving independent creative and then Connect; the old Add Discount opened the picker directly. That changed action sequence is not a like-for-like speed comparison. Search-ready and selected-offer save boundaries are separately reported.

### Automation control audit, six samples per version

| Playwright tool-wall boundary | a1a8cda | V6 |
| --- | --- | --- |
| page_to_list_tool_wall_ms | 1038.61 / 1593.95 | 1110.08 / 1629.35 |
| list_to_editor_shell_tool_wall_ms | 298.36 / 420.49 | 333.21 / 391.31 |
| discount_picker_shell_tool_wall_ms | 202.30 / 239.04 | 1164.81 / 1620.97 |
| discount_search_ready_tool_wall_ms | 1188.30 / 1243.75 | 1180.51 / 1269.14 |
| discount_apply_and_save_tool_wall_ms | 210.39 / 299.65 | 201.04 / 264.39 |
| return_to_list_tool_wall_ms | 864.85 / 880.78 | 631.58 / 891.22 |
| different_email_open_tool_wall_ms | 335.63 / 362.54 | 320.62 / 901.83 |

Page-to-list includes local fixture setup/seeding and is not an application-only cold-start number. Editor-shell timing waits for its tab, not final content paint. The V6 discount shell includes creating/saving independent creative and then Connect; the old Add Discount opened the picker directly. That changed action sequence is not a like-for-like speed comparison. Search-ready and selected-offer save boundaries are separately reported.

## Complete journey audit: coverage and remaining gaps

| # | Operation | Evidence and boundary |
| --- | --- | --- |
| 1 | Open Campaigns | Control-audit page-to-list; includes fixture setup. Initial route-only production timing remains unverified. |
| 2 | Open campaign | Full opening table: visible fields, iframe attachment and SQL time. |
| 3 | Open Automations | Control-audit page-to-flow; synthetic flow seeding included. |
| 4 | Open automation email | Control-audit editor shell; matrix also checks real content. |
| 5 | Saved content load | Full opening and exact-source reopen browser checks. |
| 6 | First useful preview | Opening iframe boundary plus backend model; all-image paint remains unmeasured. |
| 7 | Switch emails | Six-sample different-email control audit. |
| 8 | Add section | Local-frame benchmark and real UI matrix. |
| 9 | Open HTML editor | Local section-panel benchmark and editor-tab DOM timing. |
| 10 | Type/update | Eight long-source samples for each 3/30-section case, plus browser matrix. |
| 11 | Hide/Show | Processing and frame timing, 12 samples per document size. |
| 12 | Move | Local frame timing; stable IDs/order asserted in real UI. |
| 13 | Duplicate/Delete | Local frame timing and UI persistence assertions. |
| 14 | Change/insert template | Local insertion and template-tab timings; structured-source insertion verified in Chrome/Edge and SQL. |
| 15 | Shopify product insertion | Fresh product facts/service timing and catalogue regression tests. Complete product-modal click-to-insert timing remains open. |
| 16 | Discount selector | Six-sample real local UI shell audit. |
| 17 | Discount search | Real local UI ready-result timing plus service cache/call-count benchmark. |
| 18 | Apply offer | UI selection-to-Saved timing plus fresh verification service timing. |
| 19 | Desktop/mobile | Full opening table and both browser engines at 1440/390 px. |
| 20 | Undo/recovery | Local frame timing, UI delete Undo, fault and source-contract checks. |
| 21 | Save draft | Local SQL acknowledgement; real autosave/failure/retry checks. Full network save latency is unverified. |
| 22 | Reopen | Local SQL and both-editor browser exact-source assertions. |
| 23 | Open review | Campaign control audit waits for review summary; never confirms dispatch. |
| 24 | Send Test setup | Full opening table, unsent dialog only. |
| 25 | Generate test preview | Backend safe preview and local publication output checks; actual customer-provider rendering unverified. |
| 26 | Validate | Readiness backend timing; separate delivery guard tests. |
| 27 | Publish automation | Disposable local worker and readback timing, immutable-before-publish assertions. UI polling is excluded. |
| 28 | Campaign readiness | Backend readiness plus local review shell; no real audience preparation/dispatch benchmark. |
| 29 | Return to list | Full opening and control-audit tables. |

The audit does not invent timings for the remaining full-UI product picker, remote image completion, production network, live audience or provider boundaries.

## Regression evidence

- Broad quiet run: **566 tests — 558 passed, seven reproduced baseline failures, one skipped**. The first concurrent run had two extra checkout timing failures; both passed when rerun without the browser workload. Raw performance comparisons use the quiet condition.
- Final focused run after the last source/template tests and stricter baseline classifier: **32 tests — 25 passed, seven exact baseline failures**. This overlaps the broad run; do not add the counts as unique tests. It includes single-catalogue template preservation, version conflicts and unsaved recovery from `tests.test_campaign_recovery`.
- Real shared editor: Campaigns and Automations, Chrome and Edge, 1440 and 390 px: **eight scenarios passed**, each exercising 3 and 30 sections, long HTML, code/amount/text/unfinished discount drafts, Hide/Move/Duplicate/Delete/Undo, save/reopen and zero send rows.
- Failed save, 1.5-second delayed retry, newer edits and replayed stale acknowledgement: **Chrome and Edge passed**. Newer local source and visibility survive reopening.
- **29** incremental browser/server composition cases passed, including sibling discounts, catalogue/product images and dynamic checkout content.
- Source contract in **both browsers passed**: rapid revert produces Saved, restores exact preview, sends no redundant persistence event; structured insertion preserves hidden source, types and fresh IDs.
- **Eight** visibility/menu keyboard/focus/dismissal scenarios passed. Its old test harness omitted the already-existing `renameControl` stub and also failed on untouched `a1a8cda`; only the fixture stub was repaired.
- V6 local publication tests passed for text-only and amount-only offer creative, retained offer metadata, original checkout URL, unsubscribe footer, exact source, old LIVE snapshot immutability before explicit local publication, and no provider send.
- Source beyond the old budget saves; oversized rendered output remains blocked. Active markup/link checks remain enforced. CSS opt-in tests prove unchanged legacy rendering after Hide/Show and an immutable published copy after source editing.
- JavaScript syntax, Git whitespace and Render topology validation passed. `render.yaml` and service identities are unchanged. No Blueprint sync was requested, so no Blueprint preview/apply was needed.

### Known failures — not V6 regressions

All seven were rerun unchanged on the exported `a1a8cda`: 27 baseline tests produced four assertion failures, three errors and one skip. The release gate still executes them, recognises only their recorded exception/message/source signatures, and reports expected failures. Any different failure or unexpected success stops the release; it is not a general ignore list.

1. `DiscountDeliveryTests.test_email_three_only_frozen_versions_tracking_and_no_duplicates`: old expectation for an enrolled frozen subject conflicts with the already-deployed current-LIVE selection; actual `New future version`, expected `Your offer: FIXTURE5`.
2. `SqlWorkspaceTests.test_empty_compose_creates_no_draft_and_initial_reads_are_bounded`: obsolete Campaigns markdown heading expectation.
3. `SqlWorkspaceTests.test_blank_new_canvas_no_blocks_and_preview_roundtrip`: obsolete iframe-srcdoc lookup (`A collector moment`).
4. `SqlWorkspaceTests.test_delete_confirmation_is_explicit_and_cancel_retains_draft`: obsolete `recent_delete_` button lookup.
5. `SqlWorkspaceTests.test_recent_open_uses_same_editor_and_protects_unsaved_compose`: obsolete `recent_open_` button lookup.
6. `TemplateCacheTests.test_failure_not_cached`: expects an empty list without the four existing built-in templates.
7. `TemplateCacheTests.test_metadata_shared_sorted_and_copied_without_bodies`: likewise omits existing built-ins.

The one skipped test is the named-fragment compatibility path on the installed Streamlit runtime; its native fallback is retained. Early browser harness failures caused by reused fixture rows, ambiguous duplicate text, diagnostic overlay, reopening the already-selected Editor tab, and an insecure synthetic origin were fixed in the fixtures and rerun. Failed baseline setup attempts missing exported static assets were excluded from timings.

## Reproduction and evidence

Raw samples are in `docs/email-editor-v6-evidence/`. Fixtures refuse busy ports and terminate only processes they own. They require the project's existing Python environment, Node/PGlite dependencies and installed Chrome/Edge. Set `NODE_PATH` to the existing Codex runtime dependency folder.

| Check | Entry point |
| --- | --- |
| Broad local release gate | `python scripts/run_email_reliability.py --modules tests.fixtures.email_v6_regression` |
| Final focused recheck | `python scripts/run_email_reliability.py --modules tests.fixtures.email_v6_final_checks` |
| Campaign browser matrix | `EMAIL_V6_MODE=campaign`, then `python scripts/run_email_v6_browser.py` |
| Automation/fault matrix | `EMAIL_V6_MODE=automation`, then `python scripts/run_email_v6_browser.py tests/test_crm_email_v6_ui.cjs tests/check_crm_editor_faults.cjs` |
| Composition/source contracts | `python -m tests.fixtures.build_local_editor_models`, then `node tests/check_crm_editor_composition.cjs` and `node tests/check_crm_email_v6_contract.cjs` |
| Backend preview benchmark | `EMAIL_V6_LABEL=after`, then `python -m tests.email_v6_audit` |
| Opening/Send Test | `EMAIL_V5_LABEL=v6-after-full`, `EMAIL_V6_MODE=campaign`, then browser runner with `tests/test_crm_email_v6_opening.cjs` |
| Remaining control audit | Set mode and `EMAIL_V6_LABEL`, then browser runner with `tests/test_crm_email_v6_controls_audit.cjs` |
| Local action comparison | `node tests/benchmark_email_v6_local.cjs` |
| Save/publication timing | `python scripts/run_email_reliability.py --modules tests.email_v6_journey` |
| Picker services | `python -m tests.email_v6_picker_audit` |

For the baseline export, use Git archive at the full `a1a8cda` SHA, including Python modules, tests, scripts, components, ui_components, prompts, templates, migrations and .streamlit. Copy only the V6 benchmark harness files into that export; do not copy modified application modules. Point its fixture node_modules junction at the existing test dependencies. The local-action benchmark expects this export at `tmp/v6-baseline-source`.

## Remaining performance roadmap

**Small follow-ups:** profile the post-Send-Test opening lifecycle and its 0.8-second tail; expand samples before attributing the modest opening/template/device regressions to code; instrument full product-modal click-to-insert and remote-image completion; add timing around background-save queueing separately from SQL acknowledgement. Refresh the seven obsolete baseline tests against the accepted current-LIVE and shared-editor contracts in a separate reviewed change.

**Larger work:** supported responsive/media CSS with a versioned renderer and cross-email-client fixtures; background hydration for a newly inserted dynamic asset before the next acknowledgement; reduce unavoidable Streamlit dialog/fragment round trips if measured bottlenecks justify it. Do not replace the working local draft or versioned persistence architecture for cosmetic parity.

## Production readiness and manual release

The first V6 implementation is locally verified, with the measured gaps and baseline failures above. **Production V6 readiness is unverified until the user performs the manual release and the existing services finish their rollout.** No new database migrations, dependencies, secrets, services or Render configuration are required. Optional `css_version:1` on edited sections and `discount_association_version:1` on draft documents are validated JSON fields. Existing records are not backfilled. The web app and existing sending worker must both run the same V6 revision before publishing new V6 documents; old published documents keep legacy rendering.

The canonical primary remains `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`). The release helper never syncs a Blueprint or creates/renames a service. A push to `main` uses the established repository auto-deploy topology; deployment health is not claimed by a successful push.

The accompanying `scripts/deploy_email_editor_v6.ps1`, release ZIP and SHA-256 sidecar are placed in the primary repository. The helper verifies every exact file against its manifest, fetches latest GitHub main, creates a separate temporary release checkout, and stops if main changed any V6 target file. It runs the local release gates, stages only manifest paths, checks main again, commits and performs a normal non-force push. The existing primary branch, staged changes, modified files and untracked work are not stashed, reset, merged or staged. Errors retain the release checkout for review. The ZIP and temporary directories themselves are never staged. Codex only validates the package with `-ValidateOnly`; the actual release is exclusively the user's manual action.

The final chat supplies one ready-to-paste PowerShell block invoking this helper from the repository root. No deployment command was executed during V6.
