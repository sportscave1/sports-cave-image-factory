# Recovery links and editable email layouts V2

Local implementation only. No commit, push, deployment, live automation publication, customer email, Shopify write, or Edition Ops mutation was performed.

## Using the editor

In an automation email's **Editor**, choose **Add section → Visual element** or **Flexible checkout template**. Existing native checkout sections have an explicit **Separate checkout elements** action. Nothing is converted merely by opening an email.

Each visual element uses the existing eye toggle, drag handle / Alt+Up or Down, rename, duplicate, delete and delete-undo controls. Open an element to change its content or action; expand **Appearance** for alignment, font size/weight, colours, border, padding and spacing. Images also have a proportional width control. Text blocks support multiple lines.

Elements include headline, text/story, button, custom image, checkout product image, lifestyle image, edition, product name, frame/variant, dimensions, quantity, price, grouped details, divider and spacing. Static elements also work in non-checkout automations. Recipient-derived elements require the abandoned-checkout trigger.

Buttons and images offer Recover Checkout, See It On Your Wall, Product Page, Custom HTTPS URL and No Link. Product/lifestyle images default to recovery. Checkout item **0** repeats for all items; a positive number selects the corresponding checkout line. Repeated individual facts identify their product explicitly. Lifestyle positions use the existing Shopify gallery positions 2–4.

Edition labels are independent: hide/delete them or move them anywhere in the section order. Plain, badge and collector presentations are supported. A pre-purchase label says **NEXT AVAILABLE EDITION**, never that it is reserved. Missing/ambiguous edition facts are omitted; known limits can display a truthful limited-edition label. No allocation, cursor, sold-count, certificate or reservation writes were added.

## Root causes and implementation

The former native renderer bundled edition, image, title, variant, quantity, price, divider and CTA into one non-editable product block. Master-template validation also required one native marker and every `sc-cart-*` CSS class. The master loader reintroduced missing style rules on read.

The implementation retains the existing JSON document, section editor, autosave, publication snapshots, delivery engine, sanitizer and tracker. It adds a typed `checkout_element` section, resolves it on a render copy, and leaves the saved design authoritative. Simple surrounding legacy copy becomes separate visual text elements only during explicit separation. Rich HTML is retained as HTML rather than silently flattening its links or images.

Legacy native sections and `<!--SC_ABANDONED_CHECKOUT-->` remain supported. A master may instead use recovery-token anchors without a native product block or required styling classes. Publication requires a visible recovery action, not an edition, image or fixed layout. The former 20-section cap is removed; existing document and final-email size limits still apply.

## One recovery destination

Use `SC_CHECKOUT_RECOVERY_URL` as the complete `href`, for example:

```html
<a href="SC_CHECKOUT_RECOVERY_URL">Claim Your Edition</a>
<a href="SC_CHECKOUT_RECOVERY_URL"><img src="SC_LIFESTYLE_IMAGE_3_URL" alt="Your selected artwork"></a>
```

There is no new checkout API or URL-construction mechanism. The delivery engine still freshly verifies checkout/recipient identity and purchase/eligibility state. The renderer takes that checkout's original URL and, when configured, the existing discount verifier's approved final URL. It shares that destination across native and authored actions, preserving query bytes, fragment, checkout identity and discount parameters.

After final HTML sanitization and tracking, the renderer checks recovery-link count and exact destination equality. Missing context, changed destination, nested anchors, misplaced placeholders or a missing actual recovery action hold delivery. Custom customer checkout URLs cannot bypass the recovery action: new publication rejects pasted checkout destinations; test/sample rendering disables them. Test/sample token actions become non-clickable spans while retaining their copy and images.

Native product images now use the same recovery destination. Recovery-only emails skip product pagination and Edition Ops lookup; product layouts retain full authoritative line-item validation. Hidden elements are omitted from the rendered HTML, including their spacing.

## Preview, persistence and performance

Preview and live delivery share the visual renderer, sanitizer and tracking code. Preview uses the existing selected-checkout cache; it is never live-send authority. Approved offer wording and discount links use the existing discount integration. Repeated lifestyle blocks reuse a gallery lookup per product during one hydration and the existing short-lived Shopify metadata cache.

The editor uses its existing keyed cards, fragment reruns and autosave. Appearance expansion, section opening and unchanged values do not write drafts. Text changes are debounced; structural actions flush pending text/settings before duplication or movement. Visibility and movement give local feedback immediately.

Measured locally with synthetic checkout data and blocked external I/O (not production/network benchmarks):

| Operation | Measured time |
|---|---:|
| HEAD legacy two-product hydrate + render | 4.076 ms |
| Working-tree legacy hydrate + render | 4.814 ms |
| Full composable layout | 6.982 ms |
| Minimal headline + recovery CTA | 2.256 ms |
| Cached preview output | 0.028 ms |
| Browser: explicit separation | 142 ms |
| Browser: hide acknowledgement | 198 ms |
| Eight unchanged editor opens | 213–292 ms |
| Editor tab switches | 72–268 ms |

Additional validation adds a small CPU cost to the legacy render; this is not a claim that every render is faster. Cached interaction remains lightweight. Eight open/tab/preview/close cycles kept the exact SQL configuration and revision unchanged (2 → 2). The fixture retained one Shopify checkout preview request while editing.

Reproduce render measurements with `.venv/Scripts/python.exe tests/recovery_elements_benchmark.py --baseline` and without `--baseline`. The baseline loader reads tracked HEAD source into an isolated Python process; it does not reset or modify the working tree.

## Verification

New tests cover repeated recovery actions (240 links), exact query/fragment/discount preservation, native and custom image links, nested links, corrupt final destinations, missing context, disabled samples/tests, pasted customer URLs, minimal publication, hidden/deleted/restored fields, styling and size, multiple products, gallery reuse, no rendering-time allocation, static non-checkout layouts, pending-edit duplication, saved/frozen versions, actual mocked provider output and duplicate-send prevention.

Browser verification covers 1440, 1024 and 390 px viewports; local layout editing, independent copy, edition visibility/styles, duplication/reordering, unchanged reopen, and no horizontal page overflow. Existing Email Performance V4, discount selector and durable publication browser suites also passed. These are browser and email-markup checks, not real Gmail/Outlook inbox delivery tests.

Edition Ops allocation, ledger, version and cursor suites: **94 tests passed** using disposable SQL.

The initial focused CRM run: **274 of 275 passed**, with the remaining campaign-default assertion independently reproduced using unchanged HEAD source. Final complete CRM suite: **1,175 tests in 128.434 s: 1,152 passed, 22 failed/errored, 1 skipped**. All **21 new tests passed**, including disposable SQL publication/frozen-journey/provider tests.

Read-only HEAD (`9b188df`) comparison: **1,154 tests in 119.333 s: 1,131 passed, the same 22 failed/errored, 1 skipped**. The final failure-name sets are identical; there are **no additional failing cases** in the final run. The older failures concern audience-sync fixture APIs, obsolete UI/footer/template expectations, schema manifest expectations, and a shared-database campaign bounce-cohort assertion. They are not suppressed or relabelled as passing. The full-suite baseline name list is included below.

Two timing/order-sensitive cases (paused-journey millisecond comparison and campaign dispatch acknowledgement) failed in an intermediate run and passed in the final full run; they are not claimed as deterministic regressions or silently counted as passes from the intermediate run.

`git diff --check`, Python compilation and JavaScript syntax checks also passed.

## Changed files

- Rendering and validation: `crm_recovery_links.py`, `crm_checkout_elements.py`, `crm_abandoned_checkout.py`, `crm_middle_sections.py`, `crm_checkout_template.py`, `crm_checkout_preview.py`.
- Existing automation integration: `crm_automation_runtime.py`, `crm_automation_store.py`, `crm_automation_preview_cache.py`, `crm_recovery_discount.py`, `crm_engine.py`.
- Existing visual editor: `crm_section_ui.py`, `components/crm_sections/{index.html,composer.js,visual.js,style.css}`.
- Tests and fixtures: `tests/test_crm_recovery_elements.py`, `tests/test_crm_recovery_elements_ui.cjs`, `tests/recovery_elements_benchmark.py`, `tests/fixtures/crm_automation_preview.py`, updated `tests/test_crm_checkout_details.py`, `tests/test_crm_checkout_progress.py`, `tests/test_crm_checkout_template_styles.py`, `tests/test_crm_frame_banner.py`, `tests/test_crm_lifestyle_images.py`, `tests/test_crm_native_automations.py` and `tests/test_crm_wall_preview_template.py` for the new recovery-action and truthful-label rules.
- This report and `docs/EMAIL_RECOVERY_LINKS_V2_RESULTS.json`.

## Limits and rollout requirements

- Complex authored HTML remains editable in the HTML editor. Explicit separation converts simple text safely; it does not attempt a lossy arbitrary HTML-to-visual round trip.
- Visual blocks use email-safe stacked tables, not a freeform canvas. Adjacent collector layouts can still be authored with the existing HTML editor. There is no invented edition reservation or guaranteed discount eligibility.
- All actions remain subject to the existing final 95 KiB email limit and document size bound. Missing optional product/gallery/edition facts are omitted; absence of the last recovery action prevents a new send.
- No schema migration, permission change, theme update or data backfill is required. Deploy compatible editor **and delivery-worker code together** before publishing designs using the new section type/token. Existing stored publications and customer journeys are not rewritten.
- Nothing has been deployed or published to production. A later authorized rollout should include a controlled internal inbox/client check before publishing revised automation content.

## Existing full-suite failures reproduced against HEAD

- `tests.test_crm_ui.UiTests.test_automation_activation_fails_closed`
- `tests.test_crm_automation_preview_stability.PreviewStabilityTests.test_automation_only_polling_and_debounce`
- `tests.test_crm_campaign_cleanup.DeletionSQLTests.test_bounce_cohort_deduplicates_verified_events_excludes_tests_and_old_sends`
- `tests.test_crm_html_workspace.SqlWorkspaceTests.test_delete_confirmation_is_explicit_and_cancel_retains_draft`
- `tests.test_crm_audience_sync.AudienceSyncTests.test_deleted_linked_segment_fails_closed_retains_stale`
- `tests.test_crm_email_defaults.EmailDefaultsTests.test_edits_update_draft_render_not_draft_or_historical_snapshot`
- `tests.test_crm_html_workspace.SqlWorkspaceTests.test_empty_compose_creates_no_draft_and_initial_reads_are_bounded`
- `tests.test_crm_storage_recovery.SchemaRecoveryTests.test_empty_list_and_healthy_settings_render`
- `tests.test_crm_template_picker.TemplateCacheTests.test_failure_not_cached`
- `tests.test_crm_single_footer.FooterStorageTests.test_internal_test_uses_global_footer_production_render_and_never_resends`
- `tests.test_crm_audience_sync.AudienceSyncTests.test_location_transfer_and_no_double_count`
- `tests.test_crm_test_preflight_issues.TestPreflightIssues.test_locked_assets_have_attribution_not_body_misattribution`
- `tests.test_crm_storage_recovery.RecoveryTests.test_manifest_is_reviewed_and_check_never_connects`
- `tests.test_crm_template_picker.TemplateCacheTests.test_metadata_shared_sorted_and_copied_without_bodies`
- `tests.test_crm_email_defaults.EmailDefaultsTests.test_mocked_test_payload_uses_latest_defaults_and_native_link`
- `tests.test_crm_storage_recovery.RecoveryTests.test_outage_keeps_navigation_and_blocks_creating`
- `tests.test_crm_html_workspace.SqlWorkspaceTests.test_recent_open_uses_same_editor_and_protects_unsaved_compose`
- `tests.test_crm_audience_sync.AudienceSyncTests.test_segment_query_change_and_rename_preserve_id`
- `tests.test_crm_audience_sync.AudienceSyncTests.test_subscribe_and_unsubscribe_refresh_au_and_global_only`
- `tests.test_crm_audience_sync.AudienceSyncTests.test_tag_add_remove_with_no_address`
- `tests.test_crm_campaign_sections.SectionPersistenceTests.test_ui_defaults_rerun_and_edits_persist_without_hidden_conversions`
- `tests.test_crm_email_defaults.EmailDefaultsTests.test_ui_has_only_global_edit_actions_and_preserves_body`
