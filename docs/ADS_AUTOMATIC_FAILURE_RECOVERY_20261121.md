# Automatic ad failure recovery — 21 November 2026

Task 20261121-ea828333; owner codex-ads-autorecover-20261121.
The user explicitly requested automatic recovery through completion and a live release.

The prior release made failures visible but excluded failed jobs from scheduling.
This release resumes recoverable failures without requiring Play or Resume import.

## Durable recovery

Recovery uses the existing job in app_settings, with its original upload ID,
conversation, prepared folder, verified artifact receipts, response IDs, frozen
targeting and deterministic posting submission ID. No new database schema or
Render service is introduced.

Transient dependency failures and timeouts schedule the original checkpoint
after 60 seconds, then back off to a maximum of 15 minutes. Transient retries
do not exhaust into a terminal failure. Catalogue sync and recovery cooldowns
release the active queue slot so other ready jobs can proceed. Pause, Cancel,
Delete, permissions, pairing and the durable single-worker lease remain enforced.
Known older recoverable failures are picked up automatically. Unknown historical
failures and provider safety refusals are not silently reclassified as safe retries.

The six-hour generation limit and repair-message deadlines now start a recovery
cycle instead of abandoning a recoverable job. Collection first restores existing
original files. For an interrupted generation, a separately identified completion
message asks the saved chat to finish only the missing deliverables using its
original brief and reference, without replacing completed artwork or copy.
It explicitly prohibits retrying or rephrasing around provider safety rejections.

Repair Send permits remain one-shot. A lost acknowledgement never grants a new
Send. A later cycle may issue a new repair only after the previous message was
acknowledged and a different finished assistant response was observed. Two failed
repairs enforce a 15-minute cooldown. Bounded repair history is retained.

## Posting recovery

Failed posting rebuilds the original request from verified files and resumes the
same submission. The existing recovery service verifies saved Meta ownership,
paused state and the request fingerprint and reuses completed operation IDs.
An interrupted nonterminal ledger can be reserved only after 30 minutes without
progress and without a live lease or pending write intent. The SQL reservation
clears only the expired lease and preserves the original inputs, IDs and journal.

Unknown write outcomes are observed for reconciliation, never blindly replayed.
Completed, externally abandoned or live-leased jobs cannot be re-created.
Provider refusals, invalid inputs, revoked access and changed/deleted Meta objects
still require their underlying condition to be resolved; no implementation can
guarantee provider acceptance. Successful completion still requires all three
confirmed ads, created paused for review. The paired companion must be connected.

## Verification and release

Offline tests block production provider access. They exercise an initial transient
failure through complete posting with no operator action, a partial Meta failure
through three completed ads without duplicate campaign/ad set/ad creation, legacy
failed-job pickup, sustained retries, queue fairness, pause/cancel/delete, missing
deliverables, one-shot Send after restart, and real disposable PostgreSQL lease and
write-intent fencing. Browser contracts cover both restore-only and completion
messages, paragraph pastes, user drafts and response isolation.

Companion 1.7.11 adds the completion message contract. Deployment uses the existing
production main auto-deploy; no Blueprint sync or infrastructure changes are needed.
