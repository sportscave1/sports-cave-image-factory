# Auto Editions V8 final: SC3287 XL TEST

This scoped continuation preserves the V8 queue, allocation checks, authenticated
Dropbox integration, PSD links, Photoshop fallback and manual supplier fulfilment.
No Prodigi API, schema migration, new service or storage system is introduced.

## Master and geometry

The SC3287 source is 2835 x 2004. A new one-time layered Photoshop Bicubic Smoother
4x preparation is 11340 x 8016, preserving the source aspect ratio. Existing
8505 x 6012 assets and the original PSD are retained. Independent Photoshop
references for editions 1, 5 and 100 match the compositor pixel-for-pixel; the
original composition outside the number region also matches. The new master
is 37,113,891 bytes. Its manifest records original 72 PPI preparation metadata;
JPG exports carry 300 PPI metadata and actual enlarged pixels. Neither the
prepared PNG nor JPG has an embedded ICC profile. Resampling does not recover
missing photographic source detail.

Master version: 5329ce4506f019b94465abbe8bf2248235300f4b20cd15b6c6e24e635c195986.
The live variant advertises 87 x 62 cm: 331.08 x 328.40 effective PPI at that
advertised size. This is not a verified supplier print area. Exact Unframed XL
SKU geometry, bleed, safe margins, colour requirements and print-quality approval
remain outstanding. All outputs stay TEST / NOT PRINT READY.

## Archived output and Orders

Generated JPGs are validated and automatically filed under the existing Dropbox
Auto Editions/Generated JPGs/[Order]/TEST directory. The human-readable filename
also includes the full immutable job identity, separating line items, units,
editions and master versions. Existing files are checksum-verified and reused;
conflicts never overwrite an archive. File ID, revision, Dropbox content hash,
SHA256, size, dimensions, master and exact order/allocation identity are retained
in the existing durable job result. Completed archives do not expire.

Orders keeps Download JPG, an inline Generating indicator, then Open. A window
reserved by the initiating gesture navigates to the authenticated Files location
after verified saving and download initiation. Popup denial leaves Open available.
Files selects the exact Dropbox file ID and its Download command uses the pinned,
checksum-verified full-resolution edition endpoint. No generation or artwork
preview modal is used. Subsequent Open requests resolve storage only; they do
not enqueue jobs. Missing/revised files fail closed with a compact retry message.
Old View bookmarks resolve to file locations. Changing approved master exposes
the new generation action while preserving access to retained historical jobs.

## Safety and validation

Cloud output rendering remains serialized, with a 95 MP input bound and 64 MiB
output limit. Existing Files plus Orders permissions govern both administrator
and Worker access; setup remains administrator-only. The SC3284 Photoshop path
is unchanged. No writes target PSD mappings, edition allocations, certificates,
Shopify orders or the manual historical archive. Render topology is unchanged.
Acceptance measurements and deployment evidence are recorded separately after
real cloud and live-browser checks complete.

Real Render validation on 14 October 2026 generated and re-downloaded #005/100:
35,690,518 bytes; SHA256
373f3a6723e3911273badf4c4b98d48e89dd376c4019adb26fc5a345ef349a4f.
Dropbox ID id:u1tYiAa2O-AAAAAAAAAtdg, revision
0165dc4577e9650000000036d367e13. Dropbox content hash
43dd03c9bc8af43bd256552549d35a874ea1ab02afa8a9925dfd173e931b8480.
Repeated publication reused that same file/revision. Peak RSS for the successful
cloud validation run was 809,724 KiB. All 284 PSD mappings and allocations 655/659
had identical before/after database digests. The direct cloud test did not change
the active layout or enqueue an order; live activation follows release checks.

Dropbox requires revision paths (`rev:<revision>`) for exact-file retrieval;
the deprecated SDK `rev` argument is not used by the new JPG path. Existing PSD
and companion implementations are left unchanged. Files resolves the permanent
file ID first, then the JPG download verifies revision, byte count and SHA256.
