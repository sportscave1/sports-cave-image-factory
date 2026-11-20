# Baseline 2.1 Beta — Ad 2 collector seal

Task 20261120-1aa52674, owner codex-ad2-badge-20261120-09. User explicitly authorized the focused change, naming the prior release Baseline 2.0, activating Baseline 2.1 Beta and pushing Git/Render.

## Result

New Ads Instant Experience keeps the original three scenes, camera roles, original framed-product reference, glazing, independent image calls, written Meta copy, CSV schema, filenames and Companion handoff. Ads 1 and 3 retain the unchanged normal 160 px three-line typography, FOMO sentence, CTA and thin gold shimmer. The same selection logic still supplies three distinct approved headline/support pairs. The existing final review chooses the best two distinct candidate pairs for Ads 1 and 3, preserving wording and matching sentences. Ad 2 has a 112 px matte-black footer at y=912, one centred 50 px editorial-serif Claim Your Edition title and original transparent 88 px gunmetal seal at x=64/y=924. Width-relative scaling preserves this profile.

The actual Dropbox PNG was found by file ID id:u1tYiAa2O-AAAAAAAACu3w and exact asset path. The local synced original is 2,371,462 bytes, 1254 square RGBA with transparent alpha. Its SHA256 is 3e614eccc8bb48f174696e91bb1d0a37f31690c49b3ba3e9b7d07d04b1155dab. The identical bytes are shipped under static/ads/blackened-gunmetal-sports-cave-medal.png and referenced through the existing static-serving path. The prompt requires original-pixel compositing during existing JPEG export, never a generated lookalike or screenshot. No image generation/posting was started for this release; prompt tests are not visual evidence of a newly generated ad.

## Conflicts removed

- Removed universal footer geometry/type from the mixed master shared section. Each image receives its own scoped footer block. Normal standalone exports retain normal geometry; Ad 2 standalone export receives only its badge profile.
- Automatic delivery now inspects each assigned profile instead of requiring three lines on Ad 2. Earlier saved Baseline deliveries keep the original inspection.
- Existing footer-prefix and seasonal helpers recognize the Beta marker and cannot prepend the old all-ads footer contract.
- USA current-contract recognition includes its actual collector-hallway group labels and both normal footer blocks. Saved submitted packs remain immutable under the existing behavior.
- The existing Meta Ads project Instructions were saved and reopened to verify exact text (normalizing Windows line endings). Its two old PREMIUM_COMPACT_V2 source associations were replaced with the aligned PROJECT_ROLE_AND_TASK_PRIORITY.txt and BASELINE_FOOTER_TYPOGRAPHY.txt; both previews were inspected. Original badge source, collector icon and true-to-scale source were retained. The scope explicitly retains Baseline 2.0 behavior and permits the Ad 2 asset export. No messages or generation requests were sent.

The old released Ads bundle is preserved as Baseline 2.0 in Git-backed prompt history. The current manifest names Baseline 2.1 Beta, version 2.1, including the new editable badge/candidate/review sections. Older Collector Beta remains inactive.

## Validation

126 focused Python tests and three subtests passed across profile isolation in five markets, exact PNG bytes/alpha, normal footer specifications, candidate retention, scenes, saved selections, seasonal behavior, automatic delivery/recovery, prompt hashes, library and clipboard UI. Nine Node download/receipt tests passed. Topology and whitespace checks passed. Four older combined-execution tests also fail on the unchanged parent f0b6574c; reproduced separately and left outside this focused change. They assert superseded room/one-generation/height behavior. No new tests claim OCR, measured generated typography or a successful live ad run.

Only the existing canonical Render service sports-cave-os is used. No Blueprint or infrastructure changes, permissions, pairing, Companion binaries, campaigns or budgets change.
