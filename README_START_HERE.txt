SPORTS CAVE OS — IMAGE-GENERATION PROMPT INVENTORY
GitHub main snapshot: 05505958ed65c92e5fa491081e29f8fdb0bcc331
Export date: 9 October 2026
Repository: https://github.com/sportscave1/sports-cave-image-factory
Total prompt / direction / builder files: 96
IMPORTANT: This is an export of tracked GitHub CODE DEFAULTS, not live edited prompt overrides stored in Supabase.

WHAT THE FILES MEAN
- Direct .txt sources preserve their source text.
- "STYLE COMPONENT" and "SHARED RULE" files are blocks assembled into longer generation prompts at runtime.
- "RUNTIME BUILDER" files contain the original Python function as readable Notepad text: product, scene, card and winner data must be resolved by the application. Do not assume code text is a fully executed prompt.
- "DYNAMIC IMAGE DIRECTION" files are one-per-image directions combined with the universal template.
- "LEGACY BUILDER" / "RETIRED MOCKUP PROMPT" files are NOT the primary active workflows.
- Some files contain placeholders such as {product} or {{PRODUCT_NAME}}: these are intentional, not missing source content.
- Code-backed marketing prompts may have saved editable Supabase overrides that differ from GitHub defaults. Those overrides are not in this archive.

COVERED
Design Studio, styles, mockup product page (3 room families), close-up product image, new Ads Carousel, Instant Experience and Single Image/Video, Creative Refresh winner-led generation, Google Demand Gen, social content imagery, Social Reels Studio image prompts, email visual/image prompts, shared realism/product constraints and retired Mockups reel prompts.

REVIEW FINDINGS
1. POTENTIAL CAROUSEL PRODUCT-AUTHORITY CONFLICT: ads_refresh_plan.AUTHORITY correctly says CANONICAL_PRODUCT (the stock black-frame photo) supplies the exact artwork and black frame, and its outside room is NOT the creative reference. But ads_refresh_plan.CAROUSEL_AUTHORITY states winning Carousel cards collectively supply immutable product authority for text, frame and other details. In reference_map(), the Carousel branch returns WINNER_CARD references without a CANONICAL_PRODUCT entry, unlike Instant Experience. Review this discrepancy against the intended workflow before changing any code.
2. WINNER IMAGE ≠ BLACK-FRAME PRODUCT IMAGE: winning ads are for creative lessons, while black frame is for artwork/frame fidelity. The current code reflects this consistently in some, but not all, refresh paths.
3. Mockups currently use one shared product-page template with 5 random room choices per type and 3 camera angles, not 3 completely unrelated static prompts.
4. Instant Experience refresh has a specific premium physical-frame, glass reflection and FOMO footer contract; verified edition facts are required.
5. Several source prompts are generated dynamically and may be edited in Supabase. GitHub alone does NOT prove which custom version is live in the UI.
6. Historical reels and compatibility builders remain in GitHub, separated here into 90_LEGACY_REFERENCE.

No production application logic was changed by this export. The repository's main branch is not changed.

Source for issue 1: https://github.com/sportscave1/sports-cave-image-factory/blob/05505958ed65c92e5fa491081e29f8fdb0bcc331/ads_refresh_plan.py
