"""Single footer contract shared by Ads generation and final export."""

FOOTER_VERSION = "SPORTS CAVE TWO-LINE COLLECTOR FOOTER V3"
COMPACT_FOOTER_RULES = f"""{FOOTER_VERSION}
Apply to every existing Sports Cave black-footer layout; do not add a footer to layouts that have none.
One two-line system for all three covers: the assigned headline, then CLAIM YOUR EDITION.
Render no supporting sentence or FOMO line on the image. Legacy supporting-line metadata is retained only for saved-record compatibility, never rendered or required by review.

ROOM GENERATION AND FOOTER COMPOSITING ARE SEPARATE
Generate the room and ORIGINAL framed edition together, preserving all lettering, signatures and badges INSIDE the product. Keep surrounding walls free of added promotional text, labels, buttons and badges. Do not send the assigned headline, CTA, FOMO sentence or footer artwork to the room-generation tool. No empty-room generation followed by pasting in the product.
Use one coherent room-generation call per assigned ad, with the existing scene, camera, lighting and glazing rules. Compose for the entire product to fit above y = 815 on the final square; reserve the bottom for the separate footer without cutting any frame edge.
After room generation, use the available image/file compositor to produce the finished cover. At 1024 × 1024, place sports-cave-ad-footer-example.jpg from Assets at its native 1024 × 209 size, full-width at x = 0, y = 815. Keep the photo above y = 815; the opaque footer fully conceals the photograph below. Preserve the satin texture, single right-hand Collector Series badge and its ring lettering, SC monogram, laurel and stars. Never invent or duplicate the badge. Preserve the single thin continuous antique-gold seam shimmer on the first footer row, within the 209 px, without a gap, extra strip, second line or vertical glow. Scale proportionally for other square sizes; retain existing non-square format geometry.

FINAL COMPOSITOR DATA — NEVER ROOM-GENERATION INPUT
Typeset only the assigned HEADLINE and CTA directly onto the footer asset using real fonts. Centre both lines on the SAME axis in the clear text area LEFT of the badge, not the full-canvas midpoint. Measure the badge's left edge and reserve at least 24 px clearance. Keep at least 64 px left inset and generous vertical breathing room; all glyphs and the underline must remain inside the footer. Never overlap the badge or move copy onto the wall to make it fit.
Use the Lewis reference's restrained collector hierarchy: one elegant warm-ivory serif headline (42–48 px at 1024), then a smaller, tracked antique-gold CLAIM YOUR EDITION (26–28 px, medium-weight sans serif). Preserve each assigned headline verbatim, with no wrapping, squeezing or stretched type. Measure actual glyph bounds before export; report a fit problem rather than silently changing the headline.
Colour the verified number 100 antique gold and underline ONLY those three digits with a fine gold stroke aligned to their measured glyph bounds, approximately 4–8 px wider, 3–5 px below, 1–2 px thick. If the headline has no 100, add no underline. No whole-headline underline or floating decorative dash.
The CTA is plain gold lettering, never a button, box, capsule, border, glow or second badge. No third line, no empty row reserved for FOMO, no added promotional text elsewhere in the photo.

FINAL EXPORT AND INSPECTION
Export one finished 1024 × 1024 sRGB JPEG per ad. Display the preview from that SAME finished composite and link that exact exported file; never preview the raw room image or link a different version. Inspect the actual JPEG at full size and 256 × 256: exact headline and CTA inside the footer, 100-only underline, no badge overlap, no wall copy or CTA button, complete unchanged product, distinct assigned rooms. Correct footer defects on the existing composite without regenerating the room. If the real asset, fonts/compositing tools or a valid export are unavailable, report the specific limitation and retain completed work; do not claim asset fidelity or mark an unfinished cover ready.
Preserve headline assignments, scene variations, written Meta copy, CSV schema, filenames, route order and Companion completion/handoff. This is a rendering contract, not a change to queue or posting execution.
"""


def apply_footer_contract(prompt):
    """Include the shared policy once at the public prompt boundary."""
    if COMPACT_FOOTER_RULES in prompt:
        return prompt
    return COMPACT_FOOTER_RULES + "\n\n" + prompt
