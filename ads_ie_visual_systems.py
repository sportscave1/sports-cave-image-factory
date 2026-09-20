"""Visual-only composition for standard IE; persisted slot identities stay unchanged."""


VERSION = "IE PREMIUM SCARCITY THREE ROOMS V2"
FAMILIES = ("premium_scarcity",) * 3
ROOMS = (
    ("collector_lounge", "premium collector lounge / refined living area", "warm taupe textured plaster", "dark walnut console at left", "cropped cognac leather sofa at right", "deep window reveal at outer left", "warm soft daylight from the left with restrained amber ambient fill"),
    ("heritage_study", "refined private home office", "smoked bronze seamless mineral plaster", "slim warm oak desk below the frame", "single upholstered desk chair crop", "balanced recessed alcove at the outer edge", "soft frontal window fill with a warm shaded desk lamp"),
    ("modern_man_cave", "premium games room / architectural collector den", "dark chocolate seamless stone plaster", "low asymmetric smoked-timber credenza at right", "restrained leather club chair crop at left", "deep room corner at outer right", "soft daylight from the right with low warm indirect architectural light"),
)
CAMERAS = ("RIGHT ANGLE, camera positioned to the RIGHT viewing diagonally toward the artwork; not straight-on",
           "CENTRE / STRAIGHT-ON, camera directly facing the frame, central hero and balanced composition",
           "LEFT ANGLE, camera positioned to the LEFT viewing diagonally toward the artwork; not straight-on")
SCARCITY_RULE = ('ON-IMAGE SCARCITY WORDING: When writing a limited-edition label use LIMITED TO {verified limit} or LIMITED EDITION '
                 'when approved. Never append worldwide, world wide, globally, or any geographic '
                 'scope to an edition claim, even when source metadata or description copy uses it. '
                 'Never invent a limit. Immutable wording already inside the source artwork stays untouched.')


def resolve_visual_system(visual, index, context, variation_token):
    """Extend the existing resolved product context, never resolve commercial facts here."""
    room_key, room, wall, primary, secondary, architecture, lighting = ROOMS[index]
    camera = CAMERAS[index]
    visual.update(visual_family=FAMILIES[index], camera_role=("RIGHT", "FRONT", "LEFT")[index],
                  camera_side=camera, camera_instruction=camera + ". Keep verticals straight and complete frame rigid. Never mirror artwork.",
                  creative_variation_token=variation_token or "standard", room_profile_key=room_key,
                  room_profile=f"Room {index + 1}: {room}", room_type=room,
                  wall_colour=wall, wall_material=wall, wall_finish=wall,
                  room_materials=wall + "; " + primary + "; " + secondary,
                  primary_cue=primary, secondary_cue=secondary, architectural_cue=architecture,
                  lighting=lighting, time_of_day="warm late-afternoon interior",
                  overlay_position="fixed opaque full-width black/gold footer across bottom 24–28%",
                  product_position=("slightly left-of-centre", "central hero", "slightly right-of-centre")[index],
                  composition="1024 x 1024 square; upper 72–76% lifestyle room; bottom 24–28% opaque promotional banner")
    if context.get("edition_limit"):
        visual.update(supporting_line="Once they’re claimed, this edition retires forever.",
                      fomo_line="Once they’re claimed, this edition retires forever.")


def camera_wall_rules(visual):
    return f"""LOCKED CAMERA / ROOM / WALL RESOLUTION
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']}
Use the token only for creative freshness; never display it or internal metadata on the image.
Selected camera: {visual['camera_side']}.
Resolve exactly ONE camera: use the selected value above, not a menu of alternatives. Keep the assigned right / centre / left camera role. Never mirror artwork.
Resolved room: {visual['room_profile']}.
Resolved wall: {visual['wall_colour']}.
Resolved material treatment: {visual['room_materials']}.
Analyse the actual attached product, SPORT, MARKET, title, palette, brightness, frame colour, emotional mood, era/nostalgia and campaign context. The actual product wins over sport tendencies. Preserve the one resolved scene and ensure the unchanged frame separates clearly from its wall.
Use the resolved primary cue and no more than one secondary cue. All three images share the same black/gold bottom banner.
Avoid identical wall/camera combinations across recent fingerprints and this package without changing the assigned camera side; product fidelity wins. Vary only visual interpretation, never product identity, branding, edition limits or verified facts.
{SCARCITY_RULE}"""
