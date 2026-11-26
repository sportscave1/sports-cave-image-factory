# Edition recovery — 27 November 2026

Task `20261126-c1ee5b85`; owner `codex-edition-recovery-20261127-3ea57b70`.
The user explicitly requested diagnosis, repairs and pushing the changes live.
Nathan's Render workspace was separately confirmed. The task fast-forwarded
from Studio's approved base to verified live/remote main `6479c268` before edits;
other tasks and installed Companion customisations remain preserved.

## Recorded causes

- SC3572, allocation 1006, edition 094/100, existing supplier order
  `75496446719197184`: image-processing failure, one pre-Save recovery, then a
  15-minute browser handoff timeout. The receipt misleadingly said `artwork.open`
  while independent runtime progress remained `uploaded` for about 920 seconds.
  Save was never permitted and readback reported no changed business fields.
- SC3574, allocation 1008, edition 032/100, existing supplier order
  `75503070205325312`: the same sequence and same unrecognised interruption
  message. Both retained supplier tabs showed an Uploading image-library dialog
  with an exact numbered JPG tile. On waking the Warne tab its editor advanced
  to an Excellent image, but no Save was performed during diagnosis. These
  observations establish stalled browser processing; they do not establish the
  supplier's internal reason for its busy flag or the browser's timer freeze.
- SC3573, allocation 1007, edition 002/100, existing product
  `gid://shopify/Product/15506061033779`: request stopped with “Link the PSD
  using the existing Add workflow first.” No mapping or onboarding row exists.
  Its exact PSD is Dropbox file `id:u1tYiAa2O-AAAAAAAADJcw`, revision
  `016610a4a166dad000000036d367e13`, in the retained PSD review folder. The
  associated Product Uploads handoff ended at stage 7 with an APPROVAL failure,
  so publication had not completed the PSD mapping handoff. The PSD contains
  embedded ICC, an editable `SC_EDITION_NUMBER` (001 / 100), and plaque layer.
  The user subsequently approved the exact copy/link recovery. Dropbox copied
  the source to the existing main PSD folder as `id:u1tYiAa2O-AAAAAAAADKYA`,
  revision `016613632afde16000000036d367e13`, without creating folders. Both
  41,810,193-byte files have SHA-256
  `19e208765a0809abb0534c3aa16337a64c5a9c5c201d5f1c60d692d75b3b6b8f`.
  The original source and its review notes remain retained. The authenticated
  Add / Save PSD workflow linked the copy to the existing product at
  `2026-11-26T23:21:49Z`, recording the normal mapping audit and enqueueing
  preparation. No direct database mutation, new listing or edition reallocation
  was used.

Fresh read-only Photoshop inspection of an isolated copy successfully opened
the Kirill PSD and resolved both standard edition roles, reference 1/100 and
Cinzel-Medium. Original and staged Dropbox content hashes remained identical.

The approved Kirill copy completed native preparation on its first attempt and
reached Cloud Ready at `2026-11-26T23:26:31Z`, preparation
`a648f6d9c0c8e90951d83fc522a255a3814ca8b06a9efaa32973577433a1282d`.
Both existing Kirill allocations, 1000 (001/100) and 1007 (002/100), then
generated their numbered JPGs and entered fulfilment. The retained missing-PSD
failure for 1007 became inactive automatically at `2026-11-26T23:28:40Z`.

## Recovery changes

The pre-Save recovery recognises interrupted/closed browser responses and the
new processing-watchdog error. It independently rechecks the current allocation,
source, supplier target, empty asset slots and full business snapshot before
retiring the old token. It reuses a library original only after matching unique
identity, byte count, dimensions and the full file checksum. Consumed Save and
submission permits, changed business fields and unknown errors remain fenced.

The browser tracks content progress instead of reporting every message timeout
as `open`. A service-worker watchdog wakes only the exact owned order tab once
after a minute in image processing and yields after three minutes even when
content timers stop. It cannot issue an upload, Save, reset or submission.
Navigation/ownership loss remains distinct from an unchanged-page interruption.

Only an independently proven unchanged pre-Save wait shows “Recovering artwork”
in Orders and the Companion header. Its retry remains durable. Failed fresh
revalidation removes that projection and retains the real review state. This
does not hide unknown failures or claim that future supplier failures cannot
occur. Companion package version: 1.7.60; no new permissions or service topology.

Live follow-through found one additional restart case: the older worker resumed
SC3572's persisted handoff without completion evidence as a bare `readback`.
Save was false and the independent changed-fields list was empty. Recovery now
recognises only that exact legacy failure signature before freshly checking the
source, full business state and empty artwork slots again. New worker restarts
explicitly report the interrupted artwork handoff; recorded completion evidence
and other handoff kinds retain their existing readback path. A consumed Save,
submission/document intent or changed/hidden order cannot enter this recovery.

## Verification and rollout

Focused recovery checks: 85 Python tests passed before the status projection;
the added projection and automatic-JPG checks subsequently passed (5 tests).
The complete browser release set passed 219 tests, zero skips. Changed Python
AST, JavaScript syntax, whitespace and Render topology checks passed.

The final broader Orders gate passed 651 Python tests and 33 subtests, zero
skips, using disposable PGlite with synthetic fixtures. It includes customer
holds, source/target fences, consumed-Save recovery, QA, submission, grid/header
reads and the release-package contract. Its only warning is the existing
Starlette TestClient/httpx deprecation. Test-run hashes pin the unchanged final
source files; the release evidence retains the full commands and logs.

The restart follow-up passed 102 Python recovery, consumed-Save and package
checks, and 91 browser/sign-in checks, with zero skips. SC3574 subsequently
completed artwork verification and every dashboard QA check, then its existing
configured submission flow confirmed supplier status `on_hold`. This is a
submitted-order receipt, not confirmation of payment or production.

## Verified closure

All three requested orders have verified original artwork bytes, full-image fit,
every dashboard QA check and a confirmed supplier submission. The source repair
also recovered the earlier Kirill allocation without reassigning its edition.

| Order | Allocation | Edition | Supplier order | Confirmed outcome |
|---|---:|---|---|---|
| SC3572 | 1006 | 094/100 | 75496446719197184 | Submitted; supplier `on_hold` |
| SC3573 | 1007 | 002/100 | 75500980680593920 | Submitted; supplier `on_hold` |
| SC3574 | 1008 | 032/100 | 75503070205325312 | Submitted; supplier `on_hold` |
| SC3565 (same Kirill source) | 1000 | 001/100 | 75464595871964672 | Submitted; supplier `on_hold` |

SC3573's final receipt was independently read at `2026-11-26T23:40:00Z`.
Supplier hold is distinct from payment or production confirmation; certificates
continue through the existing finalisation workflow. No manual supplier Save,
payment, hold release, extra primary service or Blueprint sync was performed.

Runtime hardening is deployed in `52aab1ac` and `30e0da04`; installed Companion
1.7.60 is active. The final repository follow-up records the approved source
repair and closure, with no additional runtime behaviour change. Deployment
identities, health checks, immutable source/JPG hashes, test results and final
order receipts are retained in the Studio task evidence.

Exact-commit verification, production rollout, installed extension activation
and per-order outcomes are recorded in
the Studio task/runtime evidence. A queued repair or successful deploy alone is
not an order-completion receipt. No infrastructure sync or new service is needed.
