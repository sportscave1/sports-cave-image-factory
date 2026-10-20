"""Visual-only composition for standard IE; persisted slot identities stay unchanged."""
import hashlib



VERSION = "IE PREMIUM SCARCITY DISTINCT FAN ROOMS V3 REFINED HEADLINE FIT"
FAMILIES = ("premium_scarcity",) * 3
SUPPORT_LINES = (
    "Once they’re claimed, this edition retires forever.",
    "Made for serious collectors.",
    "For collectors who know why it matters.",
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
# Frozen legacy room labels are copy-selection seeds only, never scene directions.
# Retain them so matching inputs keep their exact approved supporting lines.
COPY_ROOM_OPTIONS = (
    ("premium residential hallway / gallery corridor", "luxury apartment entrance gallery", "dark executive gallery corridor",
     "modern architectural foyer", "warm heritage hallway", "minimalist private collector gallery"),
    ("premium man cave / home office / collector den", "walnut executive study", "contemporary home office",
     "premium heritage library", "modern collector media den", "understated luxury apartment workspace"),
    ("private home bar / lounge / entertaining corner", "private whisky lounge", "modern home bar", "luxury leather lounge",
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
    """Preserve existing copy seeds and camera/format choices before scene resolution."""
    options = COPY_ROOM_OPTIONS[index]
    seed = visual["resolved_seed"]
    preferred = [option for option in options if
                 (context.get("product_era") == "historic" and any(w in option for w in ("heritage", "walnut", "club"))) or
                 (context.get("product_era") == "modern" and any(w in option for w in ("modern", "contemporary", "apartment")))]
    candidates = list(options) + preferred
    # These labels affect the established supporting-line choice, never the scene.
    copy_room = candidates[int.from_bytes(stable_rank(seed, f"room:{index}")[:4], "big") % len(candidates)]
    support = SUPPORT_LINES[index]
    if index == 0 and not context.get("edition_limit"):
        support = "A statement for your collection."
    camera = CAMERAS[index]
    visual.update(
        visual_family=FAMILIES[index], camera_role=("RIGHT", "FRONT", "LEFT")[index],
        resolved_camera_variation=resolved_camera_variation(visual, index, context, variation_token),
        camera_side=camera, camera_instruction=camera + ". Keep verticals straight and complete frame rigid. Never mirror artwork.",
        creative_variation_token=variation_token or "standard", room_type=copy_room,
        fan_archetype=fan_style(context)[0], supporting_line=support, fomo_line=support,
        product_width=("79-86%", "84-87%", "77-84%")[index],
        overlay_position="fixed opaque full-width black/gold footer across bottom 24–28%",
        product_position=("slightly left-of-centre", "central hero", "slightly right-of-centre")[index],
        composition="1024 x 1024 square; upper 72–76% lifestyle room; bottom 24–28% opaque promotional banner",
    )


# Curated whole scenes follow the product-page draw-once/preserve-selection approach.
# Slot palettes are disjoint so every resolved pack reads as three properties.
SCENES = (
    (
        ("terrace collector hallway", "long narrow Victorian passage with high ceiling", "chalk-white lime plaster", "slim painted console at outer left", "warm picture light with cool side daylight"),
        ("apartment entrance gallery", "broad apartment passage receding past a recessed opening", "pale sage matte paint", "slender pale ash console at outer left", "soft north-window daylight with warm picture-light fill"),
        ("heritage collector hallway", "tall Edwardian passage with distant archway", "dusty blue mineral plaster", "narrow ebonised console at outer left", "overcast side daylight with gentle warm picture lighting"),
        ("modern courtyard hallway", "low wide passage receding toward a courtyard", "warm grey fine microcement", "slim travertine console at outer left", "filtered courtyard daylight with warm picture-light accents"),
        ("coastal collector corridor", "airy deep passage with distant stair return", "soft ivory limewash", "narrow bleached-oak console at outer left", "bright diffused morning daylight with gentle picture lighting"),
        ("mid-century entrance gallery", "compact offset passage with clerestory depth", "warm mineral-grey brushed plaster", "slim tubular steel console at outer left", "late afternoon clerestory daylight with warm picture-light fill"),
    ),
    (
        ("minimal apartment art wall", "tightly cropped high-ceiling apartment wall", "mineral-blue matte paint", "one small doorway glimpse into a softly focused sitting room at the far left", "cool soft east-window morning light"),
        ("minimal courtyard-house art wall", "close composition on a low modern residential wall", "pale warm-stone limewash", "one shallow corridor return at the far right", "diffused courtyard noon light"),
        ("minimal townhouse art wall", "tightly framed tall townhouse wall", "deep teal fine plaster", "one doorway sliver at the far left", "soft lateral daylight from the right"),
        ("minimal coastal art wall", "close composition on a compact coastal cottage wall", "pale sea-glass green brushed plaster", "one window recess with a partial furniture silhouette at the far right", "luminous coastal overcast daylight"),
        ("minimal loft art wall", "tightly composed broad loft wall", "cool charcoal mineral paint", "one distant room glimpse at the far right", "broad diffuse skylight"),
        ("minimal garden-home art wall", "close composition on a modest garden-home wall", "smoked taupe mineral paint", "one narrow doorway into a softly focused room at the far right", "soft garden-reflected afternoon light"),
    ),
    (
        ("refined bay-window sitting room", "angled bay-window seating recess", "deep olive lime plaster", "one oatmeal wool seating edge at the outer perimeter", "cool bay-window daylight with soft neutral lamp fill"),
        ("architectural split-level living corner", "sunken living corner with distant floor-level change", "pale silver-grey mineral plaster", "one low cobalt fabric settee edge at the far side", "high side-window afternoon light"),
        ("heritage library lounge", "off-centre library alcove with a deep side-window reveal", "desaturated navy mineral paint", "one painted reading-bench edge deep in the alcove", "soft rear-window daylight with a shaded reading light"),
        ("quiet modern private retreat", "low-ceiling intimate seating corner with deep window reveal", "warm off-white textured plaster", "one moss-green banquette edge at the far side of the recess", "gentle early-evening window light with neutral indirect fill"),
        ("courtyard collector sitting room", "open residential seating corner looking toward an offset courtyard", "muted petrol-blue limewash", "one cream woven settee edge near the courtyard opening", "balanced courtyard morning daylight"),
        ("contemporary collector living recess", "double-height living recess with an off-centre window", "pale sand fine plaster", "one ink-blue upholstered seating edge at the outer perimeter", "soft high-window overcast light"),
    ),
)
ROOM_OPTIONS = tuple(tuple(scene[0] for scene in slot) for slot in SCENES)
SCENE_VERSION = "IE COLLECTOR SCENES V2 ARTWORK FIRST"
COMBAT_PALETTES = (
    ("warm stone fine plaster", "mineral grey subtle limewash"),
    ("charcoal mineral paint", "graphite fine plaster"),
    ("smoked taupe limewash", "muted olive mineral paint", "desaturated navy fine plaster"),
)


def is_combat(context):
    sport = f"{context.get('product_sport', '')} {context.get('selected_sport', '')}".casefold()
    return any(word in sport for word in ("combat", "boxing", "mma", "ufc", "martial", "wrestling", "kickboxing", "muay thai"))



def resolve_scene_set(visuals, context, recent_fingerprints=(), selections=()):
    """Resolve all slots before rendering; saved selections win, history only on draws.

    Callers pass the snapshot of recent fingerprints captured at fresh-pack creation,
    never the mutable live history when reopening. No new persistence is needed.
    """
    seed = f"{visuals[0]['resolved_seed']}|{context.get('market', '')}"
    for index, visual in enumerate(visuals):
        saved = selections[index] if index < len(selections) else {}
        saved = saved if isinstance(saved, dict) else {}
        heritage = context.get("product_era") == "historic" or context.get("artwork_mood") == "heritage"
        def scene_rank(scene):
            suitable = heritage and any(word in scene[0] for word in ("heritage", "terrace", "library"))
            return int.from_bytes(stable_rank(seed, scene[0]), "big") // (2 if suitable else 1)
        candidates = sorted(SCENES[index], key=scene_rank)
        recent = {f.get("room_type") for f in list(recent_fingerprints)[:18] if isinstance(f, dict)}
        history = [f.get("room_type") for f in list(recent_fingerprints)[:18] if isinstance(f, dict)]
        # Exhausted libraries fall back to the least recently seen scene.
        fallback = max(candidates, key=lambda s: min(
            (i for i, room in enumerate(history) if room == s[0]), default=len(history)))
        scene = next((s for s in candidates if s[0] not in recent), fallback)
        room, architecture, wall, cue, light = scene
        if is_combat(context):
            # Slot palettes span lighter/darker neutral homes and stay distinct.
            wall = min(COMBAT_PALETTES[index], key=lambda value: stable_rank(seed, f"{index}:{value}"))
        visual.update(
            room_profile_key=("hallway_gallery", "minimal_art_wall", "collector_interior")[index],
            room_profile=f"Room {index + 1}: {room}", room_type=room,
            wall_colour=wall, wall_material=wall, wall_finish=wall,
            room_materials=f"{wall}; {cue}", primary_cue=cue,
            secondary_cue="no additional styling", architectural_cue=architecture,
            lighting=light, time_of_day=light,
            atmosphere="restrained collector home; authentic residential materials",
            shot_distance=("close product view with a subtle receding passage", "close straight-on product wall with one edge glimpse of home", "close product view with restrained alcove depth")[index],
        )
        # Explicit saved/editable scene fields retain precedence over automatic choices.
        for key in ("room_type", "wall_colour", "wall_material", "wall_finish", "room_materials",
                    "primary_cue", "secondary_cue", "architectural_cue", "lighting", "time_of_day"):
            if saved.get(key):
                visual[key] = saved[key]
        if saved.get("wall_finish") and not saved.get("wall_material"):
            visual["wall_material"] = saved["wall_finish"]
        if saved.get("wall_colour") and not saved.get("wall_finish") and not saved.get("wall_material"):
            visual["wall_finish"] = visual["wall_material"] = saved["wall_colour"]
        wall_description = "; ".join(dict.fromkeys((visual["wall_colour"], visual["wall_finish"])))
        visual["room_materials"] = saved.get("room_materials") or f"{wall_description}; {visual['primary_cue']}"
        visual["room_profile"] = f"Room {index + 1}: {visual['room_type']}"
        visual["purpose"] = f"Image {index + 1}: {visual['room_type']}; {visual['camera_side']}"
        visual["physical_product"] = context.get("physical_product", {})
        visual["scene_brief"] = (
            f"{visual['room_profile']}; {visual['architectural_cue']}; {wall_description}; "
            f"{visual['primary_cue']}; {visual['lighting']}. " + (
                "Premium collector hallway: close artwork-first view, subtle visible passage depth, restrained console at the perimeter, warm picture light balanced with natural daylight.",
                "Minimal artwork-first wall composition: complete frame straight on and prominent on mobile, a modest calm wall margin and exactly one understated architectural glimpse at an outer edge. The glimpse stays secondary. No full-room arrangement, large foreground desk, chair, cabinet or decorative cluster.",
                "Distinctive collector interior: dominant artwork, off-centre alcove/window/adjoining-room depth and one peripheral furniture anchor. Neither a hallway nor a nearly empty wall; simplify the setting if it competes with the product. No bland empty-wall-and-armchair formula, flat light or showroom staging.",
            )[index]
        )


def camera_wall_rules(visual, *, compact=False):
    if compact:
        return f"""LOCKED CAMERA / ROOM / WALL RESOLUTION
{SCENE_VERSION}
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']} (internal only).
Selected camera: {visual['camera_side']}; refinement: {visual['resolved_camera_variation']}.
SCENE: {visual['scene_brief']}
Framing: {visual['shot_distance']}; target width {visual['product_width']}; {visual['product_position']}. Camera distance determines prominence; never enlarge the physical product.
VARIANT PRECEDENCE — MANDATORY: use this one scene and camera; saved selections take precedence. Never mirror artwork.
Reserved sibling headlines: {[s['headline_text'] for s in visual.get('sibling_summaries', [])]}.
Only on a measured mobile fit failure, use an unused eligible alternative {visual.get('eligible_headline_alternatives', [])}, then this route's reserved truthful fallback {visual.get('headline_fit_fallback')}. Never repeat a sibling headline or use its reserved fallback.
{SCARCITY_RULE}"""
    return f'''LOCKED CAMERA / ROOM / WALL RESOLUTION
{SCENE_VERSION}
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']} (internal only; never display).
Selected camera: {visual['camera_side']}.
Selected viewpoint refinement: {visual['resolved_camera_variation']}. Resolve exactly ONE camera; retain RIGHT / FRONT / LEFT and Never mirror artwork.
SCENE: {visual['scene_brief']}
Framing: {visual['shot_distance']}; target width {visual['product_width']}; {visual['product_position']}. Achieve prominence through camera distance, never physical enlargement. Width targets yield to source aspect ratio, complete-frame visibility and a modest calm margin above the footer. Keep furniture/architecture near the perimeter or deeper behind the artwork. Avoid wide room views, excessive empty wall, dominating furniture and distracting background brightness. Retain enough subtle context to read as a real home.
VARIANT PRECEDENCE — MANDATORY
Honour the single resolved scene and explicit saved selections. Sibling metadata is comparison data only. Three different properties must differ in architecture, spatial layout, wall treatment, furniture/cue and light at thumbnail size; angle or accessory changes alone are insufficient. No scene blending or random sporting props. Avoid repeated dark-brown rooms, walnut, leather, whiskey props or orange light. Allow lighter and darker homes. Use the source palette, brightness, frame colour and verified construction for natural contrast. Automatic wall palettes exclude red, pink, rose, salmon, peach and strongly orange; honour explicit saved overrides. Keep the immediate artwork backdrop calm. Any supplied successful hallway image is a composition/light style reference only: inspect it when accessible, use its artwork prominence without copying its room, and never use it as the product source.
Sibling headlines reserved for other routes: {[s['headline_text'] for s in visual.get('sibling_summaries', [])]}. Never repeat them.
This image's ONLY banner supporting line: {visual['supporting_line']}
The only exception to exact resolved headline wording is a measured visual-fit failure. Headline fit alternatives, only if the assigned headline fails actual rendered mobile fit: {visual.get('eligible_headline_alternatives', [])}.
Reserve this route's truthful compact fallback: {visual.get('headline_fit_fallback', visual.get('headline_text'))}. Other routes must never use this reserved fallback. Select an unused eligible alternative first; compare sibling headlines and never repeat one. Display only the final selected headline, never this list or selection notes.
Use neutral collector language only; never attach a sport name to collector labels.
{SCARCITY_RULE}'''
