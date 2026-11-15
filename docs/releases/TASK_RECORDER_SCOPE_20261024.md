# Task Recorder generation preflight and desktop launcher

Record preflight rejected Product Uploads after Streamlit exposed the immediate main layout as `Group / stMain`. Accept that exact layout boundary while retaining the root, document, window, unique-button, protected-control and generation-receipt checks. The live page also omitted `data-product-sha256`; publish the deterministic fingerprint of the existing prepared-product context so the adapter can bind the product, category and PSD revision.

The Windows launcher accepts `--toolbar` to reveal the current floating toolbar without starting capture or resetting the current session. The installed desktop shortcut uses that option. The reviewed archive includes both fixes; the browser adapter and native download host are unchanged.

- Package manifest: `9df87deaaf94a7c089b8c9d17e571921dd5d4c5aafd2f1901ec7b9a076d31806`.
- ZIP SHA256: `4d34e67396ae9b28471a762b1013e3bd2c87e9b06bc5cc643a782af53a90f1d0`.
- Native SHA256: `c4ce479b77b14aa0fdbd15c94a3ea77a86e89185e71df3b1d8b69287754b9da8`.
- Installed local release: `9df87deaaf94a7c089b8`; previous direct-launch release `5f7bd25309664561eb9d` retained, along with Preflight23 `9dfa55d025e68c718487`.
- Compatibility remains native IPC 2, desktop format 1, actions 2/3, adapter 0.3.4/protocol 1, relay 4, package 2.

Validation: 27 native generation policies; 18 Python tests and 5 subtests covering fingerprint binding, toolbar reveal, package and upgrade behavior. Actual installed preflight in the affected OS window passes the scope check and correctly blocks on the missing live fingerprint before its deployment. Post-deployment acceptance is recorded separately. No generation action is needed to verify Record preflight.

Canonical target: Nathan's workspace `tea-cut91gtsvqrc73e5acs0`, existing `sports-cave-os` service `srv-d8kl4on7f7vs73dvavv0`. Previous live deploy `dep-dbdsrh5g1s2s73avn64g`, commit `27bd096c848deca36f9ce0a79e756f6bc348e038`, is the rollback reference. No topology, database migration, adapter registration or Photoshop/Edition Ops companion change.

Preserve newer recordings before any rollback; select the previous installed code with the supported rollback command, never overwrite recording data with a prior snapshot. All private traces, backups and recording evidence remain local and are excluded from this release.
