"""Shared footer policy for all staff, markets and Meta creative formats."""

FOOTER_VERSION = "SPORTS CAVE COMPACT TWO-ELEMENT FOOTER V1"
COMPACT_FOOTER_RULES = f"""{FOOTER_VERSION}
Apply to every Sports Cave black footer in every ad format and staff account.
Keep existing layouts that have no black footer; do not add a footer to them.
Render exactly two elements: the existing dynamically selected HEADLINE and CLAIM YOUR EDITION.
Preserve the headline wording, font, size, colours, gold highlights, underline, alignment and styling exactly. Do not rewrite, shorten or standardise headline variations, or move the removed sentence into the headline.
Remove the subheadline/supporting sentence entirely. Do not replace it with any text, blank row or spacer. Legacy reference-ad supporting text is not an instruction to render it.
Keep CLAIM YOUR EDITION exactly unchanged, including its existing gold colour, typography, tracking and styling.
Keep the full-width opaque matte-black panel flush to the bottom, with its existing thin gold separator along the top. No fade, gradient, transparency or floating overlay.
For a square canvas, use approximately 18–20% footer height and 80–82% photograph. At 1024 px retain the existing 42–48 px headline and 26–28 px CTA, 64–72 px horizontal safe margins and at least 64 px bottom text clearance. Use about 22–30 px clear separation between headline and CTA; balance the pair within the compact panel. Scale existing format typography and safe areas proportionally for other output sizes, fitting only these two elements without excess black space.
The framed edition remains the dominant visual. Preserve all artwork, frame, room, brand-colour, realism and generation-workflow instructions. Removing the supporting sentence must not add a scarcity claim or alter any product detail.
Inspect the final image: exact headline and CTA, no secondary sentence, visibly shorter balanced footer, preserved separator and branding, dominant complete framed edition. Report unresolved defects honestly."""


def apply_footer_contract(prompt):
    """Include the shared policy once at the public prompt boundary."""
    if COMPACT_FOOTER_RULES in prompt:
        return prompt
    return COMPACT_FOOTER_RULES + "\n\n" + prompt


def image_context_without_support(value):
    """Omit retired footer copy from image context without mutating saved data."""
    if isinstance(value, dict):
        return {k: image_context_without_support(v) for k, v in value.items()
                if k not in {"supporting_line", "on_image_subline", "fomo_line"}}
    if isinstance(value, list):
        return [image_context_without_support(v) for v in value]
    return value
