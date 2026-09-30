# Email / CRM initial-load performance pass

Local implementation, 30 September 2026. No commit, push, deployment, schema
change or live email/campaign/automation/business-data mutation was performed.
All exercised providers and database writes belonged to fabricated test fixtures.

## Findings and changes

| Page | Blocking work found | Change |
| --- | --- | --- |
| Inbox | Settings, folder discovery and the header/snippet fetch ran before the desktop component was emitted. | Emit the existing component first with lightweight loading feedback. Its acknowledged initial-load event then fetches the selected folder; the existing separate body event loads the auto-selected message afterward. |
| Campaigns | Sending/branding/compliance settings, recovery and selected composer rendering preceded the recent-campaign list. Hidden Editor tab content also executed. | Stream the shell, issue the existing metadata-only list query first, and populate the composer in its existing position. Execute Editor content only when its tab is open. Explicit Save reruns so the earlier-rendered list reflects the save. |
| Automations | The selected email loaded on entry; the collapsed workflow configuration queried every template body to build a name selector. | Stream the header before reads, retain selected-email behavior, and load workflow configuration only on expansion. Its query now selects template keys rather than full content. |

The existing automatic opening/restoration of the selected campaign/flow editor
is intentionally preserved. Only that selected editor is loaded; this pass does
not replace the existing workspaces with new list-only landing pages.

Inbox uses the existing event acknowledgement ledger to prevent duplicate initial
loads. An attempted initial load is recorded, including unconfigured/error states,
so it cannot cause a reload loop. Folder contents, bodies, attachments and CID
images retain their existing on-demand behavior. Preview snippets remain bounded.
Refresh still reaches the provider and existing invalidation remains in effect.

No new long-lived data cache, authentication cache, credentials, schema or client
was introduced. Existing mailbox LRU/session caches, provider connection reuse,
CRM caches and composer fragments remain. No change was needed to connection
initialization. Hidden panels now avoid work rather than caching stale results.
The page dispatch still loads only the selected subsection.

Stage logging covers shell emission, CRM list queries/rendering and selected
detail reads. Existing Inbox list, body and MIME/sanitization timings remain.
Logs contain durations and stage labels, not message content or credentials.

## Measurements

These are individual **synthetic local measurements**, not production claims or
an SLA. Baseline functions were read from the repository's unchanged HEAD and
executed against the same fabricated providers. Import/cache warm-up can affect
these samples, particularly the CRM timings.

* Inbox with an injected 500 ms header-fetch delay: first component emission
  **662.4 ms before / 4.5 ms after**; header requests before emission **1 / 0**.
  This measures server-side emission, not end-to-end browser paint.
* CRM with an injected 20 ms per read-only query: campaign list query began at
  **1256.0 / 172.0 ms**; sampled page queries **12 / 11**.
* Automation list query began at **234.0 / 131.6 ms**; sampled page queries
  **9 / 6**, and full template-library reads **1 / 0**.
* Initial import inspection: `crm_page` approximately 452 ms including its
  dependencies; `support_email_page` approximately 65 ms afterward. This did
  not justify a broad import refactor.

Remaining latency is provider/database response time and the intentionally
preserved selected-editor restoration. Production latency was not measured.

## Validation

* Support Email: **219 passed**.
* CRM: **326 passed, 1 skipped** using isolated loopback PGlite.
* Other Email tests, including new stage contracts: **159 passed**.
* All **9 Email JavaScript check scripts passed**.
* Changed Python files compiled; JavaScript syntax and `git diff --check` passed.
* Tests assert first-shell zero mailbox I/O, list/body separation, idempotence,
  current-folder-only loading, real refresh, early metadata queries, deferred
  hidden panels and selected-editor availability.
* Existing HTML/CID rendering, send/draft/signature, recovery, consent/suppression,
  campaign-save and automation-activation safeguards remain covered.
* Updated stale expectations for the existing HTTPS image CSP, Settings tab label,
  autosave behavior and reply-prompt DOM dependency in the Trash test harness.
  The autosave expectation was also checked against the baseline implementation.
* Offline browser fixture checked all three pages at **1440×900 and 1920×1080**,
  Home/subsection navigation, return to Inbox, automatic selected-body loading,
  and configuration expansion. No console errors or page-level horizontal
  overflow detected. This fixture is not a production-auth/network speed test.

## Files

Production:
`support_email_page.py`, `support_email_workspace.py`,
`components/support_email/mail.js`, `email_loading.py`, `crm_page.py`,
`crm_campaign_page.py`, `crm_flow_editor.py`.

Tests/fixture:
`tests/test_email_initial_load.py`, `tests/fixtures/email_initial_load_preview.py`,
`tests/test_support_email.py`, `tests/test_crm_ui.py`,
`tests/test_crm_campaign_sections.py`, `tests/test_email_loading_performance.py`,
`tests/test_email_reader_component.cjs`, `tests/test_support_email_signatures.py`,
`tests/test_email_navigation.py`, `tests/test_email_trash_component.cjs`.

Report: `docs/EMAIL_INITIAL_LOAD_PERFORMANCE.md`.
