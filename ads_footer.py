"""Shared footer policy for all staff, markets and Meta creative formats."""

FOOTER_VERSION = "SPORTS CAVE COMPACT RESTORED SUBHEADLINE FOOTER V2"
COMPACT_FOOTER_RULES = f"""{FOOTER_VERSION}
Apply to every Sports Cave black footer in every ad format and staff account.
Keep existing layouts that have no black footer; do not add a footer to them.
Render exactly three lines: the existing dynamically selected HEADLINE, its exact assigned supporting line directly below it, and CLAIM YOUR EDITION.
Preserve the headline wording, font, size, colours, gold highlights, underline, alignment and styling exactly. Do not rewrite, shorten or standardise headline variations, or move the supporting sentence into the headline.
Restore the exact saved supporting sentence and historical selection rules; never invent replacement wording. Set it in Montserrat Regular, 24–26 px at 1024 px, softer warm off-white, centred on one line. Keep it secondary; no blank row or spacer.
Keep CLAIM YOUR EDITION exactly unchanged, including its existing gold colour, typography, tracking and styling.
Keep the full-width opaque matte-black panel flush to the bottom, with its existing thin gold separator along the top. No fade, gradient, transparency or floating overlay.
For a square canvas, use approximately 18–20% footer height and 80–82% photograph. At 1024 px retain the existing 42–48 px headline and 26–28 px CTA, 64–72 px horizontal safe margins and at least 64 px bottom text clearance. Use compact clear inter-line gaps to balance the headline, supporting line and CTA within the same panel; never enlarge the footer to fit the restored line. Scale existing format typography and safe areas proportionally for other output sizes, fitting these three lines without excess black space.
The framed edition remains the dominant visual. Preserve all artwork, frame, room, brand-colour, realism and generation-workflow instructions. Restoring the supporting sentence must not add a scarcity claim or alter any product detail.
Inspect the final image: exact headline, assigned supporting sentence and CTA, unchanged compact balanced footer, preserved separator and branding, dominant complete framed edition. Report unresolved defects honestly."""


def apply_footer_contract(prompt):
    """Include the shared policy once at the public prompt boundary."""
    if COMPACT_FOOTER_RULES in prompt:
        return prompt
    return COMPACT_FOOTER_RULES + "\n\n" + prompt
