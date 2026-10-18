# Ordered-design recovery: 18 October 2026

Existing task: 20261017-37907e10; owner codex-01a14756-post-upgrade-20261018.

The owner narrowed recovery to products ordered during the audited 12-month window. The full Shopify audit read 1,325 orders and identified 163 current product IDs: 43 already verified and 120 outstanding. This release pins that scope for automatic backlog admission. Existing manual controls remain available. Historical lines without product IDs remain identity review cases.

## Shared changes

- Recognise and preserve the existing No. prefix consistently in Python validation, Photoshop inspection/preparation and export proof. Count both number candidates when present; never silently choose one.
- Resolve selected artwork roles from exact source identity plus existing layer ID, name, type and bounds. Native validation rejects changed, duplicate, nested or stale targets. Nine source-bound records reuse existing collector graphics and editable fields. The final read-only batch added Final Crown Messi, Called Shot Babe Ruth, Bird/Johnson, Anthony Edwards and Kobe's motivational quote; all retain valid embedded ICCs. This is role metadata, not a replacement template or source PSD change.
- Support streamed PSD input up to 2 GiB, with three source copies of disk headroom plus 5 GiB scratch reserve. Retain source checksums, 4 MiB streaming, pixel budget, output/package limits and all colour/profile gates. Only known old 1 GiB input-cap failures become eligible; output-size failures remain blocked.
- Restrict automatic admission to audited ordered product IDs. Preserve queue priority bands; use annual order counts within each band. Source-bound role fixes receive one attempt; unchanged font/range problems do not gain retries merely from a role record.
- Historical generic Photoshop/worker errors and old HTTP transfer failures may receive one fresh guarded attempt only while the authenticated Companion has the current full revision/code hash, a fresh healthy heartbeat, and no retained lock/checkpoint. Missing colour provenance still blocks export. Package-size failures are eligible only if they predate the approved lossless compact transport; current expanded-package and pixel limits remain enforced.
- Temporary admission contention/provider failures use three capped backoff attempts separately from the native-render budget. A busy queue never consumes the sole native attempt. Deterministic source/guard failures remain capped and do not loop.
- Worker Health uses actual verified technical completion for its last-completed signal and includes automatic colour-recovery evidence in the historical colour counts. Discovery, admission and retained uploaded packages do not become completion signals.

## Source evidence

Read-only staged PSD review inspected root layers, groups and embedded smart objects through depth 2. Cached composite previews are review aids; Photoshop remains the preparation authority. Evidence lives outside Git under .studio/release-evidence/companion-backlog-20261018-37907e10/ordered-recovery-20261018.

The Mentality has one visible editable #093/100 layer (246) and a separate central plaque smart object Generative Fill (267). The full signature strip is not selected. Messi/Ronaldo has one visible editable No. 001 / 100 layer (308) and its central plaque Layer 2 (307). Each source is content-hash and revision bound in the role registry.

The owner selected labelled E (`No. 027 / 100`) for Kobe/Jordan. The disposable Photoshop document hides only the exact obsolete A field; the PSD is never saved. Both local preparation and server package ingestion independently compare the before/after export outside its existing plaque. Changed source revision, layer identity, bounds or unapproved extra number layers fail closed.

Gaethje's current native inspection and labelled composite identify the separate root `LIMITED EDITION` smart object (458), containing the sole `001 / 100` text layer (456). This exact source now uses the same role-evidence mechanism; the full-artwork Layer 9 is never selected.

The owner approved matching Mentality's existing black-backed production export after verification. The current source over black matches production reference `id:u1tYiAa2O-AAAAAAAAAruw` (SHA256 `9a88dbf5a5544c551ba69981f7d60d9cd751e96685fe11f0b68329e981069708`), outside-number MAE 0.395 and RMSE 1.175. Only this exact source may composite its RGBA exports over black. Embedded output ICC bytes remain identical. Unbacked exports and Kobe's before-correction export are kept outside temporary cleanup directories. No general alpha flattening is enabled.

Six Laps Ahead retains its blocker: its plaque is embedded in larger artwork and no independent root plaque was guessed. Jackie Robinson's current original has no editable text layers. These need suitable approved layered originals.

Historical missing/invalid upload receipts no longer prevent a safe fresh native export when source identity, approved colour provenance, editable roles and pixel proofs validate. This admission returns repair-only evidence, never a completion certificate. Old packages and receipts remain preserved. Every replacement still needs new independently verified cloud receipts before Cloud Ready.

Shane Warne: registered existing approved RGB8 workflow membership after verifying the current PSD bytes and an independent tagged production export (#024). Reference ICC SHA256 is 2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e. Outside the edition-number mask, raw RGB source versus downsampled JPEG reference MAE=0.541 and RMSE=1.463. The approved policy is fac7ff72ed00e370365ca269e86f763057faa32df988450c7780fcaa774b287e. Original creator intent is not claimed. The original remains untagged and untouched; only the guarded staged export may apply that policy. Queueing is not completion.

## Validation and activation

### Existing mapped filenames during repair

Source-pinned export repairs reuse their existing approved mapping even when a product display title differs from its original PSD filename. The repair and host-context paths check the full unchanged mapping, exclusive source ownership, retained preparation generation, approved original location, revision and content hash. A failed discovery with zero native attempts can reuse its existing request ID through the same guarded Retry service; it does not remap a product or certify the old exports. Ordinary reset/rematching retains the original filename rules, and the three-attempt native cap is unchanged. This resolves Dale Earnhardt/Jeff Gordon's historical `Not linked` replacement without renaming its PSD or product.

The Worker Health queue selector exposes that same corrected failed-replacement retry after explicit correction acknowledgement. Retained successful packages without a failed replacement remain protected. The selector only reports availability; submission still runs the full locking and source/checkpoint checks in `Reset.retry_failed` and preserves the replacement operation ID.

Black Caviar/Winx already has an owned queued replacement. Michael Dunlop remains separate: the current original is untagged RGB8, its historical revisions contain the same bytes, and the found 1,000px lifestyle mockup is also untagged. It does not establish the existing approved colour policy's scope. No automatic profile assignment or repeated retry is permitted until an original embedded profile or independent verified workflow/production-export evidence is supplied.

Initial focused suite: 91 passed against disposable PGlite (no production providers). New role/parser/size/scope checks: 17 passed; scope SQL regression and combined revision checks recorded in external release evidence. Render topology validation passed. Tests isolate host capabilities and never touch the registered Companion host.

Merge the exact tested change with the current live 5af8499e application revision, preserving Product Uploads additions. Release only to existing sports-cave-os and sports-cave-seo-worker. Update Companion from the immutable tested revision only when no preparation, pending checkpoint or processor lease remains. The automatic scanner then admits eligible scoped jobs once under the existing guarded service. Do not mass-requeue blocked artwork. Confirm completion only from current source-bound export proofs, profiles and cloud upload receipts.
