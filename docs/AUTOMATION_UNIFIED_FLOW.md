# Unified Automation Flow

Implemented locally on 8 October 2026. No deployment, production publication,
customer send, schema migration, or scheduler change was performed.

## Interface and reuse

The overview's Flow menu and existing automation links open one normal page.
The analytics compatibility entry points route there too. The overview's six
cards, filters, table columns and recent activity are retained. The old analytics
dialog/content renderer, Flow Builder tabs/sequence renderer and duplicate
composer analytics toggle are removed. The Create dialog still selects a trigger;
it opens the same Flow page after creation.

Flow combines the existing publication toolbar, date-filtered overall metrics,
compact email rows, inline step settings, trigger settings and recent activity.
Step forms save drafts through the existing optimistic-revision store; they never
publish. The toolbar's Save draft is disabled when the current draft is saved.
The existing composer and its read-only preview handle editing and larger previews.
Returning from editing scrolls the selected step into view. The existing checkout
table and manual-enrolment controls remain available in a collapsed section.

Summary, step metrics and recent activity reuse the existing asynchronous read
cache. Recipient timelines, checkout lists, performance charts and full previews
are requested only when opened. Initial authoring data still comes from the
existing single draft JSON record; this change does not introduce a second schema
or strip documents out of the version comparison.

Thumbnails render the saved email document with neutral checkout sample data.
They are content-keyed, cached, loaded on intersection and isolated with Shadow
DOM. They do not mount editors or one iframe per email. Remote images are limited
to bounded Shopify CDN thumbnails; tracking URLs and arbitrary full-size remote
images are excluded. This deliberately conservative miniature renderer preserves
inline email styling, but does not execute scripts or arbitrary stylesheet rules.
The existing full preview remains available for inspecting the complete design.

## Metrics and history

Per-email metrics use immutable template-version step IDs, with frozen enrolment
step IDs as the fallback. They do not use the current draft ordering. Message
counts are distinct send IDs, so duplicate open/click events cannot inflate rates.
Sent means provider acceptance; delivered, opened, clicked and bounced require
their respective recorded events. Test sends are excluded.

Conversions and revenue use eligible order-attribution evidence for that specific
automation and step. Currencies are kept separate. Overall enrolments are counted
from enrolment records, independently of the number of messages. Historical or
removed step IDs remain visible separately; unidentifiable old evidence is never
silently assigned to a new Email 1. Per-email unsubscribe attribution is not in
the current ledger and is explicitly labelled unavailable.

Legacy non-native flows retain their prior conversion/editing restrictions and
history; their overall analytics remain accessible. No live legacy configuration
is converted automatically.

## Rendering cause and measured results

Streamlit coalesces `empty()` followed by `container()` at the same delta position.
That reused the overview block and retained its stale children during the new
page's read/render work. Keyed containers alone did not solve it. Separate stable
overview and Flow delta slots now clear the inactive subtree without replacing
it in the same run. The Flow route is a normal fragment, eliminating the previous
dialog lifecycle and opacity transitions. Critical overview styles remain at a
stable position while its subtree unmounts; icons retain intrinsic dimensions.

Local Chrome, 1440×1000, synthetic SQL and blocked external browser requests:

| Scenario | Old popup toolbar / interactive | Flow toolbar / interactive | Old overlap / faded frames | Flow overlap / faded frames |
|---|---:|---:|---:|---:|
| Cold navigation | 553 / 623 ms | 350 / 492 ms | 23 / 18 | 0 / 0 |
| Warm navigation | 440 / 440 ms | 365 / 469 ms | 24 / 19 | 0 / 0 |
| 150ms latency, 200KB/s download, 4× CPU throttle | 1236 / 1386 ms | 841 / 1000 ms | 33 / 7 | 0 / 0 |

These are individual local observations, not production percentiles. Cold means
a fresh browser context, not a newly started Python interpreter. Warm interactivity
was roughly comparable/slightly slower while rendering more information. No giant
icons or JavaScript errors occurred in either measured fixture. The historical
baseline loads the relevant modules from commit `edbeb70`; the new route uses the
working tree. Raw results: `tmp/flow-navigation-before.json` and
`tmp/flow-navigation-after.json`.

## Verification

- Broad relevant suite: 186 tests, 183 passed, three existing Campaign workspace
  assertions failed. All three were reproduced using committed automation modules:
  `test_delete_confirmation_is_explicit_and_cancel_retains_draft`,
  `test_recent_open_uses_same_editor_and_protects_unsaved_compose`, and
  `test_empty_compose_creates_no_draft_and_initial_reads_are_bounded` in
  `tests/test_crm_html_workspace.py`. They expect obsolete recent-campaign buttons
  or a Markdown heading. Those unrelated tests were not weakened.
- Subsequent focused suite: 65 passed; final retry/metrics/navigation/build-contract
  suite: 18 passed. These runs overlap; counts must not be added together.
- SQL fixture verifies 32 original sends, 11 unique opens and one click remain on
  the original step after reordering; Email 2 remains independent. It also verifies
  32 enrolments versus 33 messages, date filtering and per-step currency attribution.
- Browser passes: complete Flow operations, thumbnails and invalidation after edits,
  existing read-only preview, add/reorder/duplicate/disable/delete, 12 steps with
  deferred off-screen thumbnails and no per-step iframes, row/menu navigation,
  reload/bookmarks, repeated clicks, different flows, delayed and failed essential
  reads with retry, editor tabs, widths 1440/1000/750/390/320, no horizontal overflow.
- Browser passes: live/up-to-date, saved changes after reload, publishing version 2
  while paused, resume, test-email controls and Back; shared section rename/cancel/
  reset/duplicate/reorder/save/reopen in both Campaigns and Automations.
- Python compilation, JavaScript syntax, `git diff --check`, and offline Render
  dependency/runtime/import contracts passed. This Python/Streamlit application
  has no root frontend production-build, lint or static-type-check configuration.
  A remote Render dependency build was not run. Local Python was 3.14; production
  runtime remains the existing declared 3.12.8.

## Source files

New: `crm_flow_page.py`, `crm_flow_thumbnail.py`, `tests/test_crm_flow_page.py`,
`tests/test_crm_flow_page_ui.cjs`, and this document.

Updated application files: `crm_automation_ui.py`, `crm_automation_home.py`,
`crm_automation_toolbar.py`, `crm_flow_builder.py`, `crm_automation_analytics_ui.py`,
`crm_automation_home_data.py`, `crm_automation_analytics.py`,
`crm_checkout_analytics.py`.

Updated test fixtures: `tests/fixtures/crm_automation_preview.py`,
`tests/fixtures/crm_automation_navigation_baseline.py`.

Updated regression tests: `tests/test_crm_automation_navigation_ui.cjs`,
`tests/test_crm_automation_toolbar_ui.cjs`, `tests/test_crm_flow_builder_ui.cjs`,
`tests/test_crm_section_names_ui.cjs`, `tests/test_crm_automation_actions_ui.cjs`,
`tests/test_crm_automation_overview_metrics_ui.cjs`, `tests/test_crm_automation_ui.py`,
`tests/test_crm_checkout_analytics.py`. New screenshots are in `tmp/unified-flow-*`.

Deploy through the normal application workflow. No new migration, environment
variable, dependency, scheduled job or service is required. Existing publication
and delivery workers, consent checks and immutable enrolment versions are reused.
