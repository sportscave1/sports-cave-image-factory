# Focused Inbox release — 11 October 2026

Explicitly authorized focused production release of the coherent completed Inbox V2A–V2D candidate, independently of VentraIP ticket VIP-R2695883. Base: ccb63e87e385164d6b62298889a26fc6d1ab2512. Exact candidate hashes: deploy/inbox-2026-10-11.json.

Includes Outlook-style layout and resizable panels; asynchronous reads/readiness and cached navigation; bounded search, filters and individually confirmed bulk actions; draft recovery, autosave/conflict handling and attachment feedback; remote-image privacy, scoped caches and current-account/session authorization. Shared integration is limited to draft-journal clearing on account transitions, authenticated readiness registration and session-version claims.

Reuses the completed 534-test and browser/privacy/concurrency evidence recorded in SPORTS_CAVE_OS_RELEASE_2026-10-11.md. Fresh checks on this isolated production-based selection: 66 Python/native PostgreSQL tests passed without skips, plus three JavaScript component scripts. Coverage: unavailable/intermittent IMAP, bounded recovery, durable drafts/attachments, ambiguous SMTP outcomes, restart/idempotency, partial search, ambiguous bulk writes and real signed-session revocation. Synthetic transports only; external network prohibited in tests. Topology and whitespace checks passed.

Existing mailbox configuration, SMTP transport, IDLE lifecycle, connection budgets and recovery controllers are unchanged. No schema, grants, security configuration, Render topology, provider credentials, DNS or ticket changes. Existing unknown sends must never be replayed. No real mail is sent for verification.

Provider-dependent acceptance remains on hold: receiving fresh mail from Render, real SMTP acceptance/delivery/Sent-copy reconciliation, provider-specific search and MOVE/COPY/UIDPLUS behavior. Existing actions retain connection/capability checks and conservative error handling; publishing their tested UI is not a claim that the unavailable provider works. Cached mail and drafts remain useful during outages. All-folder search stays bounded and explicitly partial; bulk results confirm individual messages only. Physical mobile, Safari and Firefox acceptance remains outstanding.

Deploy by pushing this exact reviewed commit to existing GitHub main; all four canonical Render services auto-deploy. No Blueprint sync or new service. Verify all four live revisions, health and authenticated Inbox UI after rollout. Preserve ticket VIP-R2695883 for investigation.

Rollback target: ccb63e87e385164d6b62298889a26fc6d1ab2512. Preserve durable drafts, attachments, frozen outbox operation IDs/MIME, unknown results, accepted receipts and database schema. Never reset the shared dirty checkout or clear queues. Future releases require fresh authorization.
