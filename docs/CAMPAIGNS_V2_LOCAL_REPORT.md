# Campaigns V2 — local implementation and verification

## Result

The editor now has **Campaign Settings | HTML | Templates**. The entire bottom infrastructure/settings panel is removed from Campaigns. Campaign Settings contains only name, subject, preview text, Market and Send timing. Audience, Templates, More and Test accordions are absent. The existing top Save draft / Send test / Send now controls remain.

Header, footer, catalogue rendering, preview sizes and approved internal test transport are retained. No customer email or internal test email was sent during this work.

## Backend defaults

The existing `crm_campaign_content.settings()` and `WorkspaceRecords.render_settings()` remain the configuration source. Verified stored configuration wins; empty stored website/privacy/contact values no longer erase the defaults or configured reply-to.

- Website: `https://www.sportscaveshop.com`
- Privacy: `https://www.sportscaveshop.com/policies/privacy-policy`
- Refund policy: `https://www.sportscaveshop.com/policies/refund-policy`
- Contact/sender/reply-to continue using existing configured values. No mailbox or verification is invented.

These URLs are repository backend defaults, not production database writes. Refund is available to rendering configuration without adding another visual footer link. Existing unsubscribe, consent, suppression, domain/readiness and frequency checks remain enforced.

## Markets and counts

| UI | Canonical country | Audience |
|---|---|---|
| AU | AU | Eligible subscribed profiles with Australian default address |
| USA | US | Eligible subscribed profiles with US default address |
| UK | GB | Eligible subscribed profiles with UK default address |
| GLOBAL | Any | All eligible subscribed profiles, deduplicated across countries |

Historical country names normalize to canonical codes. Counts and final send preparation call the same market calculation. One paginated Shopify-authority pass supports all four counts. All profiles are checked for conflicting consent; only eligible profiles enter the recipient result. Existing `evaluate_profiles()` applies email validity, explicit subscription, suppressions, conflict handling, deduplication and recent-send frequency protection. No independent customer database is created.

The composer retains aggregate counts for 120 seconds per session/frequency setting; keystrokes and viewport switches reuse them. Final review and final queue preparation always calculate fresh results. Counts failures show an em dash and a restrained status while retaining edits. Existing network timeouts and a between-page calculation budget remain; external-service latency has not been benchmarked live.

The browser's **synthetic fixture** showed AU **12**, USA **13**, UK **11**, GLOBAL **36**. These are test values, not live subscriber totals. No live customer lookup was performed.

## Persistent Templates

The existing `crm_templates` and `crm_template_versions` tables store name, HTML snapshot, versions and timestamps. The library uses the existing `campaign_blocks_v1` representation; no new storage architecture or table is added. Shared Header/Footer and delivery snapshots are excluded, as are templates referenced by Automations.

Create, edit/rename, soft-delete and Use are available in the third tab. Template data is queried only when this tab or the HTML template picker is requested. Add section now offers HTML, Catalogue and Template. A template fills an empty first HTML section, otherwise it is inserted as a new numbered HTML section. Existing meaningful HTML is never overwritten. Campaigns keep their own source snapshot and become dirty until Save draft. Editing/archiving a library item cannot change previously saved campaign HTML.

## Recent campaigns and deletion

Recent campaigns remain below the editor. Each draft row has a small left trash icon, with confirmation. Cancel does nothing. Deletion soft-archives the unsent draft and preserves all revisions and audit records. Queued/scheduled/sent campaigns, test receipts, delivery references and compliance/attribution references are protected at the database operation boundary. History, duplicate and archive/restore are compact row actions, not a More accordion in the editor.

## Scheduling

`send_timing` is an optional field in the existing campaign document. Old documents default to immediate sending. Saving a draft persists mode/date/local time without creating delivery jobs.

On an authorised final production confirmation (only when both existing delivery gates and readiness checks pass), the same queue transaction freezes eligible recipients and an immutable delivery snapshot. Each existing `crm_marketing_sends` row receives a UTC `due_at`. The versioned template snapshot stores each recipient hash's timezone, resolution reason and original due instant. The existing leased CRM worker dispatches due jobs and revalidates current consent, suppression, email identity, market and frequency. There is no browser timer or second delivery system.

Timezone priority:

1. Valid Shopify mailing-address `timeZone`, or existing explicit timezone.
2. Deterministic known postcode/state mapping (including Broken Hill).
3. GB uses Europe/London. Country fallback is Australia/Sydney for AU and America/New_York for US.
4. Other/unresolved countries use UTC and record `global_utc_fallback`. Valid subscribers are not excluded for missing timezone precision.

The state mapping covers Sydney, Brisbane, Adelaide, Perth, New York, Chicago, Denver and Los Angeles. Split-zone US states without explicit address timezone use the documented fallback rather than claiming precise geographic resolution. No geocoding service is called. Address fields were schema-validated using the Shopify Admin skill; primary reference: [Shopify MailingAddress](https://shopify.dev/docs/api/admin-graphql/latest/objects/MailingAddress).

Python `ZoneInfo` handles daylight saving; `tzdata` is now an explicit dependency for Windows as well as server runtimes. For **5 October 2026, 07:00 local**, tests prove:

| Recipient zone | UTC due instant |
|---|---|
| Sydney | 4 Oct 20:00 |
| Brisbane | 4 Oct 21:00 |
| Adelaide | 4 Oct 20:30 |
| Perth | 4 Oct 23:00 |
| New York | 5 Oct 11:00 |
| Chicago | 5 Oct 12:00 |
| Denver | 5 Oct 13:00 |
| Los Angeles | 5 Oct 14:00 |
| London | 5 Oct 06:00 |

Nonexistent spring-forward local times are rejected; ambiguous fall-back times use the first occurrence. These decisions are explicit and regression-tested.

## Marketing OFF and missed schedules

`CRM_MARKETING_ENABLED=false` was not changed. Immediate and scheduled final confirmations are blocked before production queue creation while OFF. An already-queued schedule reaching its due time while OFF is persistently BLOCKED. Enabling later changes its reason to `schedule_missed`; it never becomes PENDING again automatically. Future buckets remain eligible.

A persistent worker checkpoint also prevents catch-up after an unobserved OFF period/restart. A worker outage over five minutes, or a job more than five minutes past its original snapshot due time, fails closed as missed. This conservative delivery window can require rescheduling if worker capacity or service availability is inadequate; it deliberately avoids surprise catch-up delivery. Recent campaigns display the blocked/missed reason. Rescheduling requires a reviewed new draft; the old send/audit remains immutable.

Existing backend Smart Sending (normally 16 hours) remains separate from local-time scheduling and is not editable in this composer. Existing recipient idempotency keys, campaign row lock, immutable snapshot and no-replay handling after uncertain provider submission remain in force.

## Files changed in this task

- `crm_campaign_page.py`, `crm_campaign_controls.py`, `crm_campaign_send_ui.py`: compact tabs, market/timing controls, removed settings, review and recent draft actions.
- `crm_campaign_library.py`, `crm_workspace_store.py`: persistent HTML library and backend default handling.
- `crm_campaign_markets.py`, `crm_shopify.py`: canonical market eligibility and address facts.
- `crm_campaign_schedule.py`, `crm_campaign_send.py`, `crm_engine.py`: recipient-local due times and persistent kill-switch/missed-schedule handling.
- `crm_campaign_content.py`, `crm_campaign_store.py`: compatible document validation/defaults and safe deletion/read-only queued drafts.
- `crm_html_workspace.py`, `crm_section_ui.py`, `components/crm_sections/index.html`: Add Template integration.
- `requirements.txt`: explicit IANA timezone data dependency.
- `tests/test_crm_campaign_v2.py`: market, scheduling, library, safety and UI regressions.
- Updated obsolete UI expectations in `test_crm_brand_templates.py`, `test_crm_campaign_sections.py`, `test_crm_html_workspace.py`, `test_crm_send_flow.py`, `test_crm_ui.py`, `test_email_navigation.py`.
- This report and `docs/campaign-v2-evidence/` screenshots.

## Validation

All SQL tests used disposable loopback PostgreSQL/PGlite. Provider sends were mocked; browser harness blocks production database, SMTP, IMAP and Shopify API requests.

| Check | Result |
|---|---|
| CRM/Campaign/Flow/template/rendering suite | 242 passed |
| Email suite | 143 passed, 1 existing skip (144 run) |
| Support Email suite | 212 passed |
| Email navigation + navigation performance + sidebar | 35 passed |
| Startup | 6 passed |
| Editor JavaScript | 21 scenarios passed in 2 files |
| Python compilation | 21 affected/new Python files passed |
| Git whitespace | `git diff --check` passed |
| Shopify address GraphQL schema validation | Passed |

Navigation and startup were run in separate processes because importing the startup harness alongside AppTest contaminates Streamlit's form context. Both isolated suites passed. No application workaround was added for that harness interaction.

Browser checks used the actual local OS shell and Campaigns UI at **1440×900** and **1920×1080**. Verified market labels/counts, Schedule fields, Templates creation and insertion, preserved existing sections, draft save, Desktop/Mobile preview, final OFF confirmation, and Cancel/confirm draft deletion. No horizontal overflow at 1920. Screenshots: `settings-schedule-1440.jpg`, `templates-1920.jpg`, `schedule-mobile-1920.jpg`.

## Handoff

No database migration is required and none was applied to production. Safe for Nathan to test locally. Live sending remains deliberately disabled and still requires existing production readiness approval/configuration.

I did not commit, push or deploy. Repository HEAD changed externally to `ef24466` during the work; that commit includes some early backend additions from this task. I preserved it and left subsequent changes uncommitted. Review the full task file list above, not only the remaining working-tree diff.
