# Campaign send acceptance and Home progress

The final Review & send dialog still performs the existing production checks.
`queue_campaign()` commits the frozen template, reviewed recipient snapshot,
campaign/send identities and `crm_marketing_sends` queue rows before returning its
receipt. No UI code submits provider messages. Only a committed receipt triggers
navigation to Campaigns Home; rejection remains in Review.

Previously `_review_finalization()` kept the dialog open, rendered
`status_content()`, registered the floating tray, and reset the composer via
`new_compose()`. Home used the active cadence to invalidate its full table query,
which also aggregates provider events and attribution. The old status readers
did already read durable counters; a screenshot of zero is not proof of a polling
failure or a provider outage.

Now a single app navigation closes Review, retains the composer and seeds a row
using only accepted receipt/editor fields. Subsequent reads are authoritative.
`crm_campaign_home_progress.live_rows()` uses one bounded read for visible active
campaign IDs. It caches progress for 2.5 seconds separately from the 20-second
table/analytics cache. Registered-future and timestamp checks reject late results;
last-good progress and analytics remain visible on read failure. Background
refresh stops when its DOM control unmounts, waits while another dialog is open,
and pauses polling while the browser tab is hidden (checks visibility every 30s).
Scheduled jobs use 30-second progress reads until within one minute of dispatch.
Stalled or wholly held jobs also use the slower status-read cadence.

## Durable semantics

`total` is the sum of persisted non-test recipient rows. `submitted` is ACCEPTED,
`skipped` is BLOCKED, `failed` is FAILED. PENDING/CLAIMED/SUBMITTING are outstanding;
UNCERTAIN and unknown states are held. `processed` is submitted + skipped +
failed + held. Submission is not delivery: delivered/opened/clicked remain
verified webhook/event-ledger metrics. Attribution remains backend-owned.

The worker commits provider batch receipts and recipient counters atomically.
It then marks a campaign SENT when no pending/claimed/submitting/uncertain rows
remain. That existing policy is unchanged; completed recipient failures display
"Sent with issues" when the live result is available. Held work requires attention,
not automatic resending. Detail views read the same durable counters and display
only allowlisted safe failure descriptions.

The worker runs independently of browser sessions. Its current idle interval is
30 seconds, so an accepted job can legitimately remain at zero before the next
worker tick. `worker_started_at` means the first persisted provider submission
attempt, not acceptance time. `last_progress_at` comes from recipient update
timestamps; dispatch now timestamps held/blocked/attempt transitions consistently.

## Stalled reporting and diagnosis

After ten minutes without a durable update, a SENDING job is reported as Stalled
with a detail link. Future recipient-local scheduled work is exempt until due.
This is a read-side warning: it does not rewrite campaign state, release leases,
or submit messages. Safe diagnostics record IDs, states, counters, timestamps,
batch counts and Home status-poll counts. They never record recipient addresses,
email bodies, unsubscribe URLs, raw provider exceptions or credentials.

To diagnose an actual production zero-count job, inspect the same campaign/send
ID in worker logs and durable records: marketing gates, worker lease, due times,
first submission attempt, last recipient update, pending/submitting/held state,
and batch retry/receipt state. Do not enqueue a replacement while submission is
uncertain. Production records were not accessed during this local implementation,
so the particular historical 0/1095 incident's worker condition is unconfirmed.

## Offline evidence

The disposable loopback PostgreSQL fixture and mocked provider test exercise
1,095 recipients through eleven batches, observe counters after every receipt
commit, reopen with a new connection, confirm SENT and verify no repeat transport.
The loopback Streamlit/browser fixture verifies review closure, Home navigation,
0 → 100 → 500 → SENT, removal of progress at completion, reload without another
job, and contained layouts. These tests establish the implementation path;
they do not measure production latency or test live Shopify/Resend.
