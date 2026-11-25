# Inbox and certificate companion: diagnosis and four-phase plan

25 November 2026. Follow-up to the released certificate automation and
Companion sent markers. Phase 1 is implemented in this change; phases 2–4
are a proposed roadmap, not claims of completed functionality.

## Diagnosis

The previous deployment's first new Render instance timed out opening TCP
connections before mailbox authentication. The retiring instance authenticated
successfully. Redeploying the identical build restored connectivity on a new
instance. This establishes an instance/network-dependent connectivity failure;
the logs do not establish whether routing or a provider firewall caused it.

The companion already retains its durable cursor on failed reads, opens a fresh
provider on each pass, and uses a deduplicated outbox. Two recovery gaps remained:

- Busy admission and an existing shared connection cooldown were treated as
  new connection failures. An independent worker backoff grew to 240 seconds
  even when the mailbox coordinator was simply asking the worker to wait.
- Selected message-body failures populated the error card without consistently
  entering the inbox reconnect scheduler. A user could be left with a Retry
  button despite the error promising automatic reconnection.

Neither fault requires clearing the order, mailbox cursor, drafts or outbox.
Unknown SMTP outcomes must continue to be reconciled without blind resending.

## Speed evidence

Read-only production log sample: latest 100 matching events after the healthy
instance started at 02:27 UTC. Pagination reported more events, so this is a
small diagnostic sample, not a representative load benchmark. No customer
bodies or credentials were used in development tests.

| Stage | Samples | Median ms | Sample p95 ms |
| --- | ---: | ---: | ---: |
| Server shell/list preparation | 20 | 0.3 | 0.3 |
| TCP/TLS connection | 19 | 699 | 2005 |
| Authentication | 20 | 237 | 420 |
| Folder selection | 9 | 209 | 239 |
| Header fetch | 7 | 238 | 435 |
| Cold message read | 2 | 3239 | 3239 |
| Related history read | 2 | 3756 | 3756 |

With two samples, the message/history figures are individual observations,
not statistically useful percentiles. Shell timing excludes browser rendering,
database model work after the shell log, and provider waits. Cold provider
latency, repeated handshakes and connection scheduling are the primary measured
opportunities. Existing lazy bodies, cached list identity, background index and
bounded attribution query should be preserved.

## Phase 1 — automatic recovery and evidence (this release)

- Recreate provider connections on worker passes indefinitely after transient
  drops. Respect shared cooldown deadlines; busy admission retries in five
  seconds without inflating failure counts. Genuine failures retain capped
  exponential backoff. All waits remain interruptible for shutdown.
- Route selected-body connection failures through the existing timed reconnect
  scheduler, preserving selected UID, drafts and cached content. Retry reads,
  never replay sends, deletes, moves or other writes.
- Keep authentication/configuration/TLS failures as explicit attention states
  in the inbox; never bypass TLS checks or reset credentials.
- Emit safe success duration and classified retry logs for companion checks.
- Verify fabricated disconnect/recovery, cursor retention, no duplicate intent,
  sent attribution, signatures and existing inbox performance contracts.
- Acceptance: recovery occurs through scheduled passes without a user reset;
  exact message identity and one accepted outgoing operation are preserved.

## Phase 2 — predictable speed

Instrument browser click-to-header/body timings, queue wait and connection
reuse separately; collect p50/p95 over at least 100 cold and warm selections.
Prioritize selected bodies over optional history, consolidate compatible
read-only operations, and assess bounded connection reuse with UIDVALIDITY
fences. Keep list/header rendering independent of history completion.

Proposed targets: cached selection feedback below 100 ms; warm body p95 below
250 ms; cold body p95 below 2 seconds when provider latency permits. These
targets require measurement and are not current performance claims.

## Phase 3 — professional inbox experience

Unify connected, syncing, reconnecting, queued, sent and needs-attention states
with clear last-success and retry information. Keep the small Companion sent
marker authoritative. Improve keyboard navigation, focus preservation,
accessible status announcements, mobile layout and loading placeholders.
Preserve compose autosave, attachment controls, Nathan's signature and existing
mail actions. Acceptance includes keyboard/mobile checks and no duplicate or
misleading success notices.

## Phase 4 — operational reliability

Track oldest unprocessed UID age, last successful companion poll, outbox queue
age, uncertain outcomes, Sent-copy lag, reconnect rate and cold/warm latency.
Define alert thresholds and an outage runbook; establish provider/hosting
network escalation and verified failover options. Exercise drop/reconnect,
deployment overlap, process restart and sustained-arrival fault tests.

Proposed service goals: 99.9% monthly availability excluding documented
upstream outages; eligible requests queued within 60 seconds of healthy mailbox
access under normal load. A disconnected upstream cannot be made to deliver
mail by application retries alone. Preserve pending work until connectivity
returns, and alert instead of silently claiming success.
