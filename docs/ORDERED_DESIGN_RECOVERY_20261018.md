# Ordered-design recovery: 18 October 2026

Existing task: 20261017-37907e10; owner codex-01a14756-post-upgrade-20261018.

The owner narrowed recovery to products ordered during the audited 12-month window. The full Shopify audit read 1,325 orders and identified 163 current product IDs: 43 already verified and 120 outstanding. This release pins that scope for automatic backlog admission. Existing manual controls remain available. Historical lines without product IDs remain identity review cases.

## Shared changes

- Recognise and preserve the existing No. prefix consistently in Python validation, Photoshop inspection/preparation and export proof. Count both number candidates when present; never silently choose one.
- Resolve selected artwork roles from exact source identity plus existing layer ID, name, type and bounds. Native validation rejects changed, duplicate, nested or stale targets. The two evidenced sources are The Mentality Jordan vs Bryant and Legends Never Die Messi vs Ronaldo; both retain their embedded ICC. This is role metadata, not a replacement template or source PSD change.
- Support streamed PSD input up to 2 GiB, with three source copies of disk headroom plus 5 GiB scratch reserve. Retain source checksums, 4 MiB streaming, pixel budget, output/package limits and all colour/profile gates. Only known old 1 GiB input-cap failures become eligible; output-size failures remain blocked.
- Restrict automatic admission to audited ordered product IDs. Preserve queue priority bands; use annual order counts within each band. Source-bound role fixes receive one attempt; unchanged font/range problems do not gain retries merely from a role record.

## Source evidence

Read-only staged PSD review inspected root layers, groups and embedded smart objects through depth 2. Cached composite previews are review aids; Photoshop remains the preparation authority. Evidence lives outside Git under .studio/release-evidence/companion-backlog-20261018-37907e10/ordered-recovery-20261018.

The Mentality has one visible editable #093/100 layer (246) and a separate central plaque smart object Generative Fill (267). The full signature strip is not selected. Messi/Ronaldo has one visible editable No. 001 / 100 layer (308) and its central plaque Layer 2 (307). Each source is content-hash and revision bound in the role registry.

Kobe/Jordan has two visible editable number layers and remains blocked pending a labelled visual choice and preservation checks. Six Laps Ahead has its plaque embedded in larger artwork; no independent root plaque was guessed. No opaque background, plaque geometry or typography was invented.

Shane Warne: registered existing approved RGB8 workflow membership after verifying the current PSD bytes and an independent tagged production export (#024). Reference ICC SHA256 is 2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e. Outside the edition-number mask, raw RGB source versus downsampled JPEG reference MAE=0.541 and RMSE=1.463. The approved policy is fac7ff72ed00e370365ca269e86f763057faa32df988450c7780fcaa774b287e. Original creator intent is not claimed. The original remains untagged and untouched; only the guarded staged export may apply that policy. Queueing is not completion.

## Validation and activation

Initial focused suite: 91 passed against disposable PGlite (no production providers). New role/parser/size/scope checks: 17 passed; scope SQL regression and combined revision checks recorded in external release evidence. Render topology validation passed. Tests isolate host capabilities and never touch the registered Companion host.

Merge the exact tested change with the current live 5af8499e application revision, preserving Product Uploads additions. Release only to existing sports-cave-os and sports-cave-seo-worker. Update Companion from the immutable tested revision only when no preparation, pending checkpoint or processor lease remains. The automatic scanner then admits eligible scoped jobs once under the existing guarded service. Do not mass-requeue blocked artwork. Confirm completion only from current source-bound export proofs, profiles and cloud upload receipts.
