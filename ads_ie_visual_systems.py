"""Visual-only composition for standard IE; persisted slot identities stay unchanged."""


VERSION = "IE PREMIUM SCARCITY DISTINCT FAN ROOMS V3"
FAMILIES = ("premium_scarcity",) * 3
SUPPORT_LINES = (
    "Once they’re claimed, this edition retires forever.",
    "Made for serious collectors.",
    "For collectors who know why it matters.",
)
ROOMS = (
    ("hallway_gallery", "premium residential hallway / gallery corridor", "floating narrow console at outer left", "one small sculptural object", "deep passage receding at outer left", "warm gallery picture light with soft side daylight"),
    ("office_den", "premium man cave / home office / collector den", "central writing desk below artwork", "shaded desk lamp and two closed books at one edge", "recessed bookcase at outer right", "soft frontal window light with shaded task-lamp fill"),
    ("bar_lounge", "private home bar / lounge / entertaining corner", "low drinks cabinet at outer right", "one lounge seat crop beside a restrained bar shelf", "recessed bar niche at outer left", "moody pendant light and low indirect amber cabinet lighting"),
)

# Aesthetic directions supplied by the campaign brief, not demographic facts.
FAN_STYLES = {
    "racing": ("refined racing-fan home, tailored leather and precision metal details", "smoked walnut", "brushed gunmetal", ("warm graphite mineral plaster", "deep bronze matte plaster", "dark tobacco stone plaster")),
    "social_sport": ("warm supporter home, comfortable seating and confident social atmosphere", "dark oak", "aged bronze", ("warm clay limewash", "smoky olive mineral plaster", "deep cocoa plaster")),
    "basketball": ("contemporary urban apartment, clean furniture lines and warm modern styling", "light smoked oak", "satin black metal", ("warm concrete-grey microcement", "mushroom mineral plaster", "charcoal seamless plaster")),
    "baseball": ("classic heritage home, timeless joinery and quiet display-like atmosphere", "American walnut", "aged brass", ("warm parchment plaster", "muted moss mineral plaster", "chestnut stone plaster")),
    "horse_racing": ("elegant polished home, tailored upholstery and restrained luxury", "dark burr oak", "soft antique brass", ("warm ivory plaster", "muted taupe limewash", "deep olive mineral plaster")),
    "cricket": ("understated collector home, refined study character and quiet heritage warmth", "honey oak", "antique bronze", ("warm sandstone plaster", "muted sage mineral plaster", "smoky umber limewash")),
    "universal": ("refined collector home with understated warm residential styling", "warm walnut", "muted brass", ("warm taupe plaster", "smoked bronze mineral plaster", "dark chocolate stone plaster")),
}


def fan_style(context):
    sport = str(context.get("product_sport", "")).casefold()
    if any(word in sport for word in ("horse", "equestrian")):
        key = "horse_racing"
    elif any(word in sport for word in ("motorsport", "formula", "f1", "racing")):
        key = "racing"
    elif sport in {"nba", "basketball"}:
        key = "basketball"
    elif sport in {"nrl", "nfl", "afl", "football", "rugby", "rugby league", "rugby union", "soccer"}:
        key = "social_sport"
    elif "baseball" in sport:
        key = "baseball"
    elif "cricket" in sport:
        key = "cricket"
    else:
        key = "universal"
    mood, wood, metal, walls = FAN_STYLES[key]
    era = context.get("product_era")
    if era == "historic" or context.get("artwork_mood") == "heritage":
        mood += "; timeless heritage furniture silhouettes and softened patina"
    elif era == "modern":
        mood += "; sharper contemporary furniture silhouettes and clean detailing"
    metadata = context.get("product_metadata") or {}
    if metadata.get("team_names") or "team" in str(metadata.get("artwork_type", "")).casefold():
        mood += "; proud supporter atmosphere through materials only, no merchandise display"
    return key, mood, wood, metal, walls


CAMERAS = ("RIGHT ANGLE, camera positioned to the RIGHT viewing diagonally toward the artwork; not straight-on",
           "CENTRE / STRAIGHT-ON, camera directly facing the frame, central hero and balanced composition",
           "LEFT ANGLE, camera positioned to the LEFT viewing diagonally toward the artwork; not straight-on")
SCARCITY_RULE = ('ON-IMAGE SCARCITY WORDING: When writing a limited-edition label use LIMITED TO {verified limit} or LIMITED EDITION '
                 'when approved. Never append worldwide, world wide, globally, or any geographic '
                 'scope to an edition claim, even when source metadata or description copy uses it. '
                 'Never invent a limit. Immutable wording already inside the source artwork stays untouched.')


def resolve_visual_system(visual, index, context, variation_token):
    """Extend the existing resolved product context, never resolve commercial facts here."""
    room_key, room, primary, secondary, architecture, lighting = ROOMS[index]
    fan_key, atmosphere, wood, metal, walls = fan_style(context)
    wall = walls[index]
    camera = CAMERAS[index]
    support = SUPPORT_LINES[index]
    if index == 0 and not context.get("edition_limit"):
        support = "A statement for your collection."
    visual.update(visual_family=FAMILIES[index], camera_role=("RIGHT", "FRONT", "LEFT")[index],
                  camera_side=camera, camera_instruction=camera + ". Keep verticals straight and complete frame rigid. Never mirror artwork.",
                  creative_variation_token=variation_token or "standard", room_profile_key=room_key,
                  room_profile=f"Room {index + 1}: {room}", room_type=room,
                  purpose=f"Image {index + 1}: {room}; {camera}; {atmosphere}",
                  fan_archetype=fan_key, atmosphere=atmosphere,
                  wall_colour=wall, wall_material=wall, wall_finish=wall,
                  room_materials=f"{wall}; {wood} furniture; restrained {metal} detailing; {atmosphere}",
                  primary_cue=f"{wood} {primary}", secondary_cue=secondary,
                  architectural_cue=architecture, lighting=lighting,
                  time_of_day=("soft late-afternoon gallery light", "warm afternoon workspace", "intimate early-evening entertaining light")[index],
                  supporting_line=support, fomo_line=support,
                  product_width=("72-78%", "78-84%", "70-76%")[index],
                  shot_distance=("editorial passage context", "closer frontal product hero", "wider intimate entertaining context")[index],
                  overlay_position="fixed opaque full-width black/gold footer across bottom 24–28%",
                  product_position=("slightly left-of-centre", "central hero", "slightly right-of-centre")[index],
                  composition="1024 x 1024 square; upper 72–76% lifestyle room; bottom 24–28% opaque promotional banner")


def camera_wall_rules(visual):
    return f"""LOCKED CAMERA / ROOM / WALL RESOLUTION
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']}
Use the token only for creative freshness; never display it or internal metadata on the image.
Selected camera: {visual['camera_side']}.
Resolve exactly ONE camera: use the selected value above, not a menu of alternatives. Keep the assigned right / centre / left camera role. Never mirror artwork.
Resolved room: {visual['room_profile']}.
Framing: {visual['shot_distance']}; product width {visual['product_width']} of canvas; {visual['product_position']}. Leave enough room context to identify this environment while keeping the artwork the largest visual element.
Resolved wall: {visual['wall_colour']}.
Resolved material treatment: {visual['room_materials']}.
Analyse the actual attached product, SPORT, MARKET, title, palette, brightness, frame colour, emotional mood, era/nostalgia and campaign context. The actual product wins over sport tendencies. Preserve the one resolved scene and ensure the unchanged frame separates clearly from its wall.
VARIANT PRECEDENCE — MANDATORY
The assigned room, camera and support line override generic lifestyle suggestions. Sibling metadata is comparison data only: never blend rooms or copy another slot's support line. The hallway must visibly read as a passage; the office as a workspace; the bar/lounge as a private entertaining space. Never substitute the same console-and-chair room or mirror another image.
Fan styling for this product: {visual['atmosphere']}.
Express this through the resolved furniture, finishes and lighting. Never add literal sports props, extra posters, team logos, themed novelty decor or clutter. Product palette and frame contrast guide subtle tonal adjustments without changing the room type or artwork.
Use the resolved primary furniture arrangement and secondary styling cluster. The three banners share design only; their supporting text must differ.
This image's ONLY banner supporting line: {visual['supporting_line']}
Use neutral collector language only; never attach a sport name to collector labels.
Avoid identical wall/camera combinations across recent fingerprints and this package without changing the assigned camera side; product fidelity wins. Vary only visual interpretation, never product identity, branding, edition limits or verified facts.
{SCARCITY_RULE}"""
