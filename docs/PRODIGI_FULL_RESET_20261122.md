# Orders companion full Reset - 1.7.32

Reset replaces the old QA-only Restart in the compact Orders review panel. It creates one new preparation generation for the same allocation, edition and supplier item. It resolves the current source, verifies/selects the canonical product when blank, reuploads the current numbered JPG and runs fresh complete QA. It reuses a retained JPG when current; a missing/current-master JPG is enqueued through the existing edition worker.

Old preparation receipts are archived under prodigi_reset_history before the active record is replaced. Their browser/product/QA tokens cannot permit writes or overwrite the new generation. A repeated Reset request while the untouched generation is queued returns the same generation. Grouped QA receipts are retired on sibling units, preserving their saved artwork and requiring fresh whole-order QA before the existing shared submission fence.

Existing supplier artwork is preserved until a replacement is ready to Save. Only an explicit reset generation, exact supplier business/asset snapshot and current numbered source can authorise replacement. Older companion versions cannot claim a replacement. The native editor remove-image affordance is read from its separate rendered transparent control canvas; ambiguous/tainted controls stop before Save. There is no live artwork API PATCH. A fresh supplier readback and source checksum precede Save, followed by the normal independent asset/fit/edition verification.

Reset rejects every submitted/uncertain submission, order-wide submission fence, charged/production/shipped order and uncertain in-flight Save. It never creates a supplier order, removes an item, changes the supplier countdown, resumes production or pays an order. The existing owner-authorised initial Submit after all QA passes and later production/certificate reconciliation remain in place.

Newly QA-passed drafts take priority over passive countdown polling. A blocked multi-item draft has a bounded submission-check cooldown, so it cannot monopolise that priority. New-order admission remains automatic in existing bounded batches; failures requiring a PSD mapping/repair or supplier correction are surfaced instead of silently retried.

Validation before release: 179 full focused Python tests passed, plus 32 tests after submission-priority/display changes (two additional cases; 181 unique Python cases), and 36 Node tests. Native replacement acceptance and the three remaining live orders are monitored after deployment; do not infer live success from these offline counts.

Live Reset acceptance found the editor dialog can precede its SKU label and image-control canvas. Companion 1.7.32 waits for the exact SKU, saved image details and a fully drawn native removal control. A delayed-hydration regression test passes; this change leaves the guarded Save/readback protocol intact.
