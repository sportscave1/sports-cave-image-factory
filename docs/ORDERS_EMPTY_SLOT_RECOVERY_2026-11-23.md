# Product selection after Reset

SC3543 stopped at `product_selection.product-readback`, before an artwork upload
or submission permit. Its original reset generation, order/item identity and
business snapshot were unchanged. The recovery budget for the previous policy
was exhausted.

The archived attempt stopped earlier at `product-select`: its durable permit
remained unissued (`started=false`, no permitted_at) and the page reported
"The blank item changed before selection." Render's primary service log confirms
HTTP 503 on `/api/orders-companion/browser/permit` at 11:09:13 UTC. The old
handler did not log the underlying exception, so its exact cause is unavailable.
New diagnostics record the phase, exception class and SQLSTATE, without exception
messages or request credentials. The unchanged blank was left stopped
until an owner Reset. This is a separate pre-permit recovery gap.

Prodigi creates a required empty print-area asset when a blank imported product
is selected. Reset had pinned `assets=[]`. Product readback already accepted
this empty slot, but the separate reset fence compared the lists literally and
rejected the legitimate transition. The earlier regression fixtures selected a
product without creating its asset slot, so they missed this supplier behavior.

The companion's server-side handoff now accepts that transition only after the
existing canonical mapping, consumed Select permit, unpaid editable draft and
whole-order business checks pass. It uses the existing strict empty-slot schema:
one default required slot, nonempty string ID, NotYetDownloaded, pageCount integer
zero, and exactly the five expected keys. A URL, extra metadata, multiple slots,
or any actual image remains blocked. Only the same unused reset generation can
advance. The observed asset identity is then pinned again before the upload's
one-time Save permit.

`supplier-empty-slot-readback-v2` lets receipts exhausted under the old policy
receive bounded independent readback. Recovery never replays a permitted Select or Save and
does not reset orders, create replacement orders, or mark QA/submission passed.
The same read-only proof also handles a lost Select acknowledgement: a correctly
selected product can continue, while an unchanged blank remains stopped without
another click.
For the known pre-permit failure only, recovery may retire an unissued handoff
after a fresh source/order read proves the exact original blank item and business
snapshot. It archives the receipt and revokes its token atomically before a new
claim. A consumed permit, changed blank, artwork, submission intent or exhausted
budget cannot enter this path. It shares the bounded two-attempt policy.
Diagnostic fields record structural paths and failed fence names, without
customer values, asset URLs or tokens. No extension reload is needed for this
server-side companion recovery.

Disposable database regressions cover all 16 canonical product mappings through
Reset, Select, empty-slot creation, old-policy recovery, upload claim and permit.
Negative cases reject attached/unknown assets, altered slots, stale or consumed
reset generations, destination, quantity and shipping changes. The release gate
also exercises existing upload integrity, QA, submission fencing, authentication,
worker recovery and fault-soak suites. This fixes the observed deterministic
failure; external authentication and supplier outages still require valid
access and successful verification before an order can safely progress.
