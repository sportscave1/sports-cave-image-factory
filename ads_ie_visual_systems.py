"""Visual-only composition for standard IE; persisted slot identities stay unchanged."""
import hashlib
import ads_ie_scenes as scene_library
import sports_cave_physical_realism as physical_realism



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


SAFE_HEADLINES = ("SPORTS CAVE COLLECTOR", "FOR YOUR COLLECTION", "A COLLECTOR STATEMENT")
FOOTER_FIELDS = ("headline_text", "supporting_line", "cta_text", "footer_pair_signature", "footer_emphasis", "eligible_headline_alternatives", "headline_fit_fallback")


def eligible_headlines(context):
    """Reuse the approved bank, with independent evidence gates per claim."""
    templates = list(SAFE_HEADLINES)
    limit = context.get("edition_limit")
    if limit:
        templates += [HEADLINES[i].replace("100", str(limit)) for i in (2, 3, 4)]
        if context.get("worldwide_verified") is True:
            templates.append(HEADLINES[0].replace("100", str(limit)))
        if context.get("no_second_run_verified") is True:
            templates.append(HEADLINES[1].replace("100", str(limit)))
        if context.get("remaining_editions") == limit and str(context.get("editions_sold")) in {"None", "0"}:
            templates.append(HEADLINES[5].replace("100", str(limit)))
    return templates


def eligible_support_lines(context):
    finality = context.get("no_second_run_verified") is True or context.get("retires_when_sold_out") is True
    return [line for i, line in enumerate(APPROVED_SUPPORT_LINES)
            if (i not in (0, 3) or finality) and (i not in (2, 5, 6, 8) or context.get("edition_limit"))]


def footer_emphasis(headline):
    return ("ownership" if headline == SAFE_HEADLINES[1] else
            "collector_identity" if headline in SAFE_HEADLINES else "scarcity")


def coherent_pair(headline, support):
    # A quantity headline is supported by emotion/identity, not a repeated quantity claim.
    if footer_emphasis(headline) == "collector_identity" and support == APPROVED_SUPPORT_LINES[7]:
        return False  # A collector label plus "Made for serious collectors" merely restates it.
    return not (footer_emphasis(headline) == "scarcity" and support in
                (APPROVED_SUPPORT_LINES[5], APPROVED_SUPPORT_LINES[6]))


def resolve_set_copy(visuals, context, headline_is_valid, recent_fingerprints=(), selections=()):
    """Resolve one immutable pack, preferring unseen/least-recently-used approved copy."""
    from itertools import combinations
    eligible = [h for h in eligible_headlines(context) if headline_is_valid(h)]
    supports = eligible_support_lines(context)
    if len(eligible) < 3 or len(supports) < 3:
        raise ValueError("Three distinct factually eligible footer headlines and sublines are required.")
    seed = visuals[0]["resolved_seed"]
    product_key = context.get("copy_product_key")
    history = [r for r in list(recent_fingerprints)[:scene_library.HISTORY_LIMIT] if isinstance(r, dict)
               and (not product_key or r.get("copy_product_key") == product_key)]
    old_heads = [r.get("on_image_headline") or r.get("campaign_line") for r in history]
    old_supports = [r.get("on_image_subline") or r.get("fomo_line") for r in history]
    old_pairs = list(zip(old_heads, old_supports))
    def age(value, values):
        return values.index(value) if value in values else len(history) + 1
    def text_rank(value, values):
        return (value in values, -age(value, values), stable_rank(seed, value))
    frozen = len(selections) == 3 and all(isinstance(v, dict) and v.get("headline_text") and v.get("supporting_line") for v in selections)
    if frozen:
        pairs = [(v["headline_text"], v["supporting_line"]) for v in selections]
    else:
        sets = [c for c in combinations(eligible, 3)
                if not context.get("edition_limit") or len({footer_emphasis(h) for h in c}) >= 2]
        sets.sort(key=lambda c: (sum(h in old_heads for h in c), -sum(age(h, old_heads) for h in c),
                                -len({footer_emphasis(h) for h in c}), stable_rank(seed, str(c))))
        chosen = sorted(sets[0], key=lambda h: stable_rank(seed, h))
        # Finite, at most 9 x 8 x 7 approved subline combinations. Recycle the
        # least-recent eligible words in different pairs after the finite bank fills.
        from itertools import permutations
        pairings = [list(zip(chosen, c)) for c in permutations(supports, 3)
                    if all(coherent_pair(h, sub) for h, sub in zip(chosen, c))]
        pairs = min(pairings, key=lambda ps: (
            sum(p in old_pairs[:3] for p in ps), sum(p in old_pairs for p in ps),
            sum(sub in old_supports for _, sub in ps), -sum(age(sub, old_supports) for _, sub in ps),
            -sum(age(p, old_pairs) for p in ps), stable_rank(seed, str(ps))))
    if len({h for h, _ in pairs}) != 3 or len({sub for _, sub in pairs}) != 3:
        raise ValueError("Saved footer selections must have three unique headlines and sublines.")
    assigned = {h for h, _ in pairs}
    for index, (visual, (headline, support)) in enumerate(zip(visuals, pairs)):
        alternatives = sorted([h for h in eligible if h not in assigned and coherent_pair(h, support)],
                              key=lambda h: text_rank(h, old_heads))
        if frozen and "eligible_headline_alternatives" in selections[index]:
            alternatives = list(selections[index]["eligible_headline_alternatives"])
        visual.update(headline_text=headline, supporting_line=support, fomo_line=support,
            cta_text="CLAIM YOUR EDITION", footer_emphasis=footer_emphasis(headline),
            footer_pair_signature=hashlib.sha256(f"{headline}|{support}".encode()).hexdigest()[:20],
            eligible_headline_alternatives=alternatives, headline_fit_fallback=headline)


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


CAMERAS = (
    "RIGHT: camera physically to the right of the artwork, looking left towards it",
    "FRONT: camera centred, directly facing the artwork",
    "LEFT: camera physically to the left of the artwork, looking right towards it",
)
# Compatibility metadata only; no independent shift, height or contradictory angle.
CAMERA_VARIATIONS = ("assigned camera role; level perspective",)


def resolved_camera_variation(visual, index, context, variation_token):
    return CAMERA_VARIATIONS[0]


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


# Reuse the draw-once/preserve-selection contract with richer curated attributes.
SCENES = scene_library.SCENES
ROOM_OPTIONS = tuple(tuple(dict.fromkeys(s["room_type"] for s in slot)) for slot in SCENES)
SCENE_VERSION = "IE COLLECTOR SCENES V2 ARTWORK FIRST"  # Saved prompt recognition stays stable.
COMBAT_PALETTES = tuple(tuple(dict.fromkeys(s["wall_colour"] for s in slot)) for slot in SCENES)


def is_combat(context):
    sport = f"{context.get('product_sport', '')} {context.get('selected_sport', '')}".casefold()
    return any(word in sport for word in ("combat", "boxing", "mma", "ufc", "martial", "wrestling", "kickboxing", "muay thai"))


def resolve_scene_set(visuals, context, recent_fingerprints=(), selections=()):
    """Draw once against captured history; complete saved attributes never redraw."""
    seed = f"{visuals[0]['resolved_seed']}|{context.get('market', '')}"
    fully_saved = len(selections) == 3 and all(isinstance(s, dict) and all(s.get(k) for k in
        ("scene_signature", "room_type", "wall_colour", "wall_finish", "lighting")) for s in selections)
    construction = physical_realism.resolve(context.get("physical_product"))
    chosen = [dict(s) for s in selections] if fully_saved else scene_library.select(seed, {**context, "frame_finish": construction.get("frame_finish", "")}, recent_fingerprints, selections)
    glazing = str(construction.get("glazing", "")).casefold()
    for index, (visual, scene) in enumerate(zip(visuals, chosen)):
        saved = selections[index] if index < len(selections) and isinstance(selections[index], dict) else {}
        scene.update({k: saved[k] for k in scene_library.SCENE_FIELDS if saved.get(k)})
        for key in ("room_materials", "secondary_cue", "time_of_day"):
            if saved.get(key):
                scene[key] = saved[key]
        if saved.get("wall_finish") and not saved.get("wall_material"):
            scene["wall_material"] = saved["wall_finish"]
        if saved.get("wall_colour") and not saved.get("wall_finish") and not saved.get("wall_material"):
            scene["wall_finish"] = scene["wall_material"] = saved["wall_colour"]
            scene["wall_colour_family"] = saved["wall_colour"]  # Do not mislabel an explicit override.
        if saved.get("wall_colour") and not saved.get("wall_colour_family"):
            match = next((w for w in scene_library.WALLS if w[0] == saved["wall_colour"]), None)
            scene.update(wall_colour_family=match[1] if match else saved["wall_colour"],
                         wall_visual_group=match[3] if match else "explicit colour override",
                         wall_lightness=saved.get("wall_lightness") or (match[2] if match else "user override; lightness not classified"))
        scene["scene_signature"] = scene_library.signature(scene)
        scene["scene_near_signature"] = scene_library.signature(scene, near=True)
        if "unglazed" in glazing or "no glazing" in glazing or glazing == "none":
            reflection = "Verified unglazed: no glazing, pane or glazing reflection. Preserve surface texture and natural frame-edge highlights."
        else:
            material = construction.get("glazing") or "existing glazing, only if present in the original product"
            reflection = (f"On {material}, a subtle but perceptible reflection from {scene['reflection_source']}: "
                f"{scene['reflection_placement']}, consistent with camera/light even straight-on. "
                "Keep face, title and edition details readable. No opaque streaks, arbitrary diagonal glare or glossy haze; never add a pane or call acrylic glass.")
        scene["glazing_treatment"] = saved.get("glazing_treatment") or reflection
        visual.update(scene)
        visual["assigned_camera_angle"] = visual["camera_side"]
        wall = f"{visual['wall_colour']} ({visual['wall_colour_family']}, {visual['wall_lightness']}); {visual['wall_finish']}"
        visual.update(room_profile_key=("hallway_gallery", "minimal_art_wall", "collector_interior")[index],
            room_profile=f"Room {index + 1}: {visual['room_type']}",
            room_materials=saved.get("room_materials") or f"{wall}; {visual['primary_cue']}",
            secondary_cue=saved.get("secondary_cue") or "no additional styling",
            time_of_day=saved.get("time_of_day") or visual["lighting"],
            atmosphere="restrained collector home; authentic residential materials",
            shot_distance=("close product view with a subtle receding passage", "close straight-on product wall with one resolved architectural glimpse", "close product view with the resolved residential depth arrangement")[index],
            physical_product=context.get("physical_product", {}))
        visual["purpose"] = f"Image {index + 1}: {visual['room_type']}; {visual['camera_side']}"
        visual["scene_brief"] = (
            "Use only the supplied framed product as the product reference. Its surrounding wall, lighting and room are not scene references and must not be copied. Rebuild the environment from this image’s resolved scene specification. "
            "Never use a previously generated mockup as the artwork source. "
            f"Room {index + 1} — HOME: {visual['room_type']} ({visual['home_setting']}); spatial structure: {visual.get('spatial_family', 'as saved')}. "
            f"WALL: {wall}. DEPTH: {visual['architectural_cue']}, positioned {visual.get('depth_position', 'as saved')}. PERIPHERAL CUE: {visual['primary_cue']}. "
            f"LIGHT: {visual['lighting']}; source position {visual.get('light_source_position', 'as saved')}. GLAZING: {visual['glazing_treatment']} " + (
                "Premium collector hallway: close artwork, subtle visible passage depth, peripheral console, warm picture light balanced with daylight.",
                "Minimal artwork-first wall: complete frame straight on, exactly one understated architectural glimpse of the resolved structure. Do not substitute a default side doorway or corridor. No full-room arrangement or foreground furniture.",
                "Distinctive collector interior: follow this resolved spatial arrangement with one peripheral furniture anchor. Neither a hallway nor a nearly empty wall; never substitute a default side-opening composition.",
            )[index] +
            " Breathing room above every outer frame corner and footer; camera proximity, never physical enlargement. "
            "Keep backdrop calm and panel joins/oak accents peripheral. No competing framed art, trophies, helmets or decorative clusters. "
            "CHECK: complete frame, true scale/source details, assigned camera, perceptible glazing only if present, mounting shadows/frame-edge highlights, exact footer/margins; compare homes at thumbnail size."
        )


def camera_wall_rules(visual, *, compact=False):
    if compact:
        return f"""LOCKED CAMERA / ROOM / WALL RESOLUTION
{SCENE_VERSION}
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']} (internal only).
Selected camera: {visual['camera_side']}. Keep verticals straight; never mirror the artwork.
SCENE: {visual['scene_brief']}
Framing: {visual['shot_distance']}; target width {visual['product_width']}; {visual['product_position']}. Camera distance determines prominence; never enlarge the physical product.
VARIANT PRECEDENCE — MANDATORY: use this one scene and camera; saved selections take precedence. Never mirror artwork.
Use only the exact selected headline and subline below. Pack-level fit selection is completed before this image call; do not pass alternatives or sibling copy into the call.
{SCARCITY_RULE}"""
    return f'''LOCKED CAMERA / ROOM / WALL RESOLUTION
{SCENE_VERSION}
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']} (internal only; never display).
Selected camera: {visual['camera_side']}.
Resolve exactly ONE camera using only this assigned definition. Keep verticals straight and Never mirror artwork.
SCENE: {visual['scene_brief']}
Framing: {visual['shot_distance']}; target width {visual['product_width']}; {visual['product_position']}. Achieve prominence through camera distance, never physical enlargement. Width targets yield to source aspect ratio, complete-frame visibility and a modest calm margin above the footer. Keep furniture/architecture near the perimeter or deeper behind the artwork. Avoid wide room views, excessive empty wall, dominating furniture and distracting background brightness. Retain enough subtle context to read as a real home.
VARIANT PRECEDENCE — MANDATORY
Honour the single resolved scene and explicit saved selections. Sibling metadata is comparison data only. Three different properties must differ in architecture, spatial layout, wall treatment, furniture/cue and light at thumbnail size; angle or accessory changes alone are insufficient. No scene blending or random sporting props. Avoid repeated dark-brown rooms, walnut, leather, whiskey props or orange light. Allow lighter and darker homes. Use the source palette, brightness, frame colour and verified construction for natural contrast. Automatic wall palettes exclude red, pink, rose, salmon, peach and strongly orange; honour explicit saved overrides. Keep the immediate artwork backdrop calm. Any supplied successful hallway image is a composition/light style reference only: inspect it when accessible, use its artwork prominence without copying its room, and never use it as the product source.
Use only this image's exact selected headline and subline. Complete any pack-level fit substitution before generation; pass no sibling copy or alternative lists into the image call.
Use neutral collector language only; never attach a sport name to collector labels.
{SCARCITY_RULE}'''
