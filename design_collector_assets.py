"""Shared composition and checks for the official collector layers."""

COLLECTOR_ASSET_HEADING = "**INTEGRATE THE OFFICIAL PLAQUE AND EDITION NUMBER**"
COLLECTOR_LAYER_RULES = """Use the original official asset and preserve its mark, lettering, geometry and edition information. Restrained, non-destructive tonal, colour and finish adjustments are permitted. Move or proportionally resize SC_EDITION_PLAQUE and SC_EDITION_NUMBER together on their original separate layers. Keep each visible once and the number aligned inside the plaque. Keep SC_EDITION_NUMBER as the original editable text layer with the same name and apply the matching live text transform. Use compatible editable styling for contrast, but never change its edition text, rasterise it or redraw the original assets."""

BADGE_FOOTPRINT = "Before generation, reserve a realistically sized footprint for the official plaque and edition number beside or beneath the intended typography, inside the safe border. Exclude both assets from image generation and add them during PSD assembly."

BADGE_PLACEMENT_VERIFICATION = f"""**COMPOSE THE BADGE INTO THE ARTWORK**

Treat the title, subject identification and official badge as one collector composition. Reassess the planned footprint against the generated artwork. Use the master badge’s size and position as asset starting values and actively choose both for the composition. When placing the badge below the title, start by testing a width around 65–85% of the main title block’s width. Adjust for the badge shape, available space, title hierarchy and subject clearance.

Use a shared centreline or edge alignment with the title group. The gap to the nearest related text should generally be smaller than the badge’s height. Avoid isolated corners or excessive empty space around the badge. Use restrained, editable tonal or colour adjustments to match the surrounding finish. Keep the badge legible and avoid blur, added glow and extra backing boxes.

{COLLECTOR_LAYER_RULES}

**Mandatory assembly check.** Compare at least two badge arrangements that test different sizes and positions using PSD transforms only. Inspect the complete artwork at full size and thumbnail size and retain the strongest arrangement. Honour explicit locks. Confirm that the badge reads as collector identification at thumbnail size, its text is legible at the intended size, and it feels part of the title group while the subject and title remain dominant. Check clearance from the subject, typography and safe border, and verify both original layers. If placement fails, adjust scale, position or nearby spacing within scope. Record unresolved placement or legibility as needs_attention even if the PSD saves and its layers pass verification.

"""

COLLECTOR_ASSET_PLACEMENT = f"""{COLLECTOR_ASSET_HEADING}

Preserve the existing badge position and size unless the user requests a change. Exclude the official plaque and number from generation and use the original layers during PSD assembly.

{COLLECTOR_LAYER_RULES}

Inspect the assembled placement at full size and thumbnail size. Verify legibility, layer identity, editability, alignment and the chosen transform. Honour explicit locks and apply changes only within the authorised edit scope.

"""

NEW_BADGE_LAYOUT = f"""**REVIEW THE REAL BADGE BEFORE GENERATION**

With master access, compare at least two badge arrangements that test different sizes and positions using PSD transforms only on the photographic layout. When below the title, start around 65–85% of the main title block’s width. Choose for hierarchy, legibility, shared alignment and safe clearance; avoid isolated corners, excessive gaps or backing boxes.

{COLLECTOR_LAYER_RULES}

Make two views of the same locked layout: review with the real plaque and live number visible, then hide both for the generation reference, leaving the underlying artwork visible. Record their paired position and proportional scale relative to the master canvas in REVIEW NOTES. Keep that area continuous, without a generated badge or placeholder. Restore the recorded transform during final assembly and adjust only a named placement defect.

Without master access, review the reserved footprint provisionally and run them once the master is available, before saving the final PSD. Record unresolved placement or legibility as needs_attention. Continue independent work without an approval pause.

"""
