"""Shared composition and checks for the official collector layers."""

COLLECTOR_ASSET_HEADING = "**INTEGRATE THE OFFICIAL PLAQUE AND EDITION NUMBER**"
COLLECTOR_LAYER_RULES = """Use the original official asset and preserve its mark, lettering, geometry and edition information. Restrained, non-destructive tonal, colour and finish adjustments are permitted. Move or proportionally resize SC_EDITION_PLAQUE and SC_EDITION_NUMBER together on their original separate layers. Keep each visible once and the number aligned inside the plaque. Keep SC_EDITION_NUMBER as the original editable text layer with the same name and apply the matching live text transform. Use compatible editable styling for contrast, but never change its edition text, rasterise it or redraw the original assets."""

COLLECTOR_ASSET_PLACEMENT = f"""{COLLECTOR_ASSET_HEADING}

**COMPOSE THE BADGE INTO THE ARTWORK**

Before generation, plan their intended position and scale with the subject and title, inside the safe border. Exclude the official plaque and number from generation. Keep the plan provisional if the master is unavailable. Do not automatically retain the master’s coordinates or use an empty corner. Align with the type or a compositional line when helpful. Use spacing and compatible tones to integrate the pair without added glow, boxes or flourishes.

{COLLECTOR_LAYER_RULES}

Inspect the assembled placement at full size and thumbnail size. Verify legibility, layer identity, editability, alignment and the chosen transform. Honour explicit locks and apply changes only within the authorised edit scope.

"""
