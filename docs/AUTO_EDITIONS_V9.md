# Auto Editions V9

Scope: internal Files navigation and the seven existing Kostecki & Hazelwood
allocations. The 11340 × 8016 master and SC3287 archive are unchanged.

The existing Files component mounts once inside the OS shell. Browser history
records the Files workspace while Orders stays mounted, preserving its filters
and grid position. Each Open verifies the saved identity with one authenticated
location request. Folder metadata is reused from the existing cache; a missing
exact file triggers a fresh folder listing. Navigation does not download artwork.

Run `python -m scripts.enable_auto_editions_v9` on the authenticated service for
read-only verification. Only after verifying its output, run with `--apply --actor
<operator>`. This adds TEST approvals for the three additional variants, scoped
to allocations 652, 653, 654, 658, 660 and 661. Existing allocation 659 and its
approval remain unchanged. It never enqueues a render or changes allocations,
product mappings, source assets, Shopify or fulfilment. Existing different
approvals and identity mismatches stop the operation.

Pre-release evidence:

- Live baseline: Orders reload 13.726 s; external Files selection cold 21.781 s
  and warm 20.528 s. Same authenticated browser; timings include automation
  observation overhead, not isolated network timings.
- 147 Python checks pass, plus 12 subtests. Five legacy Files assertions fail
  identically on V8 (permission wording and superseded desktop-helper strings).
- Desktop/mobile internal navigation, selection, frame/folder reuse, download
  initiation, duplicate prevention, state restoration and missing-file recovery
  pass. Existing Files browser/native interactions pass four scenarios.
- Canonical Render topology validation passes. No infrastructure changes.

Live acceptance must additionally verify a real new edition download, checksum,
plaque, archive reuse, all seven links and cold/warm internal navigation timings.
All output remains TEST / NOT PRINT READY pending variant-specific certification.
