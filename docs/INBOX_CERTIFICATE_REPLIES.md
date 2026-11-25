# Missing-certificate replies

The canonical web server runs a small lifecycle-owned worker every thirty
seconds. No extension update, new service, credential, campaign or order change
is required. The rule is disabled until an Email administrator enables it in
Companion → Inbox → Missing certificate replies.

Only new Inbox messages after activation are scanned. The administrator can
also check the newest existing request and explicitly enable the rule with
that exact message included. Activation rechecks its mailbox identity, policy,
certificate availability and Sent history. Re-enabling an already running rule
retains its pending new-mail cursor. UIDVALIDITY changes establish a new
baseline without replaying historical messages.

A deterministic policy checks newly authored text for a missing certificate,
COA, packing slip or package slip, or a request to access/resend the certificate.
Quoted history and thanks-only replies do not trigger it. Mixed refund, damage,
product or address-change requests remain manual. The sender must be a known
customer with a ready certificate, the mailbox must be a direct recipient,
Reply-To must match From, and automated/self/no-reply messages are excluded.
No private customer details, certificate URL or attachment is sent: every reply
uses the existing public My Collection login destination.

The reply links to My Collection, tells the customer to log in to access their
certificate, mentions framing and briefly asks for a review there. It selects
the saved `nathan` signature and adds no sign-off to the body. Existing human
compose, signatures, mail settings and order-change automation remain intact.

Before queueing, the worker checks Sent for a reply to the incoming Message-ID
and preserves matching human drafts and unresolved sends. One deterministic
operation UUID per mailbox/Message-ID is inserted through the existing durable
outbox. Concurrent scans and restarts reuse that operation. The outbox owns
SMTP acceptance and Sent-copy reconciliation; uncertain DATA is never resent.
Automatic replies carry `Auto-Submitted: auto-replied` and suppress further
automatic responses. Disabling stops new authorisations; already queued mail
continues through the existing outbox.

Diagnostics retain message identity, sender, outcome and operation ID, without
storing incoming message bodies. Read-only message fetches do not mark mail
read, move it, download certificates or modify customer orders. Incomplete
messages, unavailable certificates and existing manual work remain for review.

Offline verification uses fabricated mailbox data and disposable PGlite with
the real mail-outbox migration. Tests cover matching, exclusions, threading,
one Nathan signature, no certificate/PDF attachment, duplicate scans, restart
and unknown-send recovery, mailbox reconnects, cursor rotation, explicit current
requests and ASGI lifecycle startup/shutdown. The release gate also runs the
existing signature, human compose and mailbox lifecycle suites.
