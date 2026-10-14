# Auto Editions V11 preparation

Order generation remains the existing Render worker and immutable Dropbox JPG archive. This release adds product preparation checkpoints and connects the existing Edition Ops PSD Add action to them. It does not change allocations, Shopify fulfilment, certificates, supplier settings or original PSDs. The legacy fallback remains during migration.

## Operation

An administrator opens Edition Ops > Auto Editions preparation and connects the existing Photoshop preparation computer once. Its existing authenticated companion stores a preparation-only capability with Windows user-scoped DPAPI. No Dropbox or Shopify credentials are sent to the computer. Normal order downloads do not use this host.

Newly confirmed Add mappings enter the queue in the mapping transaction, ahead of bulk catalogue work. Resume mapped catalogue adds existing mappings without resetting completed checkpoints. One host job runs at a time, sharing the existing Photoshop processor lease. Preparation uses a staged PSD and never saves the original. Each source is pinned by product ID, Dropbox ID, revision, size and content hash.

Ambiguous/flattened/nested numbers, missing fonts, mismatched edition limits and unrecognised plaques fail closed. Existing number/plaque bounds determine placement. The existing Photoshop preparation code preserves number appearance and produces a clean master plus reusable patches, with bounded proportional TEST enlargement. The Kostecki reference is retained.

Render independently verifies every generated asset checksum, pixel-reference equality, and unchanged pixels outside the authorised number region before storing the master. Enlarged or uncertain artwork awaits administrator visual quality approval in the preparation panel. Approval enables product-wide TEST downloads; exact variant approvals retain precedence. Cloud Ready never means supplier Print Ready.

Failed jobs retain reasons and have Retry. Expired leases are reclaimed at most three times. New leases fence stale workers. Completed assets and immutable JPG history are reused; replacing a master does not overwrite previous artwork.

## Host availability and recovery

Keep the authorised Windows session and Photoshop available for one-time preparation. The existing companion supervisor restores preparation polling when it starts. Disconnect my preparation hosts revokes the current administrator's host capabilities. Account deactivation, permission loss, session-version change, expiry or revocation stops new claims and invalidates outstanding grants. Legacy administrator capabilities are bound to the existing server authentication signing configuration.

The host processes serially and pauses claims below 8 GiB free space. After confirmed cloud verification it releases only its own staged PSD and expanded temporary assets; it retains the package and receipt for recovery. Sources, historical archives and other task directories are never cleanup targets. Technical failures remain visible; no uncertain product is automatically approved.

## Deployment

Apply `supabase/migrations/20261014053326_auto_editions_onboarding.sql` before deploying code. The three additive tables use RLS and deny PUBLIC, anon and authenticated access; the existing server connection performs authorised operations. No new Render service or storage system is required. Use the canonical sports-cave-os service only.

Update only the installed companion's preparation module, pair message handler, supervisor preparation startup hook, and conservative layer detector, preserving its task identity, trust and other functions. Register it through the live preparation panel. Test a genuinely new mapping through Edition Ops Add, cloud validation, visual approval and Orders before considering onboarding accepted.

## Verification record

Baseline: main `823a19666e9d69a75b6c89b022ceb549cc2c1b4c`, 334 Edition Ops product records, 284 PSD mappings, one approved cloud product across four variant layouts. These are database counts, not a fresh Shopify catalogue crawl.

The initial five distinct local pilots passed source-preservation and pixel proofs at 11340 x 8016. The next ten yielded seven successful local preparations, two Needs PSD Repair, and one Blocked. Local preparation is not equivalent to cloud approval; deployment/migration acceptance is recorded separately after live checks.

Focused tests cover durable PostgreSQL leases, scoped host authentication/revocation, VA mapping permissions, wildcard/variant precedence, immutable history, Windows DPAPI, temporary-path boundaries, responsive preparation review and the existing internal Files workflow. The old `test_psd_open` snapshot test requires the external `output/psd_snapshot/approved_dropbox_psds_282.csv`, which is absent from a clean task checkout.
