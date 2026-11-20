# Original Ads prompt restoration — 20 November 2026

Historical release note: superseded by ADS_BASELINE_RELEASE_2026_11_20.md. The active version is now v1.0 Baseline with three footer lines.

Task/owner: codex/ads-footer-reference-typography (this Codex session). Existing user-assigned worktree retained; it has no Studio registry task ID, so no other task record was changed.

Explicit authorization: restore the attached original Ads bundle, change only the footer style, and push to Git/Render. User confirmed two lines rather than the original supporting/FOMO row.

Restored original supplied sections, including the original creative review. Footer changes retain the original square 18–20% geometry and non-square proportions. The Dropbox 03_ASSETS sports-cave-ad-footer-example.jpg was inspected locally: opaque black satin, subtle diagonal folds, fine gold top seam and subdued right-hand collector seal. It is now visual reference only, never an asset pasted into the output. The complete ad is generated in the original workflow without a mandatory compositor. The shared footer defines italic champagne serif headline, gold 100-only underline, tracked upright antique-gold serif CLAIM YOUR EDITION, badge clearance and one in-place gold shimmer seam. Headline rotation and saved choices remain unchanged.

The 16 unchanged original prompt sections are SHA256-checked in test_ads_footer_original_restore.py. Footer-specific runtime additions that previously excluded headline/CTA from image calls have been removed. CSV, Companion handoff, queue/status code, room resolution and written copy are unchanged.

Validation: 31 focused tests passed (original restoration, two-line footer across five markets and two products, all New Ads formats, saved choices, creative review, delivery and prompt bundles). Python compilation and git diff --check passed. Render topology validator passed; no Blueprint or service identity change.
