# Campaign send experience

## Cause and change

Previously the successful queue handler displayed a receipt and immediately
called a full `st.rerun()`. The selected campaign ID stayed in the editor/URL.
The Campaigns route then found the durable delivery record and automatically
rendered the large locked campaign preview. History refreshed only every 30s,
was labelled Drafts, and sorted solely by draft timestamps.

The review remains authoritative and compact. Clicking its final production
button replaces that button with disabled **Preparing campaign…**, retaining
the existing operation UUID. The existing `queue_campaign()` transaction and
all its revalidation/idempotency protections remain unchanged.

After its durable receipt, the same open dialog clears the summary/preview and
renders **Sending campaign**, actual persisted progress, and Minimise / Close.
There is no full-page rerun at queue completion. Only the sent editor is replaced
in session with the existing `new_compose()` defaults; its campaign query
parameter is cleared. The new composer becomes visible when the user dismisses
the overlay. A separate draft is never replaced by status polling.

## One authoritative progress calculation

`crm_campaign_progress.read_progress()` executes one read-only aggregate for
one or multiple campaign IDs. Campaign status and send counts come from the
same SQL statement/snapshot. It selects no customer identifiers, recipient
addresses, payloads, template bodies, provider IDs or webhook data.

The `campaign_id` restriction can use the leading column of the existing unique
indexes `(campaign_id, shopify_customer_id)` and `(campaign_id, recipient_hash)`.
No migration or new index is needed. The query is a constant-size result,
although counting naturally scales with the selected campaign's send rows.

| Durable send status | Meaning |
| --- | --- |
| PENDING / CLAIMED / SUBMITTING | Still pending normal worker processing |
| ACCEPTED | Submitted/accepted, never described as delivered |
| BLOCKED | Skipped |
| FAILED | Failed; attention required |
| UNCERTAIN | Held; attention required, do not resend |
| Unrecognised future status | Conservatively held/attention |

Total is the number of retained, non-test send rows in the frozen queued
audience, including BLOCKED rows from final revalidation. It deliberately does
not use `final_recipient_count`: that field excludes initial blocked recipients
and is later rewritten by the worker. Processed = submitted + skipped + failed
+ held. For three ACCEPTED and one BLOCKED, this means 4/4 processed, 3 submitted
and 1 skipped. A 100% bar alone never means sent. Only `crm_campaigns.status=SENT`
confirms completion. Held/failed rows retain explicit attention wording.

The existing worker owns delivery and the SENDING → SENT transition. This task
does not change its logic or replay any send.

## Polling and isolation

The dialog status, floating tray and history own independent Streamlit fragment
events. One-shot timers click hidden, native fragment buttons; no WebSockets,
provider polling, browser storage of recipients or separate delivery thread.
Timers stop when their DOM region unmounts. History/tray polling defers while
unrelated AI/analytics dialogs are open. The tray also defers behind the send
dialog; that dialog owns its own status refresh.

- Sending/Building and near-due scheduled status: every 2.5 seconds.
- Active history: every 3 seconds, including schedules due within one minute.
- Idle/future-scheduled history/status: every 30 seconds.
- Short session aggregate reuse: 2 seconds, scoped to the exact IDs requested.
- Opening a tray status explicitly clears that cache and reads fresh DB state.
- A successful queue wakes the history fragment once so an idle timer does not
  leave the just-queued campaign absent for 30 seconds.

Polling never calls Shopify, Resend, audience calculation, rendering, image HEAD
requests, tracking verification or queue creation. It never writes editor state,
calls focus APIs or performs a full-page rerun. Explicit navigation/dismissal
actions may perform a normal app rerun to show the new composer or analytics.

## Minimise, close, completion and multiple campaigns

Minimise removes the blocking dialog and shows a fixed, small, nonblocking tray.
Close removes that campaign's tray entry as well. Native X/Escape dismisses the
overlay and leaves background status available. All only affect UI visibility;
none pauses/cancels delivery or changes a send row.

The session tracks a map of campaign IDs, not one mutable global send ID. Each
Open button reopens its own DB-backed status. The tray is fixed outside normal
page flow, bounded to 180px with internal overflow for many concurrent entries.
Its Open/Hide controls do not own delivery. Clean completed entries expire after
20 seconds at the next tray refresh; attention entries do not silently disappear.
It is a temporary status surface, not an archive.

SENT displays precise submitted/skipped/failed/held counts, Done and explicit
View analytics. Analytics never opens automatically from a completion poll.
Unexpected session/app reruns recover the tracked IDs through DB reads rather
than trusting session percentages; tray timers do not depend on an old modal
visibility flag. Full browser/session loss can still find durable campaigns in
Active/Sent history; progress percentages are not stored in the browser.

## History and explicit View

Drafts is now **Active**. The same history poll updates Active/Sent counts and
the selected table. SENDING rows disappear from Active once the DB reports SENT;
Sent uses the existing analytics query/controls. Selection, search, archived
controls, version history and actions remain available.

History orders/displays `GREATEST(d.updated_at,c.updated_at)` without mutating
draft timestamps. Active rows show compact submitted/total progress. Scheduled
campaigns that actually enter SENDING are no longer mislabelled SCHEDULED from
the old document's timing field.

Explicitly opening a queued campaign shows a compact operational read-only
view, Back to campaigns, secondary Duplicate, and a bounded preview loaded only
on request. Its status fragment never reloads that preview. Sent table
View analytics continues to open the existing analytics UI. No locked preview
opens automatically after queueing.

## Files

Production:
- `crm_campaign_progress.py` — new DB-only aggregate, status semantics/cadence,
  exact-ID cache, multi-campaign session tracking and completion expiry.
- `crm_campaign_progress_ui.py` — independent dialog/tray/history timers,
  compact status UI and explicit operational view.
- `crm_campaign_send_ui.py` — same-dialog queue transition, busy button, durable
  receipt state and guarded clean-composer transition.
- `crm_campaign_page.py` — Active history, adaptive refresh, batch progress,
  activity dates, composer-first tray mounting and explicit operational view.
- `crm_campaign_store.py` — read-only counts/cadence and activity ordering.

Tests/evidence:
- `tests/test_crm_send_progress.py`
- `tests/test_crm_send_progress_ui.cjs`
- `tests/fixtures/crm_send_progress_preview.py`
- `tests/test_crm_campaign_history.py`
- `tests/test_crm_production_v2.py`
- `tests/test_crm_send_flow.py`
- `docs/CAMPAIGN_SEND_EXPERIENCE.md`

## Validation and limits

Local PGlite PostgreSQL fixture, mocked transports, offline Streamlit AppTest
and local browser only. The deterministic queue fixture covered 0/4 → 2/4 →
SENT, retained skipped rows, history filtering and unchanged draft records.
The existing actual-worker tests covered background delivery and scheduling.

Focused regression command (with a fresh disposable SQL fixture and
`CRM_TEST_POSTGRES=1`):

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_crm_send_progress tests.test_crm_review_modal tests.test_crm_campaign_history tests.test_crm_campaign_first_paint tests.test_crm_fast_review tests.test_crm_send_flow tests.test_crm_production_v2 tests.test_crm_campaign_loading tests.test_campaign_recovery tests.test_crm_campaign_v2 tests.test_crm_campaigns_v1 tests.test_crm_email_size tests.test_crm_tracking_hardening tests.test_crm_production_style_test
node tests/test_crm_send_progress_ui.cjs
node tests/test_crm_review_ui.cjs
```

206 focused Python tests passed before the final cadence regression was added;
40 post-change targeted checks passed including that new regression. JS timer
and review checks passed; py_compile and git diff --check passed.

Broader validation also ran unsubscribe and leave-dialog tests. All 14
unsubscribe tests passed on a fresh fixture. Three leave tests passed; two
existing assertions that AppTest no longer lists a dismissed dialog's buttons
failed. Their navigation and saved-draft checks passed. Both assertions also
failed when all three changed production modules were replaced in memory with
their unchanged HEAD versions. No leave-dialog implementation was changed.
Repeated suite runs must use fresh SQL: fixture suppressions and retained sends
otherwise contaminate later tests' reused synthetic customer IDs.

Synthetic loopback SQL: ten four-recipient aggregate reads averaged about 15ms
in one run. This includes fixture HTTP overhead, not production DB latency.
No real Shopify/Resend latency or production throughput was measured.

Browser evidence: at 1366×768 the sending dialog was 520px wide and about 312px
high, with zero preview iframes. Minimise removed the modal overlay. Background
history/tray updates preserved the second campaign's uncommitted Subject input,
focus, scroll=0 and composer render count=3 while the first campaign completed.
At 390px the completion dialog was 358px wide/about 295px high, without
horizontal overflow. Screenshots are stored in the task visualization folder:
`campaign-sending-laptop.png`, `campaign-send-minimised-laptop.png`,
`campaign-send-status-narrow.png`.

No production resources were accessed or changed. No email was sent. No commit,
push, deployment, Render/environment/schema change, migration, worker rewrite,
tracking change or Shopify modification occurred. The change is ready for
deployment review, with the existing leave-test limitation explicitly recorded.
