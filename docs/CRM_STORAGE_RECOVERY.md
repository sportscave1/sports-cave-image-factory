# CRM storage recovery verification (28 September 2026)

Schema contract: 19 server-only tables, 183 columns and 17 explicit indexes.

Tables and exact columns verified after applying the three migrations:

- `crm_automation_enrollments`: `automation_id`, `created_at`, `current_step`, `id`, `last_checked_at`, `next_due_at`, `shopify_customer_id`, `status`, `steps`, `stop_reason`, `trigger_at`, `trigger_key`, `trigger_shopify_id`, `updated_at`.
- `crm_automations`: `activated_at`, `automation_key`, `config`, `id`, `name`, `status`, `steps`, `trigger_type`, `updated_at`.
- `crm_campaign_drafts`: `archived_at`, `created_at`, `created_by`, `document`, `id`, `last_test_resend_id`, `last_tested_at`, `name`, `status`, `tested_version`, `updated_at`, `version`.
- `crm_campaign_history`: `action`, `actor`, `after_value`, `before_value`, `campaign_id`, `created_at`, `id`, `version`.
- `crm_campaigns`: `created_at`, `id`, `name`, `recipient_cursor`, `resume_status`, `scheduled_at`, `segment_definition_id`, `shopify_segment_id`, `snapshot_at`, `status`, `template_id`, `template_version`, `updated_at`.
- `crm_delivery_events`: `event_id`, `event_type`, `hard_bounce`, `occurred_at`, `provider_id`, `received_at`, `send_id`, `test_id`.
- `crm_internal_tests`: `accepted_at`, `actor`, `campaign_id`, `campaign_version`, `created_at`, `error_category`, `id`, `provider_id`, `recipient`, `render_hash`, `sender`, `status`.
- `crm_marketing_events`: `created_at`, `event_id`, `event_type`, `link_host`, `occurred_at`, `provider_email_id`, `recipient_hash`.
- `crm_marketing_sends`: `attempts`, `campaign_id`, `created_at`, `due_at`, `enrollment_id`, `error_code`, `first_submitted_at`, `id`, `idempotency_key`, `lease_token`, `lease_until`, `provider_email_id`, `recipient_hash`, `request_hash`, `shopify_customer_id`, `status`, `step_index`, `template_id`, `template_version`, `test_recipient`, `test_send`, `updated_at`.
- `crm_order_attribution`: `amount`, `campaign_id`, `campaign_key`, `checked_at`, `currency`, `eligible`, `model`, `order_created_at`, `shopify_order_id`, `visit_at`.
- `crm_runtime_state`: `key`, `updated_at`, `value`.
- `crm_segment_definitions`: `created_by`, `id`, `name`, `rules`, `system_key`, `updated_at`.
- `crm_settings_history`: `actor`, `created_at`, `id`, `key`, `value`, `version`.
- `crm_suppressions`: `active`, `campaign_reference`, `created_at`, `email_for_provider`, `provider_reference`, `provider_synced`, `reason`, `recipient_hash`, `shopify_customer_id`, `shopify_sync_attempts`, `shopify_sync_checked_at`, `shopify_sync_error`, `shopify_sync_state`, `source`, `updated_at`.
- `crm_template_versions`: `content`, `created_at`, `template_id`, `version`.
- `crm_templates`: `archived_at`, `content`, `id`, `kind`, `name`, `template_key`, `updated_at`, `version`.
- `crm_webhook_events`: `attempts`, `error_code`, `event_id`, `lease_token`, `lease_until`, `object_id`, `occurred_at`, `processed_at`, `provider`, `received_at`, `related_customer_id`, `status`, `topic`.
- `crm_website_events`: `campaign_key`, `event_id`, `event_type`, `occurred_at`, `product_ref`, `received_at`, `session_ref`, `test_context`.
- `crm_workspace_settings`: `key`, `updated_at`, `updated_by`, `value`, `version`.

## Applied database change

Confirmed the canonical Render service `sports-cave-os` (`srv-d8kl4on7f7vs73dvavv0`)
uses project `ceyzbfpuwuuxaiqwiltz`, database `postgres`, schema `public`, through
`aws-1-ap-southeast-2.pooler.supabase.com`. Before recovery there were no CRM
relations in any schema and no CRM entries in `public.schema_migrations`.
The targeted repository runner applied only:

1. `20260927093818_crm_marketing_v1.sql`
2. `20260928020740_crm_campaign_workspace_v1.sql`
3. `20260928024722_crm_campaigns_first_workspace.sql`

All three ledger entries and the contract above were verified independently after
commit, then the targeted runner was repeated to verify safe no-op behavior.
All 19 tables have RLS; public/anon/authenticated have no table grants. No SQL
functions were added. No existing data was dropped, truncated, reset or deleted.

## Root cause and local code fix

The existing Render pre-deploy command applies only the repair-request migration.
The normal application startup also runs a SHA-reviewed migration manifest, but
that manifest excluded all three CRM files. Deploying the new UI therefore never
created its storage. Campaigns caught the missing settings-table query and
returned before displaying any authoring controls. Settings was independently
filtered out of navigation because it was not worker-assignable.

The three reviewed migrations now participate in the established startup manifest;
`--crm` targets only CRM and `--verify-crm-schema` is read-only. DDL and ledger
updates share a transaction and advisory lock. The two newer SQL files tolerate
safe replay; version normalization only updates legacy spellings. No page-render
DDL or new database was introduced. The Settings route uses existing permissions.
Outages retain CRM navigation and a diagnostic shell; create/save is not presented
as successful while storage is unavailable, and session drafts are retained.

## Real-data verification

The full local `app.py` ran on loopback with the confirmed database and existing
Shopify configuration. Nathan's normal sign-in was used; no authentication bypass
or fabricated customer/product fixtures were used in this browser verification.
No Resend delivery keys were provided to the local verification app; marketing was
forced off. Real Shopify customer browsing, audience pagination and product search
worked without Shopify mutations. Eligibility remained explicitly partial until
all pages are scanned; no fabricated complete audience count was displayed.

The harmless draft `CRM storage verification â€” 28 Sep 2026` was created through the
UI, reloaded, edited, reopened after an app restart and saved through revision 4.
The independent duplicate was archived (revision 2); the original remains DRAFT
for inspection. Database history records creation, edits, content changes,
duplication and archiving. The built-in Initialize draft library action created
four existing Flow definitions, all DRAFT, plus their existing template/segment
configuration. Nothing was activated. Settings renders its existing sections.

Campaigns, Flows and Settings were inspected at 1440Ã—900 and 1920Ã—1080; the real
email layout preview was checked at 320, 375, 430 and 600 pixels (actual iframe widths verified). The yellow
marketing-disabled banner remains on Campaigns. No live campaign action exists.

## Tests

- CRM and storage-recovery suites: 127 passed, using explicit loopback SQL fixtures
  and mocked external services. Includes failed-migration rollback, ledger replay,
  missing schema, safe diagnostics, unavailable-page navigation, empty state,
  Settings permissions and persisted draft lifecycle.
- Email / support mailbox suites: 285 passed (73 Email + 212 support Email).
- Navigation/startup suites: 34 passed.
- Accounts / migration / Orders / Edition UI regression group: 253 run, 251 passed.
  Two pre-existing source-text assertions fail in
  `tests.test_orders_loading_ui.EditionOpsUiTests`:
  `test_mockups_prompt_cards_use_compact_modal_prompt_actions` and
  `test_product_uploads_shows_only_selected_embedded_product_prompt`.
  Both inspect `app.py`, which is byte-for-byte unchanged from HEAD in this task.
  Unrelated product/mockup code and expectations were not modified.
- All changed Python sources compile; `git diff --check` passes.
- All three CRM migrations applied twice successfully in fresh local PGlite.

## Safety and deployment status

Render's marketing flag was confirmed false and never edited. Independent database
checks after verification showed zero production send records, zero internal-test
records, zero active automations and zero suppression records. No customer email,
internal test email or real campaign was sent. Shopify consent, suppressions,
orders and the support mailbox were not modified. No commit, push or code deployment
was performed. The database repair is already applied; the navigation and outage
handling code awaits Nathan's separate deployment approval.

Known operational prerequisites remain intentionally unchanged: business postal
identity, internal-test allowlists and future live unsubscribe/delivery readiness
must be configured/reviewed separately. Schema availability does not enable sending.

## Files changed

`crm_campaign_page.py`, `crm_page.py`, `crm_settings_page.py`, `crm_store.py`,
`crm_schema.py`, `os_accounts.py` (CRM Settings navigation only), `run_migrations.py`,
the three CRM migrations above, `tests/test_crm_storage_recovery.py`,
`tests/test_crm_resend_marketing.py`, `docs/CRM_CAMPAIGNS_FIRST.md`, and this report.

The deployed CRM URL was opened after migration but required a fresh sign-in in
the verification browser. Live browser rendering was therefore not independently
confirmed; the completed visual checks used the full local app and actual live
database. The deployed sidebar still needs the pending navigation code deployment.
