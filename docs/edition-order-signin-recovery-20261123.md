# Edition order sign-in recovery — 23 November 2026

Task: 20261123-6659bf5b. Owner: codex-editions-20261123-recovery.

## Diagnosis

Order #SC3542: allocation 976 (Don Mattingly, 034/100) and 977 (Derek Jeter, 055/100).
Both allocations and retained numbered JPGs existed. Prodigi preparation stopped before
Save/product-selection permits: worker tabs redirected to the same supplier login page,
but the extension reported “The worker order tab changed before wake-up.”
The durable queue placed both units in Needs review and correctly preserved write fences.
The owner signed back in during this incident. Both units were reset through the existing
Orders controls, retaining supplier order and exact item IDs; no SQL state bypass was used.
Completion must be verified separately; queued is not done.

## Source dependency and focused fix

Studio approved base 7869c263 predates the running companion. Read-only Render discovery
verified production commit daec97e570fb6abcbff7a9245c798a64ff6f92e9.
windows-upload-companion/prodigi-browser.js prodigi_product_browser.py and prodigi_browser.py were explicitly transferred from that
committed production revision into this isolated task before editing. No unfinished task
source was copied. Review this incident delta against daec97e5, not the old Studio base.
The file is not an independently releasable downgrade of the running extension.

Recognize only the exact supplier-origin login redirect for the pinned order. Fail early
with an actionable sign-in message and signin receipt stage. Reuse the existing owned
order tab after sign-in; avoid opening duplicate login tabs. Keep foreign URL, ownership,
checksum, source and supplier Save fences strict. Session expiration itself cannot be
prevented by the companion, and login remains a user action. Release was explicitly authorised by the owner during this incident.

## Validation

- node --test tests/test_prodigi_signin.cjs: 6 passed, offline mocked browser APIs.
- Existing deployed tests/test_prodigi_browser.cjs with matching deployed helper modules
  and the patched browser file in an isolated temporary fixture tree: 47 passed.
- node --check windows-upload-companion/prodigi-browser.js: passed.
- git diff --check: passed.
- python scripts/validate_render_topology.py: passed; no topology changes.

Owner explicitly authorised commit, push/deploy to existing services, and companion update.

## Verified product selection after Reset

Live recovery revealed a second issue: Reset pins the whole supplier draft before a
blank product is selected. Successful authorised selection updated the item SKU/frame,
but its reset authorisation still pinned the blank item. Both sibling upload claims
then correctly rejected the stale whole-order snapshot. Recovery uses serial resets
through normal controls after product selection, never edits to supplier receipts.

The local product completion fix advances the reset snapshot only after independent
readback proves the consumed product-selection permit, canonical product, unchanged
business fields, exact reset generation/order/item, unchanged assets and unused reset
authority. It does not mint new reset authority or weaken supplier Save checks.

- python -m unittest discover -s tests -p test_prodigi_reset_selection.py -v:
  4 passed, covering successful handoff, replay, unrelated mutations, stale/used/misbound
  resets and ordinary selections. AST-isolated actual state-machine functions;
  no application startup, provider calls, credentials or live data in tests.

## First calculated sibling prices

Mattingly reached a permitted Save and the supplier shows its JPG as Excellent. The
readback correctly recorded only items[1].unitPrice and items[1].lineTotal as different:
saving the first artwork also populated previously missing sibling prices. The local
fix allows newly calculated finite nonnegative money values with a canonical currency
only after Save, only on previously unpriced siblings. Existing currencies and extra
money metadata stay pinned. No supplier charge or payment is authorised by this check.
Five isolated actual-function tests cover the first-price case and rejected unrelated
mutations, currency changes and malformed money. The consumed Save must be read back;
never reset it or repeat its upload to work around a verification failure.

## Release authorisation and baseline

The owner answered “Yes—commit, deploy and update companion” to the explicit scoped
release question. Integrate only these reviewed changes onto the verified remote main
commit daec97e5; preserve every other task. Companion version: 1.7.52.

## Shared-order verified sibling readback

After the second unit was saved, the first unit's earlier whole-order snapshot also
saw that legitimate sibling artwork change. The release now accepts that artwork/fit
transition only if there is exactly one durable sibling handoff for the same supplier
order/item, its own Save was permitted and verified, its current allocation/source is
unchanged, and its current supplier original asset/bytes and full-image fit still
verify against that pinned JPG. Every other business field remains pinned. The sibling
read is enrolled in the same optimistic transaction boundary so concurrent changes
invalidate the result. This path performs reads only; it cannot replay a Save.

Five isolated actual-function tests cover this boundary. Ten disposable-PGlite
integration cases pass against real handoff/permit/readback persistence: first-price
population, rejected currency/quantity/artwork changes, stale Reset generations, and
verified versus unverified sibling Saves. All new cases are included in the release
gate. The initial broad gate was stopped before release to include this new evidence
and rerun the complete final revision. No partial suite was claimed as passing.

Companion 1.7.52 manifest and browser worker were backed up and installed into the
existing local installation; both SHA256 hashes matched tested source. The owner
reported Reload complete. Runtime version must still be observed after polling.

The observed saved-artwork mismatch is now eligible for one automatic read-only
reconciliation on the existing desktop poll. Only persisted Save receipts with the
known item artwork/fit/price structural changes qualify. Fresh source, target,
checksum, whole-order business and verified-sibling checks still run. Unverified or
changed artwork stays blocked, no permit is generated and the counter prevents loops.
Disposable-database tests prove successful and rejected recovery and duplicate polling.

The release preserves the concurrently approved collection/certificate release by
rebasing onto current remote main; the task never edits another task checkout.
Companion 1.7.52 was observed in the server runtime record after owner reload.
