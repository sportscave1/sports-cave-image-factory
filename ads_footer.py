"""Single footer contract shared by Ads generation and final export."""

FOOTER_VERSION = "SPORTS CAVE TWO-LINE COLLECTOR FOOTER V5"
COMPACT_FOOTER_RULES = f"""{FOOTER_VERSION}
Apply to every existing Sports Cave black-footer layout; do not add a footer to layouts that have none.
One two-line system for all three covers: the assigned headline, then CLAIM YOUR EDITION.
Render no supporting sentence or FOMO line on the image. Legacy supporting-line metadata is retained only for saved-record compatibility, never rendered or required by review.

REFERENCE-LED FOOTER — GENERATE AS PART OF THE FINISHED AD
Inspect sports-cave-ad-footer-example.jpg in the project's source/Assets (Dropbox: Sportscave Team Folder/03_ASSETS). It is a visual design reference only: do not paste, composite, embed or place that file into the output. Generate the complete ad, including its footer and the assigned two text lines, in the original image-generation workflow. Do not require a separate compositor, font installation or asset-insertion step.
Recreate the reference's opaque satin-black background with soft, restrained diagonal fabric folds and natural charcoal highlights, and its single subdued dark Collector Series seal at the right. The backdrop remains opaque; no photograph shows through. No plain flat-black substitute, room-driven recolouring, marble, glitter or conspicuous texture. If the source cannot be viewed, use this description and continue; do not claim to have inspected it.
Keep the original layout: on a square, upper photograph approximately 80–82% and footer approximately 18–20%, full width and flush to the bottom with a crisp straight boundary. Retain each non-square format's original footer proportions. Keep the complete framed product visible above it.
Replace the existing thin top divider IN PLACE with one fine continuous antique-gold shimmer across the top of the footer: a restrained luminous metallic highlight, not an extra strip, gap, second line, central flare or vertical glow. Do not enlarge the footer or change the room to accommodate it.
Centre both lines on the SAME axis in the clear text area LEFT of the badge, not the full-canvas midpoint. Keep at least 64 px left inset at 1024 px and at least 24 px clearance from the badge. All glyphs and the underline remain inside the footer. Never overlap the badge or put promotional text on the wall.

REFERENCE-LOCKED TYPOGRAPHY — SINGLE AUTHORITY
Use the approved footer example in the project source/Assets (sports-cave-ad-footer-example.jpg) as the visual authority for the satin-black colour, warm champagne/ivory headline, richer antique-gold number and CTA, badge and top seam shimmer. Inspect that source as a design reference before generation; do not recolour the footer to match the room or impose a different hexadecimal palette. The supplied Lewis footer screenshot guides the lettering, not its example headline selection. Preserve the current approved headline rotation and each assigned headline verbatim.
Line 1: a large, elegant high-contrast ITALIC serif headline, regular weight, with fine hairlines, graceful bracketed serifs and natural slanted letterforms; no upright roman, sans serif, heavy bold, slab or condensed type. Match the reference's warm luminous champagne lettering with restrained tonal warmth, never a flat white block or bright yellow glow. At 1024 px, start around 56–62 px and measure the assigned wording within the clear text area; use the largest natural size that fits comfortably without wrapping, squeezing, stretching or rewriting. Keep normal optical kerning and preserve supplied casing. Do not copy the screenshot's headline in place of the selected variation.
Line 2: exactly CLAIM YOUR EDITION, upright classical SERIF capitals, regular to medium weight, visibly smaller than the headline (about 22–25 px at 1024), in the source's antique gold. Use generous, even optical tracking around 0.35–0.45 em, with clear word spaces; target roughly two-thirds of the headline width as in the reference, adjusting tracking modestly for the assigned headline. Render normal words with font tracking, never insert extra literal spaces or change the CTA text. No Montserrat or other sans-serif CTA, no italic CTA, no bold button-like lettering.
Centre both lines on their shared axis left of the badge. Keep one calm, compact vertical interval: about 16–22 px between the lowest headline/underline edge and the top of the CTA glyphs at 1024. Balance the complete two-line group vertically inside the existing footer with generous top/bottom breathing room; no third row or leftover supporting-line space. Proportions follow the source and actual glyph bounds, not cumulative resizing of previous outputs.
Colour the verified number 100 antique gold and underline ONLY those three digits with one fine, level gold hairline, optically centred on their measured glyph bounds, approximately 4–8 px wider overall, 3–5 px below, 1–2 px thick at 1024. Use refined subtly tapered ends and a restrained source-matched gold highlight; no thick bar, heavy shadow, neon glow, second underline or decorative dash. If the headline has no 100, add no underline. This number underline is separate from the unchanged continuous gold shimmer at the top of the footer.
Inspect actual glyph bounds before export and refine size/kerning within this hierarchy to fit; use font measurement only if available, never as a prerequisite for generation. Preserve the selected wording and readable serif character; report only an unresolved genuine fit/tool limitation, not a routine typography adjustment. These source-led rules are the sole footer font, colour, spacing and underline specification for every ad and market; room palettes, legacy typography defaults and seasonal copy must not restyle it or reintroduce a supporting sentence.
The CTA is plain gold lettering, never a button, box, capsule, border, glow or second badge. No third line, no empty row reserved for FOMO, no added promotional text elsewhere in the photo.

FINAL FOOTER INSPECTION
Use the original generation, review and delivery workflow. Check the actual finished ad at full size and 256 × 256: exact assigned headline and CTA inside the footer, 100-only underline, no badge overlap, no supporting sentence, no wall copy or CTA button, and complete unchanged product. Preview and download must refer to the same finished ad. Follow the existing creative review for corrections; no additional approval, compositor or asset-copy gate.
Preserve headline assignments, scene variations, written Meta copy, CSV schema, filenames, route order and Companion completion/handoff. This is a rendering contract, not a change to queue or posting execution.
"""


def apply_footer_contract(prompt):
    """Include the shared policy once at the public prompt boundary."""
    if COMPACT_FOOTER_RULES in prompt:
        return prompt
    return COMPACT_FOOTER_RULES + "\n\n" + prompt
