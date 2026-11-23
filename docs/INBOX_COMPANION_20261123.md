# Inbox Companion — 23 November 2026

Release authorised on 23 November 2026. Production activation and runtime results
are recorded separately below; no customer email or supplier edit was used as a
development test.

## Behaviour

The existing paired Edge extension has a separate Inbox scheduler, without a
header/status card. It polls every 30 seconds, using the existing server mailbox
configuration. The OS window and Inbox page do not need to remain open. Edge and
the computer must remain running; supplier browser actions require the existing
Prodigi login. Inbox intake can run while Orders uploads, but native edits share
the existing Orders writer and owned tabs. There are no new extension permissions,
Render services, provider credentials or database migrations.

Only new Inbox messages after activation are processed. First use and a mailbox
UIDVALIDITY change establish a fresh baseline rather than acting on historical
mail. Message-ID deduplicates copies/reappearance; otherwise the mailbox UID is
used. At most five new messages are inspected per poll, with the cursor retained
behind the unprocessed remainder. Bodies/attachments/remote images are not saved
to job metadata; only the parsed delivery fields and reply-thread headers remain.
Inline image downloads are disabled for these background reads.

Matching requires one recent (14-day) unfulfilled mirrored order for the exact
sender email; an explicit SC number narrows this match. Multiple order references,
multiple candidate orders, mismatched Reply-To, automated/bulk and malformed
messages do not produce a supplier action. Automation additionally requires a
DMARC pass with matching From domain, or a strictly From-domain-aligned DKIM pass
when DMARC is absent, in the first Authentication-Results header from a configured
trusted receiving authority. Its identity must also match the first Received hop.
Configure
`SPORTS_CAVE_INBOX_AUTH_SERVERS` only after verifying the receiving provider removes
spoofed copies of its own authority's headers. Never trust an arbitrary header or
search lower headers for a passing result. Missing/untrusted/failing results are
review-only and cannot edit or pause the supplier. No trusted authority was
invented or configured during development.
This trust requirement follows [RFC 8601, section 1.6](https://www.rfc-editor.org/rfc/rfc8601.html#section-1.6).
Email prose is parsed as data, never executed or used to choose arbitrary tools.
Quoted history and acknowledgements in an old change-request thread do not replay
the old request. Ordinary shipping/status questions are left to the existing inbox.

For an already paused/on-hold order, a complete same-country address replacement
can be applied. Supported explicit labels include Address, City/Suburb, State,
Postcode and Country, with an optional recipient name/address line 2. Common
Australian and US address blocks are also accepted. An absent new recipient name
preserves the old name; contact email and phone are always preserved. An omitted
line 2 in a complete replacement clears the old unit line. Partial addresses,
conflicting fields, country changes, mixed product/address requests and unclear
change instructions become a hold/review request instead of a guessed edit.
Prodigi's inspected country field is disabled, so cross-country changes require
manual review. This parser deliberately does not claim to understand every email.

The address form's actual IDs were inspected read-only in the live dashboard,
then closed with Cancel changes. No live address or countdown was changed.
Each Save/pause requires a single-use server permit pinned to the customer,
supplier reference, all exact supplier item IDs and the pre-edit supplier state.
Every product/numbered item and business field must remain unchanged. An address
reply enters the existing durable SMTP outbox only after supplier GET readback
confirms the entire replacement address and unchanged contact details. Split
supplier orders must all confirm first. The existing saved Nathan signature,
reply threading and Sent-copy worker are reused; the one deterministic operation
ID prevents duplicate sends. Queued confirmation does not mean delivered email.

Size, frame, cancellation and other order changes only pause indefinitely and
flag the order for review. This module cannot cancel, refund, select variants,
submit/pay, click Send now or resume an order. Existing indefinite pauses and
normal countdowns after an address edit are preserved. An uncertain Save/pause
is not repeated; it becomes a review flag. Supplier state is never inferred from
an old Order history entry.

If the supplier is still a draft/preparing, the request blocks automatic submission
and goes to manual review; it does not change upload/QA snapshots mid-process.
Orders already in production are also review-only. This is a material limit of
the initial release. Missing supplier mappings remain pending until they exist.
An owner can clear a reviewed local flag in Companion control; that action does
not resume Prodigi or change a product. All items in the customer order share the
request flag, including identical variants, without changing their QA checks.

## Local release controls

The owner explicitly authorised verification, production release and activation
on 23 November, confirming Nathan's Render workspace. Read-only production
preflight used 20 header-only messages: the first authentication authority and
first receiving hop were `be4.s10.ax.email` throughout. The provider reported
19 DKIM passes (14 strictly aligned to From), one neutral result and no DMARC
result in that first header. The verifier therefore supports strictly aligned
DKIM from that first trusted receiver, with explicit DMARC failure still blocking
automation. SPF alone and results from lower/untrusted headers are insufficient.
No email bodies, credentials or customer addresses were printed by this check.

Live supplier schema inspection confirmed the existing email/name/phone/address
fields, and caught Shopify global-ID versus numeric-ID aliases. Inbox matching,
submission flags and the Orders display normalize both forms. Activation captures
its mailbox cursor before enabling, preventing the first desktop alarm gap from
skipping newly arrived messages. The installed 1.7.49 Orders queue, upload, QA,
wake and worker source matched the production baseline before preparing the update.
The prior complete Orders release gate passed 342 Python and 113 Node checks,
including 1/2/5/10-item submission fixtures. Final committed release validation
and live activation observations are retained in the Studio task evidence.

The feature is off unless `SPORTS_CAVE_INBOX_COMPANION_ENABLED=true` on the server
and an authorised administrator enables Inbox Companion in Companion control.
Activation also requires the verified receiving authority allowlist described above.
The new extension candidate is 1.7.50 and reuses existing pairing. Neither control
was activated. Existing Orders has no additional flag database reads while the
feature environment gate is off. The only submission change is a customer-request
guard; the normal variant, artwork, item QA, grouped QA and Submit path is retained.

Before any authorised rollout, integrate against the then-current main, rerun
the recorded focused checks, install/verify the exact package and inspect a
genuine request under observation. Verify provider sender-authentication handling
and the current customer email/order correlation before enabling unattended
address edits. Never use a submitted customer order as a fabricated canary, send
customer test emails, or bypass the repository's preview restrictions.

To stop new work, switch Inbox Companion off. In-flight actions with a committed
permit require readback/manual review; disabling is not a claim to undo an edit.
The existing finite supplier production countdown continues when Edge is closed,
offline or asleep. Inbox Companion cannot promise interception after production
has started or while the desktop is unavailable.
