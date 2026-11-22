# Marketplace Resend alerts

New committed messages, offers, seller offer responses and PayPal invoice links
queue a short transactional email for the other participant. The existing OS
Resend key/sender pair is reused. Marketing switches, campaigns and audiences are
independent and remain unchanged. No new paid service, dependency or media store.

Emails have a short event heading, one **View conversation** button and an email
preferences link. They contain no chat text, names, listing title, prices,
attachments or PayPal payment URL. Links use the fixed marketplace origin and a
conversation UUID. A valid, verified marketplace account and conversation
membership are still required; the link is never an authentication token.

Registered customers can turn alerts off on **Account → Email alerts**. Published
guest sellers receive a content-free alert at their original submission email;
opening the chat requires registration and verification of that same email.
Blocked conversations/accounts and disabled email preferences suppress pending
alerts. OS support viewing a conversation does not mark it read for customers.

## Delivery and minimal storage

- The message and a small notification record commit in one transaction. The
  request never waits for Resend. Notifications cannot reference a rolled-back
  message, and provider failures cannot undo a saved chat message.
- The existing primary web service runs one lightweight ASGI-lifecycle consumer,
  checking every 15 seconds. A 12-second grace lets active chats receive the
  message in-app first. Visible customer page/poll reads cancel read alerts;
  polling without new messages performs no extra notification writes.
- Repeated activity coalesces into one alert per conversation per 15 minutes,
  capped at six attempted alerts per recipient per hour across conversations.
  A first pending alert is not postponed by continuing unread messages.
- The existing private `crm_runtime_state` table holds one reusable record per
  participant/conversation, one due pointer while pending, and one reusable hourly
  budget per recipient hash. Primary-key range scans fetch at most ten due jobs.
  Photos/videos remain in Dropbox and chat bodies are never copied into emails.
- Key ranges use a letter after the valid UUID/hash/numeric suffix alphabet and
  an exact namespace filter. The production database sorts punctuation such as
  a trailing tilde before these suffixes. Tests cover that ordering for inboxes,
  message pages, account lists, seller claims, due alerts and session cleanup;
  the existing primary-key index still bounds each lookup.
- Only an in-flight attempt temporarily freezes the small outgoing email fields
  and recipient so a retry is byte-identical. Success removes this payload and
  keeps a bounded receipt/sequence/cooldown record. Historical chat is not mailed
  when the feature is deployed. Stale queued activity expires after 24 hours.
- Leases recover after restart. Retries use the same Resend `Idempotency-Key`
  and frozen payload, with bounded backoff and a maximum of six attempts. The
  provider's 24-hour deduplication window is respected by stopping before 23
  hours. Ambiguous outcomes are not blindly resent outside that window.
- Email acceptance is not proof of inbox delivery. No logs contain private
  payloads, email addresses, credentials or raw provider exception messages.

The worker starts only with `RENDER` present, the existing paired Resend
configuration available and `MARKETPLACE_NOTIFICATIONS_ENABLED` not set to
`false`. Imports and local previews never start it. Shutdown stops new claims;
an interrupted in-flight attempt retains its lease and stable retry key.
The OS Accounts connection panel shows whether the alert consumer is running.

## Validation and release

Run `python -B scripts/test_marketplace.py`, `node tests/marketplace_accounts.cjs`,
`node tests/marketplace_gallery.cjs`, JavaScript syntax and the Render topology
validator. Synthetic provider tests cover routing, all alert types, opt-out,
read suppression, rollback, duplicate requests, quotas, immutable retries, crash
leases, expired idempotency and ASGI startup/shutdown. Tests send no real emails
and create no production accounts or conversations.

The owner explicitly authorised GitHub/Render publication for this task. Deploy
through the existing `sports-cave-os` service only; no Blueprint sync is needed.
Verify health, the running alert consumer, existing Resend connection and guest
chat gates without sending test messages to live customers.

References: [Resend sending API](https://resend.com/docs/api-reference/emails/send-email),
[Resend idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys).
