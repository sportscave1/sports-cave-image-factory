# Campaign send flow — local implementation, 29 September 2026

## Root cause and result

The former top Send test button only set `show_test` and selected Campaign
Details. It never invoked a transport. Sending required finding a second form,
saving the draft, checking copy review and confirming there. This explains the
reported click/loading-without-send path; live provider credentials were not
tested or diagnosed in this task.

The top bar now contains Save draft, Send test and Send now. The Test accordion
and top Settings/More controls are removed. Draft management and New remain in
the existing left More section. Embedded Settings no longer renders its separate
diagnostic test-send form.

Send test opens one small email popover with autofocus. Enter or the arrow submits
the explicit manual test, validating a single email, admin permission, the
internal allowlist and existing content checks. The submission confirms copy
review, persists the exact current revision if needed, and invokes the existing
Stage 1 test transport. Sending feedback and safe errors are displayed locally.
The existing 15-second HTTP timeout, no redirects, durable operation receipt and
no automatic retry after uncertain submission are retained. Identical
content/recipient submissions reuse their operation identifier. Tests never enter
the production recipient queue or totals.

## Production review and safety

First Send now opens a compact modal and calculates fresh authoritative audience
counts. Nothing is queued by reviewing. Final confirmation rechecks the saved
revision, eligibility and content, freezes recipient IDs/hashes and a content/
configuration snapshot, and writes the existing `crm_campaigns`,
`crm_marketing_sends` and template-version records in one transaction. There is
no new schema or migration.

`CRM_MARKETING_ENABLED=false` rejects final confirmation before audience I/O or
queue writes: **Marketing delivery is currently OFF. No emails were sent.**
The existing secondary `CRM_MARKETING_SEND_ENABLED` gate also remains required.
The existing worker consumes the new immutable snapshot format, revalidates
Shopify consent, suppressions and Smart Sending, and uses the existing provider,
unsubscribe signing, leases and submission-idempotency handling. Internal
delivery snapshots are excluded from author-facing template selectors. Legacy
campaign/automation formats retain their existing branch.

The shared audience evaluator's decisions are unchanged; its optional recipient
output exposes only the customers that passed those same checks. No fallback to
all customers exists. Conflicting consent, invalid emails, suppression and
duplicate-address rules remain in force. Changed recipient addresses are blocked
at worker time. Catalogue facts must still match the reviewed draft snapshot.

A draft lock plus one production campaign identity per draft prevents a repeated
confirmation, including one with a new request UUID, from queueing a second
broadcast. Recipient uniqueness constraints and existing provider idempotency
remain. Duplicate a campaign to prepare a separate future broadcast.

Future activation is **not** just flipping the master flag. Previously
hardcoded readiness checks now have explicit default-false attestations at this
new production boundary: `CRM_ONE_CLICK_UNSUBSCRIBE_VERIFIED`,
`CRM_DMARC_VERIFIED`, `CRM_RESEND_WEBHOOKS_VERIFIED`,
`CRM_BROADCAST_VERIFIED`, and comma-separated `CRM_MARKET_REVIEW_VERIFIED`
(explicit markets, such as AU). Existing verified identity/domain/address,
provider configuration, HTTPS public base and unsubscribe secret checks also
apply. These values must only be set after actual verification and authorization.
A running existing CRM worker is required. No production configuration or worker
deployment was changed here.

Production rendering uses the shared renderer with a signed unsubscribe URL;
only system TEST labels and owned `sc_test` tracking markers are removed. Preview
and test HTML continue using the same existing output and footer.

## Loading and persistence

Save draft retains the existing full document persistence and uses an editor
fragment rerun to refresh saved state, with compact Draft saved feedback.
Campaign settings is now a collapsed bottom expander. Its settings panel and
settings-only reads run only after expansion. Regression tests prove zero panel
calls on initial render and ordinary subject editing, then one on expansion.
Baseline rendering already conditionally opened settings; no unmeasured startup
speedup is claimed. Required renderer configuration still loads normally.
Audience review is explicit, with a bounded 30-second page-loop budget in
addition to existing network timeouts; it never runs for ordinary typing or
preview-size changes. Test transport is confined to its fragment submission.

## Files changed

- `crm_campaign_send.py`: shared explicit test/review/queue boundary.
- `crm_campaign_send_ui.py`: popover, review dialog and deferred settings.
- `crm_campaign_page.py`: three actions, removal of duplicate controls, save rerun.
- `crm_settings_page.py`: compact embedded settings without a second test action.
- `crm_audience.py`: optional eligible recipient identities, unchanged decisions.
- `crm_campaign_content.py`: production mode using the shared rendering pipeline.
- `crm_engine.py`: immutable Campaign composer snapshot in the existing worker.
- `crm_store.py`, `crm_workspace_store.py`: hide delivery snapshots from templates.
- `tests/test_crm_send_flow.py`: 13 focused regression cases.
- `tests/test_crm_brand_templates.py`, `tests/test_email_navigation.py`: bottom
  settings expansion expectations, preserving existing form/persistence checks.
- This report and `docs/campaign-send-flow-evidence/` screenshots.

## Verification

All database/transport tests used disposable local SQL and mocked external I/O.

| Check | Result |
| --- | --- |
| CRM discovery, including rendering, templates, audience and flows | 224 passed |
| Focused send flow + Email navigation + navigation performance + sidebar cleanup | 48 passed (overlaps above) |
| Email discovery | 144 run, 143 passed, 1 existing skip |
| Support Email discovery | 212 passed |
| Startup scope regressions | 6 passed |
| Editor shell + section JavaScript | 21 scenarios passed in 2 test files |
| Compilation | 12 affected Python files passed |
| `git diff --check` | Passed |

The enabled-path SQL test queues once and exercises the real worker with a mocked
provider. Other tests cover allowlisting/admin restrictions, exact test HTML,
timeout sanitization, repeat-submission protection, changed/empty audience,
marketing-OFF zero jobs, review-only behavior, UI success/error feedback and lazy
settings. AppTest does not reliably drive the dialog's fragment rerun; final OFF
confirmation was additionally exercised in the actual browser.

Browser verification used the actual local OS Campaign page with synthetic
customers/products, blocked live transports and marketing OFF, at its normal
1280×720 viewport. Verified autofocus, Enter validation, review counts, final OFF
error, settings expansion/collapse and retained preview/layout. Screenshots:
`campaign-send-flow-evidence/test-popover.jpg` and
`campaign-send-flow-evidence/review-marketing-off.jpg`.

No real email was sent. No Shopify or Edition Ops data was modified. Marketing
remains OFF; no environment files, production data or migrations were changed.
Nothing was committed, pushed or deployed. Ready for Nathan's local review;
real provider acceptance and production activation remain unverified/unapproved.
