# Send now review overlay — local validation

## Cause and fix

The Send now widget belonged to the entire `campaign_workspace` fragment rather
than the small action control. Its event replayed workspace rendering: emit the
Campaigns loading shell (including a 780px minimum editor placeholder), render
history, reload selected-detail settings, redraw the composer, then invoke the
dialog. `review_dialog` then synchronously called `review()` before drawing its
summary. Cancel called an app-wide `st.rerun()`.

Send now now owns a small fragment. Opening it never calls `campaign_workspace`,
history, the composer or the page loading shell. The native dialog first emits
draft summary, timing, send tracking identity and the existing cached preview.
Its finalization fragment shows `Finalizing audience…`, with confirmation disabled.
No page-mode/history/editor selection transition is used.

A session-owned job takes an immutable copy of the draft. If required, it saves
the pending checkpoint once using the existing optimistic-save helper. It then
calls the unchanged authoritative `review()` workflow: Shopify membership/consent,
suppression and deduplication, production readiness, tracking validation, schedule
validation and the existing durable snapshot transaction. No Resend request occurs.
Only timing instrumentation was added to that backend review function.

An identical in-flight review is reused. A successful result can be reused for
30 seconds from job start when the exact draft identity/version/content matches.
Other changes or expired/failed reviews require a new calculation. Final send
still performs all existing fresh consent/suppression/version/configuration checks;
the displayed count is never used as send authority. Four concurrent review jobs
are allowed per process; extra requests fail visibly and can be retried.

Only the finalization fragment polls its future, using a one-shot native widget
event after 200ms. It stops on ready/error/dismiss; it never polls Shopify itself.
Errors remain in the dialog, and Retry starts only finalization. Confirmation
requires no blockers, a real snapshot, a saved campaign and marketing enabled.
The same `queue_campaign()` and operation identity remain in use. A full lifecycle
page update occurs only after the existing durable queue transaction succeeds.

Cancel delegates to the native X button on the client; X/Escape use Streamlit's
`on_dismiss='ignore'`. A narrowly scoped Cancel listener prevents a server event.
There is no global Streamlit patch or scroll restoration workaround. The native
editor DOM stays in place. A 240px internal review-result area keeps confirmation
buttons stationary when counts/errors arrive; the modal is bounded to 92vh.

The composer remembers its effective preview settings (including current shared
header/footer defaults), so the review reuses the same `crm_preview_cache` entry.
Production HTML still undergoes the existing tracking validation; that safety
render is intentionally not replaced with a preview cache.

## Measurements

All measurements are offline, using the real Campaigns UI and disposable local
PostgreSQL with fabricated Shopify customers. The fixture adds exactly three
seconds to finalization and prohibits external HTTP/production database access.
They are not production latency promises.

- Original: dialog title appeared at 182ms, but usable summary and audience
  arrived at **3,207ms**. A Campaigns skeleton was observed.
- Updated fresh review at 1280×900: title **87ms**, populated summary **136ms**,
  audience ready **3,243ms**. No skeleton. A repeat open was **125ms**, ready included.
- Updated fresh review at 1440×900: title **111ms**, populated summary **170ms**,
  audience ready **3,170ms**. At 1920×1080: title **109ms**, populated summary
  **161ms**, audience ready **3,104ms**. Both retained the exact scroll offset
  and showed no history skeleton.
- Backend finalization remains roughly the same authoritative work; the win is
  immediate interaction and removal of unrelated workspace work, not skipped checks.
- Example actual server stage logs: modal shell **3.2ms**; already-saved draft
  handling **0.0ms**; authoritative audience **36.0ms**; suppression lookup **2.3ms**;
  recent-marketing exclusions **29.9ms**; render settings **0.1ms**; production
  validation **1.0ms**; tracking validation **1.7ms**. Shopify fixture calls were
  **0.0–0.1ms** (mocked, not representative network timings).
- Snapshot creation measured **3.8ms** in the enabled offline setup. The marketing-
  disabled browser fixture correctly creates no snapshot (**0ms** stage).
- No draft reload or count-only Shopify request is needed to open the modal.
  Already-saved content incurs no save transaction. Cached preview lookup and
  shell emission are included in the modal-shell timing above.
- Browser click-to-server receipt cannot be separated exactly from network and
  rendering without synchronized client/server instrumentation. The measured
  click-to-dialog/summary values include that round trip; no invented split is used.

## Checks and limitations

Browser checks at 1920×1080, 1440×900 and 1280×900 used a scrolled editor.
Opening, count completion, Cancel, X and reopening retained the exact main-scroll
offset (505.333px at 1080px height, 595.333px at 900px height in the fixture).
The page-render counter remained 1 and no loading skeleton was observed on the
fixed path. Existing background history/count freshness timers remain unchanged;
opening the review does not trigger them. Internal preview/result scrolling keeps
the buttons accessible. No console errors in the clean final browser session.

407 CRM tests passed, one skipped, against disposable PostgreSQL. Focused tests
cover asynchronous readiness, coalescing, save ordering, failed review/retry,
editable-field preservation, format/segment/timing identity, gating and scope.
Existing SQL tests cover snapshots, current consent, exclusions and send lifecycle.
The JavaScript test executes the actual inline scripts repeatedly and verifies
native Cancel, suppression of the server click and stopped polling after dismissal.
Python compilation and `git diff --check` pass.

Changed production files:

- `crm_campaign_page.py` — isolated Send now entrypoint.
- `crm_campaign_send_ui.py` — immediate dialog, local finalization, native dismissal.
- `crm_campaign_review.py` — bounded asynchronous review and safe stage timings.
- `crm_campaign_send.py` — timing only; audience/queue semantics unchanged.
- `crm_html_workspace.py` — one-line effective-preview-settings handoff.

Validation files: `tests/test_crm_review_modal.py`, `tests/test_crm_review_ui.cjs`,
`tests/test_crm_send_flow.py`, `tests/fixtures/crm_review_modal_preview.py` and this
report. The fixture has an optional `REVIEW_FIXTURE_BASELINE=1` mode that loads the
HEAD implementation solely for the before/after browser comparison.

No schema/migration, provider, attribution, consent or queue-lifecycle change.
No live send was exercised. No campaign/customer/email was modified in production.
The patch is locally validated for review and an approved deployment, with the
existing production readiness gates still required. Nothing was committed,
pushed or deployed by this task. Existing unrelated Inbox edits were preserved.
