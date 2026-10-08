# Email workspace performance and usability

Implemented in the existing Campaigns, Automations and shared editor. No deployment,
customer emails, live publication, migration, new dependency, service or Render plan
change was performed. The existing unified Flow implementation and delivery engine
are retained. The application outside Email is unchanged.

## Findings and changes

- Campaign navigation invalidated all overview data even without a mutation. It now
  retains the bounded session cache; confirmed draft saves invalidate only rows and
  counts. Delivery/revenue summaries keep their own refresh lifecycle. Detached
  pending jobs are cancelled where possible and cannot replace newer results.
- Campaign route selection performed a redundant whole-script rerun. Known routes
  now render in the current pass. Separate stable overview/editor slots prevent
  stale page children from sharing a changing layout. Critical styles are emitted
  before either route.
- Browser recovery interrupted the composer before rendering its selected tab.
  Recovery now consumes widget events before emitting the component, returning the
  saved version and acknowledgement in the same render. Optimistic locking and
  recovery-copy protection remain intact. Native name/subject/preview callbacks
  persist blur events even when Settings is no longer the selected lazy tab.
- Audience and size polling continued targeting removed fragment IDs after their
  controls disappeared. Both now reuse the existing one-shot visible-control poll
  mechanism. It stops on unmount, pauses for open dialogs/popovers, and backs off
  audience polling when no refresh is pending. Sending eligibility remains a fresh
  backend decision, never a cached display count.
- Preview rendering redundantly loaded master defaults despite a saved email
  snapshot. It now uses the saved copy/resolved configuration without another read.
  Internal section labels no longer invalidate preview, thumbnail or size caches;
  HTML, order, visibility and other rendering changes still invalidate them.
- The size display reused rendered HTML but parsed it repeatedly every tick. It now
  caches analysis and only recalculates the asset report when metadata changes.
- Campaign Back, title, actual status, size, Save and send controls share one compact
  desktop toolbar. Controls wrap and the two-column composer stacks on small screens.
  The existing explicit send review/confirmation remains; opening a screen never sends.

Flow continues to use the current unified analytics/sequence/activity page, shared
step editor, independent metrics, lazy neutral thumbnails, published versions and
original historical records. See `AUTOMATION_UNIFIED_FLOW.md` for that implementation.

## Measurements

Local headless Chrome, real Streamlit UI and disposable SQL, 120 synthetic campaigns,
approximately 36 KB of HTML per measured email. External requests were blocked.
Baseline source was commit `2f6adbd`; current code was measured on the same machine
and fixture database. These are individual observed runs, not production percentiles.

| Campaign interaction | Before | After |
| --- | ---: | ---: |
| Cold editor open | 1,123 ms | 1,130 ms |
| Warm editor open | 585 ms | 377 ms |
| Warm return after editing | 293 ms | 237 ms |
| Warm open database reads | 4 | 3 |
| Four warm tab switches: database reads | 4 | 0 |
| Four tab switches: master-default reads | 4 | 0 |
| Return after editing: database reads | 4 | 2 |

Warm tab switches took 132–250 ms in the final normal run. No top-window long task
over 50 ms was observed during its typing sample. The preview iframe remained the
same DOM element across unrelated tab changes. No sampled giant icons or overlapping
overview/editor frames occurred in the before or after normal campaign runs; the
campaign test does not establish that those defects existed in its baseline.

With 4x CPU throttling, 150 ms network latency and 200 KB/s download, final editor
opening was 2,705 ms cold / 2,326 ms warm; return was 5,091 / 5,212 ms. Warm tab
switches were 272–1,660 ms. A cold typing sample recorded a 1,100 ms long task.
The baseline throttled workflow failed to complete return navigation, so no valid
before/after speed ratio is claimed for that condition. This remains a performance
limitation; the fast interaction targets are not met under that severe profile.

Current Flow measured 418 ms cold / 428 ms warm / 1,320 ms throttled to interactive
email controls. Its sampled frames had no overlap, giant icons, faded intermediate
content or JavaScript errors. This is a current measurement, not a new Flow speedup
attributable to this pass. Raw campaign results: `tmp/email-performance-*.json`.

## Verification and limits

- Final selected regression suite: 114 tests passed, with disposable SQL enabled.
  Earlier clean-database suite: 122 passed; additional final targeted suite: 66
  passed. These suites overlap and must not be added together.
- Browser passes: campaign create, rapid native field edits, HTML preview, save,
  schedule configuration without sending, duplicate, reload, desktop/mobile preview,
  widths 1440/750/390/320, no page overflow or JavaScript errors.
- Browser passes: unified Flow operations, correct-step editing, thumbnail update,
  12-step lazy rendering without per-step iframes, compact responsive layout;
  section rename/cancel/reset/duplicate/reorder/reopen in Campaigns and Automations;
  live/up-to-date, draft refresh, paused publication, resume and test controls.
- The broader 128-test run found four assertions requiring updates for the new
  toolbar signature/inactive route slot; those 11 loading/first-paint tests now pass.
  Two older assertions remain: `test_automation_only_polling_and_debounce` expects
  a removed source substring in unchanged `crm_section_ui.py`; and
  `test_ui_defaults_rerun_and_edits_persist_without_hidden_conversions` expects no
  saved `html_sections`, contrary to the existing independent template-copy model.
  These were not weakened to make this pass green. That run also skipped one test.
- Compilation, JavaScript syntax and whitespace checks were run. The offline
  production runtime/dependency/import build-contract tests pass. This Python/
  Streamlit repository has no root frontend build, lint or static-type-check command.
  No remote production dependency build or production load test was performed.
- Synthetic tests do not verify real Shopify response latency, real-provider delivery,
  multi-hour editing sessions or production browser/device percentiles. The fixture
  intentionally fails closed for unsupported live audience calls. Local Python is
  3.14; the declared production runtime stays 3.12.8.

## Files changed in this pass

Application: `crm_campaign_home.py`, `crm_campaign_home_data.py`,
`crm_campaign_page.py`, `crm_campaign_controls.py`, `crm_campaign_recovery.py`,
`crm_recovery_ui.py`, `crm_campaign_send_ui.py`, `crm_html_workspace.py`,
`crm_preview_cache.py`, `crm_email_size_ui.py`, `crm_flow_thumbnail.py`.

Tests: `tests/test_crm_email_optimisation.py`,
`tests/fixtures/crm_email_performance.py`, `tests/test_crm_email_performance_ui.cjs`,
`tests/test_crm_email_workflow_ui.cjs`, `tests/test_crm_campaign_home.py`,
`tests/test_crm_campaign_loading.py`, `tests/test_crm_campaign_first_paint.py`,
`tests/test_crm_campaign_history.py`, `tests/test_crm_email_size.py`.
The Flow browser regression also now scrolls the edited email into view before
checking its intentionally lazy thumbnail: `tests/test_crm_flow_page_ui.cjs`.

Some earlier changes were committed in the shared repository while verification was
running; they are preserved. Use the normal review/deployment workflow. No database
or scheduler configuration change is required for this pass.
