# Orders companion full Reset - 1.7.32

Reset replaces the old QA-only Restart in the compact Orders review panel. It creates one new preparation generation for the same allocation, edition and supplier item. It resolves the current source, verifies/selects the canonical product when blank, reuploads the current numbered JPG and runs fresh complete QA. It reuses a retained JPG when current; a missing/current-master JPG is enqueued through the existing edition worker.

Old preparation receipts are archived under prodigi_reset_history before the active record is replaced. Their browser/product/QA tokens cannot permit writes or overwrite the new generation. A repeated Reset request while the untouched generation is queued returns the same generation. Grouped QA receipts are retired on sibling units, preserving their saved artwork and requiring fresh whole-order QA before the existing shared submission fence.

Existing supplier artwork is preserved until a replacement is ready to Save. Only an explicit reset generation, exact supplier business/asset snapshot and current numbered source can authorise replacement. Older companion versions cannot claim a replacement. The native editor remove-image affordance is read from its separate rendered transparent control canvas; ambiguous/tainted controls stop before Save. There is no live artwork API PATCH. A fresh supplier readback and source checksum precede Save, followed by the normal independent asset/fit/edition verification.

Reset rejects every submitted/uncertain submission, order-wide submission fence, charged/production/shipped order and uncertain in-flight Save. It never creates a supplier order, removes an item, changes the supplier countdown, resumes production or pays an order. The existing owner-authorised initial Submit after all QA passes and later production/certificate reconciliation remain in place.

Newly QA-passed drafts take priority over passive countdown polling. A blocked multi-item draft has a bounded submission-check cooldown, so it cannot monopolise that priority. New-order admission remains automatic in existing bounded batches; failures requiring a PSD mapping/repair or supplier correction are surfaced instead of silently retried.

Validation before release: 179 full focused Python tests passed, plus 32 tests after submission-priority/display changes (two additional cases; 181 unique Python cases), and 36 Node tests. Native replacement acceptance and the three remaining live orders are monitored after deployment; do not infer live success from these offline counts.

Live Reset acceptance found the editor dialog can precede its SKU label and image-control canvas. Companion 1.7.32 waits for the exact SKU, saved image details and a fully drawn native removal control. A delayed-hydration regression test passes; this change leaves the guarded Save/readback protocol intact.

## Final live acceptance and server handoff review

SC3529, SC3530 and SC3531 all completed full preparation and reached Submitted with 13/13 dashboard QA checks. SC3530 reuploaded its saved White/XL artwork after the late-editor fix; its QA record was committed before the initial submission intent. Existing submitted orders were not reset. The owner confirmed supplier preferences exclusively control the edit window: do not query its duration or add any duration-dependent automation.

Server-only optimisation reuses the independently verified upload readback for QA queue admission, then revalidates live state again when QA is claimed/permitted and before submission. This removes a redundant order/source read and an intermediate preparation poll. Ready QA is served before another large upload. A successful QA-finish callback wakes the existing owner-gated submission worker immediately, preserving its durable order-wide fence and all-item barrier. The periodic workers remain recovery fallbacks. Companion 1.7.32 needs no reload for these server changes.

Validation for these handoffs: 137 focused Python cases passed, followed by 42 browser/handoff cases including an additional live-context upload-completion test (138 unique cases across those runs). No duplicate live test was performed on the already-submitted SC3530. All client files remain the accepted 1.7.32 release.

Suggested later phases: reuse the same pinned supplier tab for upload and saved-order QA; update only changed Orders rows and expose concise stage timings in backend diagnostics; evaluate repeat-customer consolidation separately. Cross-Shopify-order merge/cancellation remains unimplemented and disabled, as recorded in PRODIGI_ORDER_GROUPS_20261122.md.
