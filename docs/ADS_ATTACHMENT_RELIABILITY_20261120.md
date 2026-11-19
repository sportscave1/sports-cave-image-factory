# Ad attachment recovery — 20 November 2026

Studio task 20261119-cf14cfea, owner codex-ads-reliability-20261120-03.
User authorized diagnosis, recovery of the three current jobs, companion update,
Git release and deployment to the existing Render service.

## Observed incident

Final Lap job 94c3dcaa-f634-5370-95e8-59f5eed0573d finished its three covers
and CSV in the saved chat. Native chat cards failed to download. The automatic
repair text remained unsent in the composer; the durable permit was already
consumed, and the server correctly refused an ambiguous duplicate after five
minutes. The content script compared literal newlines against Work paragraph
spacing and allowed only three seconds for Send readiness. Its outer message
deadline was eight seconds.

Submitted the already staged repair exactly once. Its response repeated the
existing file references. Chat-card downloading still failed, while the explicitly
linked original Library file downloaded successfully. The preserved Collector
Hallway original is a readable 1024×1024 JPEG; its actual filename includes
`(20261119-213046)`, unlike the chat label. Resumed the same saved job through Play.

The other current jobs stopped for different reasons: No Fear's Architectural
Wall and Legends Never Die's Collector Hallway/Architectural Wall were reported
as `moderation_blocked` by the image provider. Their successful outputs remain
in their chats. These rejections were not retried or treated as transport errors.

## Companion 1.7.7

- Compare repair content independently of paragraph whitespace and wait up to
  120 seconds for its enabled Send. The worker deadline now covers that window.
- Journal preparation separately from clicking. Only the exact owned,
  unmodified, unclicked draft can continue after interruption. Once a click was
  journalled, absent/virtualized history never authorizes another Send.
- Wait for the submitted marker. Preserve the existing durable server permit,
  two-repair bound, imported hashes and deterministic Posting identity.
- On a failed chat-card download, accept a unique Library original only from
  the exact filename's table row in the selected assistant response. Open it
  inactive and use the site's native Download. Accept the timestamp suffix only
  for this associated fallback. Keep the existing file validation and receipt API.
- Retain explicitly requested original bytes across temporary blob revocation.
- Ask for real exports and original Library fallback links in the delivery and
  repair prompts. The approved Baseline artwork/footer instructions are unchanged.
- Include a reported provider rejection in missing-file queue errors.

No additional browser permissions, production credentials, services or schema
changes. Extension files are installed with SHA256 verification and an external
backup. Reloading the existing extension is required; the browser tool's URL
policy prevented opening extension settings, so the user was asked to reload it.

## Validation and limits

Synthetic Edge tests cover paragraph paste, slow Send, owned draft restart,
edited/foreign draft refusal, hidden sent markers, response isolation, native
Library downloading and revoked blob bytes. Node tests cover one-shot permits,
Library provenance, timestamped names, durable transfer journals, receipt retries,
message deadlines and worker lifetime. Disposable PGlite tests cover four file
receipts, original-job resume, queue serialization and posting idempotency.

Three broader `test_design_publish_ad.py` targeting assertions fail on both the
unchanged ce1e9d59 production implementation and this branch (expected set 21,
actual 20). An exploratory Creative Refresh suite also exposes existing unrelated
fixture/behavior failures; no Creative Refresh code is modified by this task.
These are not claimed as passing. Focused recovery acceptance is recorded in Studio.

The companion cannot guarantee provider acceptance, browser availability or
network uptime. It preserves recoverable checkpoints and avoids duplicate sends
or campaigns. Existing automatic posting creates paused ads for review; that
receipt does not mean delivery is active in Meta.
