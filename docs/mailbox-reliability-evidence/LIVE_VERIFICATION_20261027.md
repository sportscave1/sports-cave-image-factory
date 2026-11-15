# Live mailbox verification — 27 October 2026 (Sydney)

Task `20261025-35ed7e58`, owner `codex-mailbox-reliability-01a157b1-20261026`. Existing isolated worktree and branch were reverified before changes; original EMAIL category work remains untouched. This report supersedes the pre-release limitations/status in REPORT.md and RELEASE_REVIEW.md.

## Release and rollback

Owner explicitly authorised Git push/Render release and approved hello@sportscaveshop.com in response to the request to send a small test, attachment and reply and inspect destination receipt. Credentials stayed in their existing Render environment; none were printed or copied to development.

Initial mailbox release `a19192f2e496511a113e0af8c55a5cb148f90594`, deploy `dep-dbfs98m1egvs73c58qp0`, became live at 2026-10-26 21:25:34 UTC. An unrelated release `6e59900dff5e317bce2bb4c0bd84a88703b310f3` superseded it at 21:38:09 UTC; ancestry and an empty email-source diff verified it retained the entire mailbox change. Unrelated released work was merged normally into the task branch and preserved.

Follow-up `197cb2c0dafb8b51f9024714bee026a1d99a4c20`, deploy `dep-dbfsne8m7kps73asb4n0`, adds the verified first-render height recovery and became live at 2026-10-26 21:55:46.551814 UTC. Only canonical primary sports-cave-os (`srv-d8kl4on7f7vs73dvavv0`) was manually deployed. `[skip render]` suppressed broad automatic deployments. No service/config/Blueprint/schema/dependency change. Immediate follow-up rollback: retained 6e59900d deploy `dep-dbfsf695efls738rdpag`. Full mailbox rollback must use a reviewed mailbox-only revert against current main, preserving unrelated releases; do not blindly return to 5980a803.

Another unrelated release `05a0b87d205a668ebe2508303ae797a9b804e639`, deploy `dep-dbft45tg1s2s73es9390`, became live at 22:23:01.537982 UTC during observation. Ancestry and empty diffs across the component, mailbox modules and server confirm it retains the final mailbox source. Task branch fast-forwarded to current main ca093ab4, preserving its ad-package changes and test whitespace. A concrete mailbox-only rollback patch passes apply-check on ca093ab4; see RELEASE_PLAN.md. Do not roll back the whole service to older releases and discard newer unrelated work.

## Fixes and focused checks

Seven production files retain the current architecture: partial incremental FETCH cannot advance past a still-present missing UID; stale health cannot mask newer failures or newer success; dead index/IDLE/outbox threads restart safely; BYE reconnect and bounded periodic catch-up remain active; unknown sends continue read-only reconciliation with backoff; observed SMTP acceptance is retained for DB-only receipt recovery and persisted only once; IPv6 attempts share a bounded budget when IPv4 is available, preserving DNS and TLS hostname verification. UI ready retries are bounded and stop on host acknowledgement/page exit.

The stricter component test uncovered a second reproducible condition: a host that misses the first ready message can also miss the first height announcement. Before the fix, actual iframe height remained zero despite rendered content. The first acknowledged render now resends height once; subsequent renders retain deduplication. Chromium delayed-listener (800ms) test passes with 710px height, stopped retries, unchanged later-height message count and no page errors. Real local Streamlit 1.58 host with fabricated data also renders without errors. Owner confirms Email loads normally in the normal OS window.

Prior focused checks: 38 disposable SQL/recovery tests, three transport tests, handshake unit, 73 scheduler/context assertions and reader sandbox checks passed; topology and diff checks passed. Local PostgreSQL service was unavailable (Docker daemon off, no PostgreSQL binaries/service), so true competing-process PostgreSQL locking was not claimed. No repeat simulated speed benchmark was used for this release.

## Authenticated live sync

Read-only EXAMINE/BODY.PEEK header checks from actual Render runtime:

| Check | UTC | Authenticated recent-header time | Latest Inbox UID | Latest 20 IDs missing from OS |
| --- | --- | ---: | ---: | ---: |
| Pre-release 5980a803 | 26 Oct 21:18:52 | 2082–2136ms | 119 | 0 |
| Post-release a19192f2 | 26 Oct 21:28:46 | 2082.8ms | 119 | 0 |
| Final release 197cb2c0 | 26 Oct 21:56:41 | 1929.6ms | 121 | 0 |

These samples prove actual authenticated login/select/fetch/index access; they do not establish a statistically meaningful latency improvement. No mailbox reset, draft deletion, queue clearing or blind unknown-send retry occurred.

## Real round trip

The live application compose/MIME, durable registry/outbox worker, SMTP and IMAP paths sent exactly two self-addressed messages to the approved owner-controlled mailbox on 6e59900d. These were runtime-path tests, not automated UI clicks. Only the test message MIME was read to verify the attachment.

| Measurement | Initial + attachment | Reply |
| --- | ---: | ---: |
| Runtime queue acknowledgement | 3017.0ms | 2864.6ms |
| Durable queued → actual SMTP acceptance | 8883.961ms | 8300.038ms |
| Destination Inbox exact-ID receipt observed from test start | 17062.7ms | 16982.6ms |
| Provider Sent exact-ID visibility observed from test start | 23299.6ms | 20609.2ms |
| Durable SMTP submission attempts | 1 | 1 |
| Inbox UID / Sent UID | 120 / 30 | 121 / 31 |

Initial operation `a8346ef0-10ea-4942-8acf-5df33720c30c`, Message-ID `<sc.a8346ef0-10ea-4942-8acf-5df33720c30c@sportscaveshop.com>`, durable created 21:43:00.018042 UTC, accepted 21:43:08.902003 UTC. Reply operation `e9a6720a-36b5-485f-aa47-2c009299d7ea`, Message-ID `<sc.e9a6720a-36b5-485f-aa47-2c009299d7ea@sportscaveshop.com>`, created 21:43:26.783711 UTC, accepted 21:43:35.083749 UTC. Both statuses accepted, Sent-copy status appended. Exact receipt in destination Inbox proves more than SMTP acceptance. Initial attachment `mailbox-verification.txt` decoded bytes match the static test text. Core thread builder puts initial and reply together. Both appeared in OS index without manual refresh, index success at 21:43:40.496 UTC. Entire verification 50.5s.

Receipt/Sent observations include polling and processing, not precise provider arrival latency. This is a same-provider self round trip, not a cross-provider delivery test. No GUI send-click acknowledgement or exact provider-availability-to-display latency was measured. Folder audit: Inbox 91→93, Sent 28→30, provider Drafts unchanged at 2, active local drafts unchanged at 27; UIDVALIDITY retained. Test mail remains available for owner review.

The final-instance audit later saw Sent 31 and local active drafts 31 during independent live activity; provider Drafts remains 2 and Inbox 93. Read-only exact-ID recheck at 21:58:17 UTC confirms each test still has exactly one Inbox and one Sent match. Counts are observations, not a claim of an immutable production mailbox or a full per-draft content comparison. Public deployed mail.js returns 200 and includes the first-render height recovery.

## Recovery observation

Observation ran 21:56:50.332 UTC → 22:29:56.755 UTC: **33 minutes 6 seconds elapsed**, across the unrelated rolling deployment. Retained 26 samples covering 25 minutes on 197cb2c0, then seven samples covering six minutes on the replacement 05a0b87d instance. The first script was terminated by instance replacement, not completed; its actual samples are retained without inventing a completion summary. Sampling gap between retained windows: 123.425s. This is not an uninterrupted 30-minute single-instance trace.

All 33 retained samples have zero duplicate UIDs. Eight bounded comparisons of the latest 20 provider Message-IDs have zero missing IDs. Successful timestamps advance throughout each window. Steady-window maximum sampled sync age: 70.3s. During handover one sample reached 116.1s, then success advanced automatically; observed success-to-success gap 134.019s. Last sample age 23.4s. Cached mail remained indexed; no manual refresh, cursor reset or resend was used.

A real new arrival advanced UID 121→122 at minute 21, after the previous approximately 20-minute disconnect interval. Shared watcher signal timestamp 1793053037.137038 → successful index timestamp 1793053040.9558685: **3.819s**. This measures signal-to-index success, not exact provider availability or GUI display. Provider UID 122 and all 20 recent IDs match at minute 25 and after replacement. Only identifiers/counts were inspected for the new arrival; its content was not read.

Replacement runtime authenticated headers in 2307.8ms at 22:23:44 UTC; provider Inbox 94/UID122 and OS UID122, zero missing recent IDs. Provider Drafts remains 2; later Sent/local draft counts are 32/32 during live activity. October 7 remains unknown, submission attempts 1, reconciliation checks 9. Available Render logs contain no captured natural BYE/reconnect event during this interval. Safe BYE/dead-worker/missed-event fault tests passed locally; live rolling-restart and subsequent automatic sync are verified, but an actual live BYE fault is not claimed. Raw retained samples: live-recovery-observation.json.

## Specific unresolved issues

- October 7 operation `11b2a2bc-5643-42cb-9a5b-5930dc10d35e`, exact Message-ID `<sc.11b2a2bc-5643-42cb-9a5b-5930dc10d35e@sportscaveshop.com>`, remains unknown/pending copy, SMTP attempts 1. Exact provider Sent search had no match; absence cannot establish failure or delivery. Original provider SMTP/queue evidence is unavailable. It was not resent or marked accepted.
- Owner confirms normal UI loads, but the controlled signed-in browser produced a component warning (the same browser also failed the isolated Streamlit host that passes headless Chromium). Automated authenticated UI opening/expansion timing, transferred-byte cold/warm/throttled comparison and GUI acknowledgement remain unverified. Existing synthetic lazy-body evidence is retained and clearly labelled; no live speedup claim is made.
- Process-local acceptance evidence cannot survive process death before a failed database receipt write is repaired; ambiguous durable operations remain reconciled without automatic SMTP retry. Real PostgreSQL competing-process claim testing remains unavailable locally.

Release status: mailbox production source is live (197cb2c0, retained unchanged in current live 05a0b87d). Authenticated sync and real approved email round trip pass. Focused component/recovery checks and the bounded live observation are complete, with the precise limitations above. No blanket claim that all delivery/UI/network failure modes are fully verified.
