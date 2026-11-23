# Companion polling and database recovery

The Social Media release did not change database code, schema, or connection
settings. Its rollout failed before serving traffic: startup schema verification
could not obtain a Supabase transaction-pool backend. The prior unrelated
release also failed a pool checkout. The running OS's account queries time out
against the same database.

Read-only Supabase logs identify queues behind the `product_upload_desktop`
singleton row, including heartbeat updates taking 77–103 seconds. An aggregate
activity snapshot also showed tuple-lock and WAL-insert waits. This establishes
polling contention; it does not establish why the database's WAL operations are
slow. No CRM or ads token was rotated, and no customer data was deleted.

The targeted patch adds shared admission for at most two poll transactions per
server process. Excess polls receive the existing retryable 503 path before
opening another connection. Once admitted, transaction-local settings bound
lock waits to 750 ms, statements to eight seconds, and idle transactions to
eight seconds. These settings do not alter database-wide or CRM configuration.
Existing claim locks, durable leases, authorization, and atomic rollback remain.
External provider work remains outside these transactions.

Orders companion authentication reads the current pairing on every request.
Its heartbeat writes at most once per 20 seconds and skips a locked singleton
instead of joining the job-claim lock queue. Pairing revocation is not cached.

The user approved a brief pause of Companion polling to drain the backlog.
Operational recovery and final rollout/action checks must be recorded as actual
observations; this patch alone is not evidence that the database recovered.

## Token-change chronology audit

Observed on 22 November 2026; times below are Sydney daylight time (UTC+11):

- 15:39:07: deployment `d07cf71a` became live, containing the visible social feed.
- 15:51:58: `accounts.current_user` already reported a database query timeout.
- 15:52:29: `ad21b5a9` became the serving release. It added a background supplier
  tracking worker. This timing is a candidate contributor, not proof of cause.
- 15:53:06: Orders database reads timed out; account pool timeouts followed.
- 16:03:09: Meta issued the new long-lived Community User token. It could not
  have been saved to Render before this time.
- 16:05:30: the likes release `a84fd5cb` began deployment. It failed startup at
  16:10:35 and never became live. A separate API-triggered retry also failed.

The Community key was saved with Render's **Save only** option. The serving
instance was started before that key existed. Existing environment-key names
were retained, with only `META_SOCIAL_ACCESS_TOKEN` added. The likes release
changed no database code or connection settings. The social feed's permission
checks use the supplied user record; its Meta read/cache path does not update
the contended desktop heartbeat row.

The Supabase dashboard warned that Nano compute was approaching its disk-I/O
budget and showed a baseline of 5 MB/s after exhaustion. During the subsequent
audit it independently entered `RESIZING`, with a dashboard notice that a
compute-size change was restarting the project. This agent did not initiate
that compute change. No overlapping restart or resize should be requested.

Polling regression validation: 152 tests passed, including existing design,
upload, ad-publishing and Orders queue contracts plus new deadline, rollback,
admission-limit and heartbeat-pacing cases. An existing stale tab expectation
was updated to include the already-present SEO queue.
