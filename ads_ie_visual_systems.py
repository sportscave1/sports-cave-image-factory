"""Visual-only composition for standard IE; persisted slot identities stay unchanged."""
import hashlib



VERSION = "IE PREMIUM SCARCITY DISTINCT FAN ROOMS V3 REFINED HEADLINE FIT"
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

# Approved copy remains separate from fit eligibility; never truncate a claim.
HEADLINES = (
    "LIMITED TO 100 WORLDWIDE",
    "STRICTLY 100 EDITIONS. NO SECOND RUN.",
    "JUST 100 EDITIONS. EVER.",
    "ONLY 100 EDITIONS WILL EVER EXIST",
    "STRICTLY LIMITED TO 100 EDITIONS",
    "LIMITED EDITION. ONLY 100 AVAILABLE",
)
APPROVED_SUPPORT_LINES = (
    "Once they’re gone, they’re gone.",
    "Not everyone gets to own greatness, but you can.",
    "The moment lasts. The opportunity won’t.",
    "When the final edition goes, that’s it.",
    "A rare piece for those who know its meaning.",
    "The run is limited. The memory isn’t.",
    "A limited edition, made for true fans.",
    "Made for serious collectors only.",
    "Some moments are worth claiming while you can.",
)
# Each option retains the route's architectural/furniture/lighting grammar.
ROOM_OPTIONS = (
    (ROOMS[0][1], "luxury apartment entrance gallery", "dark executive gallery corridor",
     "modern architectural foyer", "warm heritage hallway", "minimalist private collector gallery"),
    (ROOMS[1][1], "walnut executive study", "contemporary home office",
     "premium heritage library", "modern collector media den", "understated luxury apartment workspace"),
    (ROOMS[2][1], "private whisky lounge", "modern home bar", "luxury leather lounge",
     "refined entertainment room", "private club-style home retreat"),
)


def stable_rank(seed, value):
    return hashlib.sha256(f"{seed}|{value}".encode("utf-8")).digest()


def eligible_headlines(context):
    """Image-only claims: verified edition total is not remaining inventory."""
    limit = context.get("edition_limit")
    if not limit:
        return ["SPORTS CAVE COLLECTOR", "FOR YOUR COLLECTION", "A COLLECTOR STATEMENT"]
    templates = [HEADLINES[i] for i in (2, 3, 4)]
    if context.get("worldwide_verified") is True:
        templates.append(HEADLINES[0])
    if context.get("no_second_run_verified") is True:
        templates.append(HEADLINES[1])
    # A remaining count equal to the total is required; contradictory sales data wins.
    if context.get("remaining_editions") == limit and str(context.get("editions_sold")) in {"None", "0"}:
        templates.append(HEADLINES[5])
    return [h.replace("100", str(limit)) for h in templates]


def resolve_set_copy(visuals, context, headline_is_valid):
    """Resolve together so fit, distinctness and evidence hold across all slots."""
    eligible = [h for h in eligible_headlines(context) if headline_is_valid(h)]
    if len(eligible) < len(visuals):
        raise ValueError("Three distinct factually eligible image headlines are required.")
    seed = visuals[0]["resolved_seed"]
    eligible.sort(key=lambda h: stable_rank(seed, h))
    used_support = set()
    for index, visual in enumerate(visuals):
        visual["headline_text"] = eligible[index]
        limit = context.get("edition_limit")
        visual["headline_fit_fallback"] = (
            (f"LIMITED TO {limit} EDITIONS", f"{limit} EDITIONS TOTAL", f"AN EDITION OF {limit}")[index]
            if limit else eligible[index]
        )
        visual["eligible_headline_alternatives"] = [h for h in eligible[len(visuals) + index:len(visuals) + index + 1]]
        if context.get("edition_limit"):
            # Quantity headlines pair with meaning/identity, not repeated quantity
            # or final-run claims. All nine remain approved for future fit contexts.
            choices = [APPROVED_SUPPORT_LINES[i] for i in (1, 2, 4, 7, 8)]
            preferred = (4 if context.get("product_era") == "historic" else
                         (7 if "study" in visual["room_type"] or "gallery" in visual["room_type"] else 2))
            choices.sort(key=lambda line: (line != APPROVED_SUPPORT_LINES[preferred],
                         stable_rank(f"{seed}|{visual['room_type']}", line)))
            support = next(line for line in choices if line not in used_support)
            visual.update(supporting_line=support, fomo_line=support)
            used_support.add(support)


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
# Five carefully limited natural viewpoints. The RIGHT / FRONT / LEFT identity of
# each image is unchanged; only camera height and subtle distance/offset varies.
CAMERA_VARIATIONS = (
    "eye-level, balanced natural perspective",
    "a little above artwork centre with minimal downward perspective",
    "just below artwork centre with very subtle upward perspective",
    "eye-level with a restrained 1–2 degree lateral shift inward, staying within the assigned right/centre/left camera role",
    "eye-level with a restrained 1–2 degree lateral shift outward, staying within the assigned right/centre/left camera role",
)

def resolved_camera_variation(visual, index, context, variation_token):
    """Deterministically choose one of five safe angles; edits and reruns stay stable."""
    user_choice = str(visual.get("resolved_camera_variation") or "").strip()
    if user_choice:
        return user_choice
    identity = "|".join((str(variation_token or "standard"), str(index)))
    digest = hashlib.sha256(identity.encode("utf-8")).digest()
    return CAMERA_VARIATIONS[int.from_bytes(digest[:4], "big") % len(CAMERA_VARIATIONS)]

SCARCITY_RULE = ('ON-IMAGE SCARCITY WORDING: Use only the exact resolved headline. The approved '
                 'geographic wording is allowed only when explicitly included in the resolved verified headline. '
                 'Do not append geographic scope to any other claim. Never invent a limit. '
                 'Immutable wording already inside the source artwork stays untouched.')



def resolve_visual_system(visual, index, context, variation_token):
    """Extend the existing resolved product context, never resolve commercial facts here."""
    room_key, room, primary, secondary, architecture, lighting = ROOMS[index]
    options = ROOM_OPTIONS[index]
    seed = visual["resolved_seed"]
    # Heritage/modern context gently favours suitable options without eliminating variety.
    preferred = [option for option in options if
                 (context.get("product_era") == "historic" and any(w in option for w in ("heritage", "walnut", "club"))) or
                 (context.get("product_era") == "modern" and any(w in option for w in ("modern", "contemporary", "apartment")))]
    candidates = list(options) + preferred
    room = candidates[int.from_bytes(stable_rank(seed, f"room:{index}")[:4], "big") % len(candidates)]
    fan_key, atmosphere, wood, metal, walls = fan_style(context)
    wall = walls[index]
    camera = CAMERAS[index]
    support = SUPPORT_LINES[index]
    camera_variation = resolved_camera_variation(visual, index, context, variation_token)
    if index == 0 and not context.get("edition_limit"):
        support = "A statement for your collection."
    visual.update(visual_family=FAMILIES[index], camera_role=("RIGHT", "FRONT", "LEFT")[index],
                  resolved_camera_variation=camera_variation,
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
                  product_width=("79-86%", "84-87%", "77-84%")[index],
                  shot_distance=("closer editorial passage context", "closer frontal product hero", "closer intimate entertaining context")[index],
                  overlay_position="fixed opaque full-width black/gold footer across bottom 24–28%",
                  product_position=("slightly left-of-centre", "central hero", "slightly right-of-centre")[index],
                  composition="1024 x 1024 square; upper 72–76% lifestyle room; bottom 24–28% opaque promotional banner")


def camera_wall_rules(visual):
    return f"""LOCKED CAMERA / ROOM / WALL RESOLUTION
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']}
Use the token only for creative freshness; never display it or internal metadata on the image.
Selected camera: {visual['camera_side']}.
Selected one of five subtle photographic viewpoint refinements: {visual['resolved_camera_variation']}. This never changes the assigned RIGHT / FRONT / LEFT role; never mirror, crop or shrink the product.
Resolve exactly ONE camera: use the selected value above, not a menu of alternatives. Keep the assigned right / centre / left camera role. Never mirror artwork.
Resolved room: {visual['room_profile']}.
Framing: {visual['shot_distance']}; product width {visual['product_width']} of canvas; {visual['product_position']}. Increase apparent frame prominence by about 10% relative to previous results: move the camera modestly closer, not enlarge or distort the product. The artwork anchors the upper photographed area; room context supports it. Keep all outer frame edges fully visible, natural perspective, realistic hanging and controlled glass reflections. Width targets yield to source aspect ratio, complete-frame visibility and clean breathing room above the footer. Leave enough room context to identify this environment while keeping the artwork the largest visual element.
Resolved wall: {visual['wall_colour']}.
Resolved material treatment: {visual['room_materials']}.
Analyse the actual attached product, SPORT, MARKET, title, palette, brightness, frame colour, emotional mood, era/nostalgia and campaign context. The actual product wins over sport tendencies. Preserve the one resolved scene and ensure the unchanged frame separates clearly from its wall.
VARIANT PRECEDENCE — MANDATORY
The assigned room, camera and support line override generic lifestyle suggestions. Sibling metadata is comparison data only: never blend rooms or copy another slot's support line. The hallway must visibly read as a passage; the office as a workspace; the bar/lounge as a private entertaining space. Never substitute the same console-and-chair room or mirror another image.
Fan styling for this product: {visual['atmosphere']}.
Express this through the resolved furniture, finishes and lighting. Never add literal sports props, extra posters, team logos, themed novelty decor or clutter. Product palette and frame contrast guide subtle tonal adjustments without changing the room type or artwork.
Use the resolved primary furniture arrangement and secondary styling cluster. The three banners share design; their selected headlines and supporting text must differ. Never display internal selection notes. No showroom, AI-catalogue styling or commercial bar.
This image's ONLY banner supporting line: {visual['supporting_line']}
The only exception to exact resolved headline wording is a measured visual-fit failure. Headline fit alternatives, only if the assigned headline fails actual rendered mobile fit: {visual.get('eligible_headline_alternatives', [])}.
Reserve this route's truthful compact fallback: {visual.get('headline_fit_fallback', visual.get('headline_text'))}. Other routes must never use this reserved fallback. Select an unused eligible alternative first; compare sibling headlines and never repeat one. Display only the final selected headline, never this list or selection notes.
Use neutral collector language only; never attach a sport name to collector labels.
Avoid identical wall/camera combinations across recent fingerprints and this package without changing the assigned camera side; product fidelity wins. Vary only visual interpretation, never product identity, branding, edition limits or verified facts.
{SCARCITY_RULE}"""
