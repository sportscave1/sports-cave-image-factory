# Auto Editions: Barry retry and reference sizing — 24 October 2026

Task: 20261024-a085057b; owner: codex-editions-20261024-barry-quality.
Branch: codex/task/editions-auto-editions-barry-sheene-block-and-consi-20261024-a085057b.
Baseline: deployed 131d0fa6d9bffa2d9ce63c14048c42355071e6f1. Changes below are LOCAL, uncommitted and not deployed.

## Barry: actual recovery evidence
Product 162, gid://shopify/Product/9747626754355; Dropbox id:u1tYiAa2O-AAAAAAAAAApA.
Original 15 October 15:33:00.784963 UTC failure: Exactly one visible, editable edition-number layer is required.
The original failed revision was 0165da1bc772469000000036d367e13.

The user explained that the VA replaced the PSD without refreshing the selected source and authorized a targeted normal retry. No unmapping or edition-run reset was performed.
The first current-source retry used revision 0165e8bd87797ad000000036d367e13, 242,534,423 bytes, Dropbox hash c4c767b9585651f1cdac549b028ab69182fcce054b6d3d77f1e532b6925c8619.
It passed editable-number/plaque layer detection, but native preflight failed: non-opaque alpha (238–255). Exactly 5,403 pixels were partially transparent, confined to the first and last canvas rows.
The VA was asked to correct the visible artwork edges, preserving the design, dimensions, layers and ICC.

After the user confirmed correction, Dropbox showed revision 0165e8c9c6d93be000000036d367e13, 242,594,873 bytes, server_modified 2026-10-24 02:11:13 UTC.
Normal guarded retry initially refused while the previous lease had no fresh idle Companion heartbeat. The existing Companion recovered its transient ConnectionError automatically.
Retry then succeeded in queueing/claiming at 02:15:06.615443 UTC, using the corrected revision and hash ea9e7191fa3c9d938c5d9cfc343f644c40be3649151aa049c049aa1e981f5b2e.
Local job: 4c6e8ec26cc9d001bf5fd70450d173d1f53b59b0cd7d5db4.
It stopped during Photoshop inspection at 02:15:38.915645 UTC with "Photoshop method unavailable" (IDispatch DoJavaScript lookup), before native PSD validation/preparation.
Photoshop was responding, with an unsaved Untitled-1 document. User was asked to finish active dialogs/tools and confirm idle. No documents were closed or altered.
That inspection attempt did not verify the corrected edge pixels and produced no package or receipts. It was superseded by the successful normal recovery below.

Preservation baseline: edition total 100; next number 60; last assigned 59; sold 59; active run b1917884-0db4-410e-a657-932dc67af0fc; mapping timestamp 2026-10-12 21:27:40.519910 UTC. Recovery must preserve these.
Read-only production verification after the second attempt confirmed every one of these values unchanged, status Blocked with the Photoshop inspection error, preparation_hash null and preparation_count 0.

### Actual final recovery — 24 October, 14:45:59 Sydney time
After the user's follow-up, a read-only Photoshop scripting probe returned version 27.11.0. Normal Retry queued the same product at 03:29:15.328296 UTC and the Companion claimed it at 03:29:39.785565 UTC, without changing installed code or production settings.
Local job d08001952a90d631091a9b357278ccf623deaaa00300d361 used corrected revision 0165e8c9c6d93be000000036d367e13 and the ea9e7191... content hash recorded above.
Both native 2835 × 2004 preflight exports are opaque RGB. The existing approved preparation produced 11340 × 8016 pixels at 4×, with source_modified=false, pixels_converted=false and tagged ICC SHA256 2b3aa1645779a9e634744faf9b01e9102b0c9b88fd6deced7934df86b949af7e.
Package size: 120,109,126 bytes; 106 ZIP entries, including all 100 number patches. The normal bounded resumable upload completed with server-confirmed chunks; no transfer limits, speed settings or readiness rules were changed.
Final authoritative state is Cloud Ready at 2026-10-24 03:45:59.421632 UTC (14:45:59 Sydney), preparation a8dab975dc985a1e430d398a3df06d67eebde0cc2d00ad5367410bda274c4b74.
Verified 101 receipts, 101 distinct names and 101 distinct cloud file IDs, all with revisions and positive byte counts. Matching technical check Succeeded; local receipt says Cloud assets independently verified; local state Prepared, no error, checkpoint_pending=false.
Final database recheck confirms the original mapping timestamp/file ID, active run, total 100, next 60, last assigned 59 and sold 59 unchanged. No customer edition allocations advanced.
Cloud Ready is not a claim of Production Ready or supplier Excellent certification. Existing production-readiness requirements remain in force. This live recovery used deployed 131d0fa6, not the local quality-policy changes.

## Proven quality discrepancy
| Design | PSD pixels | Prepared pixels | Historical policy | Cloud evidence |
| --- | --- | --- | --- | --- |
| For Brock Bathurst 2006 (product 394) | 2362 × 1670 | 9448 × 6680 | 4× | 101 receipts; prep 3615e0dd7038aed390c245e6c718a0b20a2c2006364563845e96a21ecfcdac44 |
| Kostecki & Hazelwood — The Final Lap #17 (727) | 2835 × 2004 | 11340 × 8016 | 4× | 101 receipts; prep 5329ce4506f019b94465abbe8bf2248235300f4b20cd15b6c6e24e635c195986 |
| Shane Warne — The Final Bow (737) | 2835 × 2004 | 11340 × 8016 | 4× | Cloud Ready 24 October 01:03:29.176709 UTC; prep 17e38391c475ce4f422832868809c58f5bc1a3aff1eb8e03515a8c905973e952 |

The screenshot is For Brock edition 008/100. Its real Ready download job 32c2022c508b07f4337e3f541e7ca3e295da96514e25018040f982a6d7453242, order #SC3357, XL Black, records 9448 × 6680 pixels and 300 DPI metadata. The displayed supplier canvas is 9933 × 7016 and scale 105.13%.
The smaller source under the same fixed multiplier explains the smaller output. DPI metadata did not add pixels. This is not evidence of a lower JPEG encoding setting.
The historical package is immutable and has not been regenerated or changed.

## Local repair
- Add versioned owner reference raster floor for verified GLOBAL-CFP-A1 at 11340 × 8016, citing the exact reference preparation.
- Retain proportional layered Photoshop resize, existing encoders, ICC, layer/plaque positioning, opacity proofs and readiness checks. No source PSD modification.
- For Brock's proportions require 11340 × 8018 (not a stretch to the reference's slightly different aspect ratio). Existing 2835 × 2004 successful designs remain 11340 × 8016.
- Preserve the 95,000,000 pixel worker bound and bounded resumable transfer. If target exceeds it, retain an explicit below-target status; do not claim quality success or raise the limit.
- Include the product's cached Shopify variant titles as well as past order variants, matched only by exact normalized product ID. New products do not require a sale to get the correct sizing context. Real cached records for Barry and Shane contain all 16 variants.
- Unknown/unverified product families do not silently inherit A1 assumptions.
- Version and bind geometry/policy into package generation, preventing stale smaller preparation reuse for new preparations. Continue validating historical manifests.
- Expose the reference sizing in resolution evidence, explicitly stating it is not supplier Excellent certification or proof of native detail.

This can enforce a raster-size floor for supported mapped products; it cannot make low-detail source art intrinsically sharp or certify the supplier's current Excellent label. Supplier crop, bleed, native detail and physical proof approval remain required. Larger pixel dimensions alone are not production readiness.

## Changed files
auto_editions_preparation_geometry.py; data/auto_editions_preparation_quality.json; auto_editions_onboarding_api.py; auto_editions_resolution.py; companion_package_identity.py; tests/test_auto_editions_fractional.py; tests/test_auto_editions_resolution.py.
The resolution preservation test baseline was corrected from an outdated pre-release hash to current released 131d0fa6 (including its approved plaque-copy fix).

## Validation
Local/offline PostgreSQL/PGlite, Pillow and localhost HTTP checks:
- Fractional/reference sizing, resolution protection and large/resumable packages: 60 passed in 20.45s.
- Onboarding API/store, Companion preparation host and guarded Worker Health retry: 63 passed in 56.91s.
Two dependency deprecation warnings per run; no failures.
Coverage includes new products without orders, duplicate/mixed-ID variant metadata isolation, global shared-master sizing, orientation/aspect rounding, unchanged existing success dimensions, historical manifests/cache invalidation, pixel/ICC/encoder proof fixtures, and interrupted oversized HTTP transfer/restart/single import.
These are not a live native Photoshop export of the new quality policy, a memory benchmark of that export, supplier certification or deployment evidence.
Studio static/secret/whitespace/identity verification passed. Task remains uncommitted; integration readiness is false. The verified task includes the already released baseline changes relative to its older Studio base; only the eight files listed in this report are new local modifications.

## Concrete next actions
1. Barry targeted recovery is completed and verified above. Do not bulk-retry unrelated backlog or regenerate Barry again.
2. Owner authorization is required before committing/pushing/releasing the LOCAL quality policy.
3. Release the exact reviewed commit to existing primary sports-cave-os and its existing worker; update the Auto Editions Companion to the matching immutable release. No topology, unrelated workflow or recorder changes.
4. Because preparation generation changes, run the required isolated matching-generation resumable acceptance, including boundary/interruption/integrity checks. Do not reuse the old d5e8adaf generation acceptance.
5. Perform a native corrected-source/reference preparation comparison and resource check within 95 MP; retain readiness holds pending required visual/supplier proof approval.
6. Existing For Brock assets/orders stay intact. A deliberate targeted re-preparation of its current source requires approval and normal replacement/acceptance controls; do not regenerate customer editions or advance allocations.


