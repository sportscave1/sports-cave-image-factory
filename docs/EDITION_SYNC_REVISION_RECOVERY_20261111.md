# Revised PSD handoff and product receipt recovery

Task: 20261111-35ee70f6. Owner: codex/edition-sync-20261111.

## Findings

A mapped product was excluded from discovery even when its Dropbox revision changed.
Its retained Cloud Ready preparation still described the previous revision. The final
technical layout replacement also permitted only unchanged source identities.

Chaz Mostert product 15479046668595 has authenticated products/update receipts from
2026-11-11 01:05–01:07 UTC. The receiver is healthy. The worker is processing older
receipts; 474 product deliveries were still received and 362 pending during inspection.
The reconciliation checkpoint was still in the 2026-11-10 23:24–23:48 UTC window.
Synchronous per-product processing inside that scan and the undifferentiated retry
order delay newer uploads. Shopify throttling was also recorded in recovery receipts.

## Additional rules (existing safeguards retained)

- A changed mapped original wakes discovery; verify its current permanent ID,
  revision and content hash before queuing a replacement.
- Retain the current generation, mapping, allocations and certificates while preparing.
- Never override a mapping hold, manual reset, deferred priority or owned operation.
- One replacement per observed revision; a failed revision does not gain unlimited retries.
- Recheck mapping ownership and exact source at package import and final verification.
- Only an unrestricted automatic TEST layout can be superseded, with a new technical
  certificate and an audit of the retained approval. Visual/production approval,
  variant restrictions and allocation allowlists cannot be inherited or broadened.
- Store reconciliation receipts before advancing the scan checkpoint. Process them
  separately with existing durable retries, so a poison product cannot pin the scan.
- Give fresh deliveries four processing slots for each retry/recovery slot. Preserve
  retry capacity, duplicate delivery protection, order-history and allocation checks.

## Release scope

No migration, infrastructure changes or additional Render services. Source changes
are local and uncommitted until explicit release approval under AGENTS.md. Deploy
only to the existing application topology after approved integration and checks.
After deployment, requeue Messi vs Ronaldo (10057331147059) through the audited
replacement flow and verify the current revision in Companion. Confirm Chaz Mostert
registration and its edition run using the existing received webhook receipts.

Two existing discovery tests used outdated expectations (exact claim response keys
and total worker thread count). Both failures reproduced with baseline discovery;
the assertions now check their intended contracts with the current interfaces.

## Validation

- Combined reset, discovery, onboarding and technical suites: 158 passed, 2 skipped.
- Latest discovery wakeup change: discovery suite 28 passed, 2 skipped; updated-source
  regressions 5 passed.
- Additional receipt-storage failure/replay regression: 1 passed.
- Render topology validator passed; git diff --check passed.
- Tests use synthetic isolated databases and assets. No production writes or deployment
  were performed. Live queue completion remains a post-release verification step.
