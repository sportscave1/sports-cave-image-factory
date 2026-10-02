# Email Automations V1 — implementation and local validation

Implemented locally on 2026-10-03. No production database, Shopify, Resend, Render, environment or Git publication changes were made.

## Audit and reuse

The old route used crm_flow_editor.flow_workspace and an Automation-specific raw HTML authoring surface. Existing crm_automations, crm_automation_enrollments, crm_marketing_sends, crm_template_versions and webhook/event ledgers already provide durable definitions, journeys, leases and individual Resend submission. V1 adds a native definition format around those existing entities.

The actual composer is crm_campaign_page.composer_form(mode='automation', settings_control=...). Settings / Editor / Templates, Catalogue, Images, shared header/footer, sanitizer, preview/device toggle and template library remain the same code. AutomationStore adapts draft persistence to a selected automation email; it never creates a Campaign draft. crm_email_editor_context explicitly separates the two session editors. Shared Send test uses the existing production renderer, admin transport, receipt/idempotency/rate protection and event reconciliation.

Home reuses Campaign STYLE, KPI markup/icons, the bounded shared read pool/cache and single refresh controller. Definitions/counts, delivery metrics and attributed orders load independently. Table queries return metadata and aggregates for one selected page (12 rows + pagination sentinel). Status/search/filter/sort changes fetch only their table slice. Cache identities are automation-session-owned; definitions invalidate counts/table only. Last-good summary values survive pending/error/incomplete/stale responses. One controller refreshes at 20 seconds when resolved and briefly at 250ms to collect in-flight results; hidden tabs back off. Delivery/orders use a shared rolling UTC 30-day window refreshed every 20 seconds with stable cache keys so the window can advance without blanking cards. No listing read fetches customers or email bodies.

## Supported sources and settings

- Welcome: the existing signed customers_email_marketing_consent/update ledger event, checked against fresh Shopify SUBSCRIBED consent and a matching consentUpdatedAt timestamp. A customers/create event alone does not enroll historic subscribers.
- Post-purchase: existing signed orders events plus a fresh non-cancelled fullyPaid Shopify order/customer. The order creation must be after activation; no historical order backfill.
- Abandoned checkout: existing authoritative abandonedCheckouts query, filtered created_at >= activation. One paginated page per bounded reconcile; pagination must advance. V1 considers an incomplete checkout after one hour and adds the selected first-email delay to that deterministic boundary. The customer must remain marketing eligible. Missing/inaccessible checkout authority holds the flow and logs only failure type/IDs.

No fulfilled-order, generic follow-up or winback trigger is advertised as newly operational. UI offers only the registry above. Rules are deliberately limited to exact Market is AU/NZ/US/UK/CA rows combined with AND; consent, valid address and trigger exit checks are mandatory, not optional rules. Re-entry is once ever, or 7/30/90 days after the prior entry. Delays are stored as integer seconds (0 means immediately); the UI edits minutes. No artificial small email-count cap exists.

## Publication, flow and safety

Draft flow lives in crm_automations.config.draft under an optimistic revision. Publish locks that definition, validates every shared document, reviewed copy, render/sender/tracking configuration and the existing 95 KiB HTML boundary. It freezes automation_delivery_v1 content in existing template version storage and activates future entry policy. Internal publication snapshots are excluded from the one global reusable Email Templates library. Publishing inserts no journeys or sends.

Entry locks the parent automation, requires an event at/after activation, checks fresh consent/suppression/rules, serializes re-entry, and copies the whole published step list into crm_automation_enrollments. Source identities remain unique across publications. That frozen list owns order, step IDs, delays, trigger/rules and template versions; editing/re-publishing never changes an existing journey.

Email 1: trigger boundary + first delay -> existing enqueue -> existing individual Engine.send_one -> durable ACCEPTED receipt. Email 2: accepted receipt time + second delay -> same process. Unique journey/step and provider idempotency keys prevent replay. Pending state is persisted, so browser closure and worker replacement do not control progress. Uncertain submissions keep the existing no-automatic-replay policy.

Before every actual email: fresh Shopify consent/recipient identity, local and provider suppression, native Shopify unsubscribe URL, frozen trigger/rules, current checkout/order eligibility, current local suppression again, existing smart-sending policy, production rendering and size guard. A recovered checkout or newer order exits abandonment; blocked or uncertain executions stop remaining steps. Existing lease and Resend permissions remain authoritative. No marketing flag is enabled by this code.

Pause blocks new entries and unsent submission claims. A claimed email is returned to pending instead of becoming a failure; a due-query/pause race does not stop the journey. Resume shifts pending due times by the pause duration, retaining remaining wait and resetting entry cutoff to avoid paused-event backfill. Publishing a paused flow applies the same shift. A provider request whose durable submission claim preceded Pause can finish; already accepted requests cannot be recalled.

Archive requires Draft/Paused. Delete is a tombstone, permitted for Draft/Archived only. It removes the definition from normal Home/counts while preserving template versions, journeys, executions, events and attribution. Legacy live flow runtime/history is retained and shown read-only; supported unused legacy drafts may be explicitly converted. There are no competing live authoring surfaces.

## Analytics and attribution

Active = ACTIVE visible automation definitions. Sent = non-test ACCEPTED individual sends in the shared UTC 30-day cohort. Bounce = distinct cohort messages with canonical email.bounced events in that window / accepted messages; zero denominator is unknown. Click average = mean per-automation delivered-and-clicked / delivered rate from the same verified event ledger. Orders = eligible crm_order_attribution records with automation identity in canonical evidence and order date in the window. No Revenue appears.

Home table shows Entered, Sent, real Delivered/Opened/Clicked, Orders and lifecycle status. Step analytics load only on demand. Resend callbacks join the same individual provider receipt/event reconciliation. Automated email tracking uses existing campaign/link decoration with an auto_<send UUID> key and deterministic tracking send UUID. Accepted automation messages become candidates in the same crm_campaign_attribution.choose algorithm, competing with Campaign candidates in the existing window rather than introducing a second attribution algorithm. Evidence carries automation/version/journey/step/send/provider identity. Campaign-only foreign keys stay NULL for automation matches; attribution rows/history are retained. Mirror configuration is not enabled or altered.

Logs contain automation/version/trigger/source/journey/step IDs, due/submission timestamps, provider message ID, status and duration/failure categories; no customer addresses, names, unsubscribe URLs or content.

## Migration

migrations/20261002132200_crm_native_automations_v1.sql is registered with a reviewed checksum in run_migrations.py. It adds nullable automation_id/automation_step_id to the shared internal test audit, makes campaign_id nullable with an exclusive source CHECK, and adds three narrow reporting/re-entry indexes. Existing records remain valid. No new exposed customer mirror or parallel send table is created. Existing RLS and server-only permissions remain unchanged. Deployment schema verification requires the new columns/indexes and continues to fail closed. The migration was applied only to disposable loopback PGlite, not a connected Supabase database.

## Validation

- 80 production/batch/Resend regressions passed: test_crm_batch_dispatch, test_crm_production_v2, test_crm_production_style_test, test_crm_resend_marketing.
- 122 shared send/editor/first-paint/tracking/unsubscribe/template/size/catalogue/core regressions passed on a fresh local database: test_crm_send_flow, test_crm_campaign_first_paint, test_crm_tracking_hardening, test_crm_production_unsubscribe, test_crm_brand_templates, test_crm_email_size, test_crm_simple_editor, test_crm_catalogue_presentation, test_crm.
- 77 automation/Home/cache/migration/attribution-recovery tests passed: test_crm_native_automations, test_crm_automation_ui, test_crm_campaign_home_cache, test_crm_campaign_home, test_migration_connections, test_crm_attribution_health_recovery. The native suite includes 25 tests; shared UI ownership/cache/selected-tab tests include five.
- Playwright loopback-only Home and editor checks passed at 1920, 1366, 750, 390 and 320px: five KPIs; no horizontal overflow; compact visible trash control; same Settings/Editor/Templates/preview; no Campaign Segment. Cancel delete retains its row. Add duplicate and blank emails open Email 2/3 correctly. External requests were blocked.
- Python compilation of 28 changed Python files, reviewed migration checksum/safety and git diff --check passed.
- Three existing test_crm_html_workspace expectations fail both here and with pristine HEAD modules: obsolete recent_delete_/recent_open_ controls and the retired list-first Campaigns heading. These are pre-existing tests, not passing validation. The other seven tests pass. Shared database fixtures need isolation: accumulating unrelated pending opt-outs can exceed existing bounded worker batches; affected suites pass on a fresh fixture.

Screenshots under docs/performance-evidence/automation-{home,editor}-{width}.png are synthetic local-fixture evidence, not production analytics or measurements of Shopify latency.

## Connected-environment limits

No live latency, provider delivery, Shopify capability/scopes, signed webhook registration or production SQL performance was tested. Deployment must apply the migration before the new route/worker contract runs. Confirm actual consent/order webhook subscriptions, abandoned-checkout API access, existing native unsubscribe and delivery configuration in the connected environment. Unsupported/missing authority fails closed. Do not turn on marketing to validate this code automatically. Existing external automation overlaps have not been assessed or changed.

This is locally validated implementation ready for deployment review; it is not a claim of verified production operation.

## Exact changed-file manifest

- `crm_automation_attribution.py`
- `crm_automation_definition.py`
- `crm_automation_home_data.py`
- `crm_automation_runtime.py`
- `crm_automation_store.py`
- `crm_automation_ui.py`
- `crm_campaign_attribution.py`
- `crm_campaign_home.py`
- `crm_campaign_page.py`
- `crm_campaign_recovery.py`
- `crm_campaign_send.py`
- `crm_campaign_send_ui.py`
- `crm_campaign_store.py`
- `crm_email_editor_context.py`
- `crm_email_size_ui.py`
- `crm_engine.py`
- `crm_navigation.py`
- `crm_page.py`
- `crm_resend_marketing.py`
- `crm_schema.py`
- `crm_section_ui.py`
- `crm_store.py`
- `crm_workspace_store.py`
- `docs/performance-evidence/automation-editor-1366.png`
- `docs/performance-evidence/automation-editor-1920.png`
- `docs/performance-evidence/automation-editor-320.png`
- `docs/performance-evidence/automation-editor-390.png`
- `docs/performance-evidence/automation-editor-750.png`
- `docs/performance-evidence/automation-home-1366.png`
- `docs/performance-evidence/automation-home-1920.png`
- `docs/performance-evidence/automation-home-320.png`
- `docs/performance-evidence/automation-home-390.png`
- `docs/performance-evidence/automation-home-750.png`
- `migrations/20261002132200_crm_native_automations_v1.sql`
- `run_migrations.py`
- `tests/crm_postgres_server.mjs`
- `tests/fixtures/crm_automation_preview.py`
- `tests/test_crm_attribution_health_recovery.py`
- `tests/test_crm_automation_ui.cjs`
- `tests/test_crm_automation_ui.py`
- `tests/test_crm_native_automations.py`
- `docs/CRM_AUTOMATIONS_V1.md`
