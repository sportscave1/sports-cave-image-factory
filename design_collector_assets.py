"""Shared composition and styling guidance for the official collector layers."""

COLLECTOR_ASSET_HEADING = "**INTEGRATE THE OFFICIAL PLAQUE AND EDITION NUMBER**"
COLLECTOR_ASSET_PLACEMENT = f"""{COLLECTOR_ASSET_HEADING}

**COMPOSE THE BADGE INTO THE ARTWORK**

Treat the official plaque and its live edition number as part of the composition from the beginning. Before generation, plan their intended position, approximate scale and relationship to the subject and typography using the inspected master assets. Generate the surrounding artwork to support that placement, while continuing to exclude the plaque and number from image generation. If the master is unavailable, keep placement provisional under the existing recovery rules and continue independent work.

Do not automatically retain the master's badge position or place it in whichever corner is empty. Choose the location that creates the strongest visual connection with the title, subject and surrounding environment. Where appropriate, align the plaque with the typography, centre it beneath a title group, or connect it to an existing compositional line. These are options, not a fixed layout. Use deliberate spacing so it belongs to the visual hierarchy while remaining comfortably separated from neighbouring elements and inside the safe border. Avoid a large unexplained gap that makes it look like an unrelated footer.

Integrate it through placement, proportional scale, compatible surrounding tones and the artwork's existing accents. Adjust the background behind and around it where needed for a natural transition. Do not add a conspicuous spotlight, glow, pedestal, extra box or decorative flourish merely to connect the badge.

Use the original official badge asset. Restrained, non-destructive tonal, colour and finish adjustments are permitted to suit the artwork and maintain contrast. Preserve the recognisable Sports Cave mark, lettering, geometry, proportions and edition information; do not redraw, distort, distress away detail, invent a replacement seal or merge it into the generated image. Keep the original asset recoverable through editable styling on its original layer. The number may receive compatible editable text styling for contrast, but never change its edition text, rasterise it or move it independently out of its intended position within the plaque.

Move and proportionally resize SC_EDITION_PLAQUE and its live SC_EDITION_NUMBER together as one placement unit. Keep the number aligned in its intended position inside the plaque. Use the original named layers, with each visible once. Keep SC_EDITION_NUMBER as the original editable text layer with the same name and edition text for automatic numbering. Apply the move and scale to the live text transform and position. Keep both layers separate from the generated artwork.

Inspect the assembled artwork at full size and thumbnail size. Ask: "Does the plaque feel deliberately composed with the subject and title, or like a stamp placed on afterward?" If it feels detached, correct its position, scale, nearby spacing, tonal styling or surrounding background before saving, within the existing review and recovery limits. Check the official design, layer identities, editable edition text, readability and relative alignment at the chosen final position and scale. Use the final layout for the transform check.

Apply this within the existing composition and final PSD review steps, without a separate approval or workflow stage. For targeted edits, honour explicit locks and change only the authorised elements. Keep all existing safe-area, layer-preservation and verification requirements.

"""
