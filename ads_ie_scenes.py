"""Curated IE homes, bounded attribute-level selection; no storage or image backend."""
import hashlib
import json

VERSION = "IE CURATED HOMES V3"
HISTORY_LIMIT = 36  # Twelve packs, newest scene first, using the existing history contract.
SCENE_FIELDS = (
    "scene_selection_version", "scene_id", "home_setting", "architecture_style", "room_type",
    "wall_colour", "wall_colour_family", "wall_lightness", "wall_visual_group", "wall_material", "wall_finish",
    "architectural_cue", "depth_family", "primary_cue", "furniture_cue", "lighting", "light_source",
    "light_direction", "light_softness", "light_family", "reflection_source", "reflection_placement",
    "glazing_treatment", "assigned_camera_angle", "scene_signature", "scene_near_signature", "history_exclusions_relaxed",
    "depth_position", "light_source_position", "spatial_family", "residential_cue_family", "scene_slot",
    "collector_detail", "collector_detail_family",
)

# Colour and construction are authored together, not independently randomised.
ROOM_STYLE = (
    "Sports Cave premium sports collector / man cave feel with subtle rugged character. "
    "Automatic walls use only charcoal, graphite, smoky grey, deep navy, midnight blue, heritage green, "
    "muted olive, earthy taupe or weathered stone, in compatible shades of matte painted brick, textured "
    "plaster, concrete, natural stone or aged timber. Keep each scene's existing composition; give the "
    "resolved homes different colour families and wall finishes, mixing dark, mid-tone and lighter earthy "
    "shades. Rotate compatible combinations through the available history on fresh generations/refreshes; "
    "never assign a colour permanently to an ad slot. Keep the edition clearly visible through tonal "
    "separation and coherent light. No excessive props, artificial grunge or three identical dark rooms."
)
WALLS = (
    ("weathered stone", "weathered stone", "light", "stone", "matte painted brick"),
    ("light weathered stone", "weathered stone", "light", "stone", "natural stone"),
    ("light earthy taupe", "earthy taupe", "light", "taupe", "textured plaster"),
    ("pale weathered stone", "weathered stone", "light", "stone", "concrete"),
    ("earthy taupe", "earthy taupe", "mid", "taupe", "textured plaster"),
    ("smoked earthy taupe", "earthy taupe", "mid", "taupe", "aged timber"),
    ("smoky grey", "smoky grey", "mid", "grey", "concrete"),
    ("light smoky grey", "smoky grey", "light", "grey", "matte painted brick"),
    ("graphite", "graphite and charcoal", "dark", "grey", "aged timber"),
    ("charcoal", "graphite and charcoal", "dark", "grey", "matte painted brick"),
    ("muted olive", "muted olive", "mid", "olive", "textured plaster"),
    ("weathered stone", "weathered stone", "light", "stone", "aged timber"),
    ("deep navy", "deep navy and midnight blue", "dark", "blue", "matte painted brick"),
    ("midnight blue", "deep navy and midnight blue", "dark", "blue", "textured plaster"),
    ("deep heritage green", "heritage green", "dark", "forest", "natural stone"),
    ("muted heritage green", "heritage green", "mid", "forest", "textured plaster"),
    ("weathered stone", "weathered stone", "light", "stone", "textured plaster"),
    ("light earthy taupe", "earthy taupe", "light", "taupe", "matte painted brick"),
    ("muted olive", "muted olive", "mid", "olive", "aged timber"),
    ("pale weathered stone", "weathered stone", "light", "stone", "natural stone"),
)

# setting, architecture, depth, furniture/edge cue, compatible wall indices, light rig.
# Image 1 always remains a collector hallway; Image 2 is one minimal edge glimpse;
# Image 3 is a restrained interior. Shared setting labels prevent same-home packs.
HOMES = (
    (
        ("Heritage collector hallway", "Edwardian terrace", "tall narrow passage receding to a distant arch", "slim painted console at outer left", (0, 1, 4, 8, 12, 18), "side window"),
        ("Contemporary courtyard home", "low contemporary courtyard house", "broad low passage receding toward a courtyard opening", "slender pale ash console at outer left", (2, 3, 6, 10, 14, 17), "courtyard window"),
        ("Refined apartment living corner", "high-ceiling city apartment entrance", "compact entrance passage with a deep recessed doorway", "narrow blackened steel console at outer left", (0, 5, 7, 9, 13, 16), "tall window"),
        ("Architectural entry alcove", "modern oak-accented home", "offset entry passage with a shallow oak-lined return", "slim limestone console at outer left", (2, 3, 5, 10, 15, 17), "clerestory window"),
        ("Bay-window sitting room", "Victorian bay-window house entrance", "restrained collector passage receding toward a distant bay opening", "narrow painted console at outer left", (0, 1, 4, 11, 12, 15), "bay window"),
        ("Split-level lounge", "mid-century split-level home entrance", "collector passage with a distant split-level stair return", "slim tubular steel console at outer left", (2, 3, 6, 7, 10, 14), "high side window"),
        ("Quiet home study", "Georgian collector house entrance", "high collector corridor receding past an off-centre study doorway", "narrow ebonised console at outer left", (0, 1, 4, 8, 12, 18), "garden window"),
        ("Restrained media lounge", "contemporary garden-home entrance", "low collector corridor with a distant stepped wall return", "slim pale oak console at outer left", (3, 5, 6, 9, 11, 15, 17), "corner window"),
    ),
    (
        ("Refined apartment living corner", "quiet contemporary apartment", "one tall recessed window reveal with a distant furniture silhouette at the far left", "none; architecture is the single peripheral cue", (0, 3, 5, 7, 9, 13, 14, 17), "tall window"),
        ("Contemporary courtyard home", "single-storey courtyard house", "one shallow limestone passage return at the far right with a tiny softly lit adjoining sitting-area glimpse", "none; architecture is the single peripheral cue", (2, 3, 6, 10, 14, 17), "courtyard window"),
        ("Heritage collector hallway", "quiet heritage townhouse interior", "one solid heritage wall pier framing a softly lit stair-landing glimpse at the far left", "none; architecture is the single peripheral cue", (0, 1, 4, 8, 12, 18), "side window"),
        ("Bay-window sitting room", "restrained bay-window home", "one window recess with a partial distant furniture silhouette at the far right", "none beyond the silhouette inside the single window recess", (0, 4, 11, 12, 15, 16), "bay window"),
        ("Quiet home study", "garden-facing reading home", "one garden-facing window recess with a distant seating silhouette at the far right", "none; no desk in the photographic foreground", (0, 4, 5, 10, 14, 19), "garden window"),
        ("Architectural entry alcove", "oak-accented architectural home", "one small oak-lined opening at the far left revealing a softly lit recessed window seat", "none; architecture is the single peripheral cue", (2, 3, 5, 10, 15, 17), "clerestory window"),
        ("Split-level lounge", "mid-century split-level home", "one lowered floor-plane glimpse beyond a low residential ledge at the far right with a softly lit recessed bench edge", "none; architecture is the single peripheral cue", (2, 6, 7, 9, 10, 13, 17), "high side window"),
        ("Restrained media lounge", "contemporary private residential retreat", "one broad layered wall return at the far left revealing a softly lit sliver of an adjoining living area", "none; architecture is the single peripheral cue", (0, 5, 6, 9, 11, 14, 16), "corner window"),
    ),
    (
        ("Bay-window sitting room", "refined Victorian sitting room", "off-centre bay-window seating recess", "one oatmeal wool banquette edge at the outer perimeter", (0, 1, 4, 11, 12, 15), "bay window"),
        ("Split-level lounge", "mid-century split-level lounge", "sunken living platform beyond a low offset parapet, with a high window; no side passage", "one ink-blue fabric settee edge at the far side", (2, 3, 6, 7, 10, 14), "high side window"),
        ("Quiet home study", "heritage library retreat", "two perpendicular walls meeting around a shallow reading bench, with lateral window light; no doorway", "one painted reading-bench edge deep in the alcove", (0, 1, 4, 8, 12, 18), "garden window"),
        ("Restrained media lounge", "quiet contemporary media retreat", "low residential seating corner with two planes of corner glazing; no narrow side opening", "one moss wool banquette edge at the far side", (0, 5, 6, 9, 11, 15, 16), "corner window"),
        ("Contemporary courtyard home", "refined contemporary courtyard sitting room", "off-centre living recess looking toward a courtyard opening", "one cream woven settee edge near the distant opening", (2, 3, 6, 10, 14, 17), "courtyard window"),
        ("Refined apartment living corner", "high-ceiling apartment living corner", "double-height living volume with an upper clerestory and a visible ceiling-height change", "one pale grey linen seating edge at the outer perimeter", (0, 5, 7, 9, 13, 16, 19), "tall window"),
        ("Architectural entry alcove", "architectural home adjoining-room retreat", "oak-detailed sitting-room corner with an adjoining-room ceiling step; no receding passage", "one quiet woven bench edge deep in the recess", (2, 3, 5, 10, 15, 17), "clerestory window"),
        ("Quiet home study", "contemporary garden library lounge", "garden-facing reading corner formed by intersecting walls and a broad window sill", "one pale oak reading-bench edge at the outer perimeter", (0, 4, 5, 10, 14, 19), "side window"),
    ),
)

# Structural classes describe the space, not the light source or room label.
# The same eight home options remain available in each role; only their small
# architectural glimpse is made explicit, so colour changes cannot pass as variety.
SPATIAL_FAMILIES = (
    ("circulation axis",) * 8,
    ("window volume", "folded wall plane", "solid architectural pier", "window volume",
     "window volume", "recessed seating opening", "split-level plane", "layered wall planes"),
    ("window volume", "split-level plane", "intersecting-wall corner", "window volume",
     "courtyard court", "double-height volume", "ceiling step", "intersecting-wall corner"),
)
INTERIOR_DEPTH_POSITIONS = (
    "rear bay volume", "low rear floor-level step", "rear intersecting-wall corner", "rear corner glazing",
    "rear courtyard threshold", "upper rear vertical volume", "rear sitting-room ceiling step", "rear reading corner",
)


def cue_family(text, fallback):
    text = str(text).lower()
    if any(w in text for w in ("media-lounge", "pool-table", "home-bar")): return "man cave furnishing"
    if "console" in text: return "console"
    if "bench" in text or "banquette" in text: return "built-in seating"
    if any(w in text for w in ("chair", "settee", "sofa", "seating edge")): return "upholstered seating"
    return fallback


LIGHTS = (
    ("left", "soft directional morning daylight", "morning-side", "recognisable upper-left peripheral window reflection"),
    ("right", "broad diffused overcast daylight", "overcast-side", "recognisable broad upper-right peripheral window reflection"),
    ("left", "soft raking late-afternoon daylight", "afternoon-raking", "recognisable lower-left peripheral window reflection"),
)


def _rank(seed, value):
    return hashlib.sha256(f"{seed}|{value}".encode("utf-8")).digest()


def signature(scene, *, near=False):
    # Deliberately excludes token, adjectives, IDs, camera role and copy.
    keys = (("wall_visual_group", "wall_lightness", "wall_finish", "depth_family", "light_family", "depth_position", "spatial_family") if near else
            ("home_setting", "architecture_style", "wall_colour", "wall_lightness", "wall_finish",
             "architectural_cue", "depth_position", "furniture_cue", "light_source", "light_source_position", "light_direction", "light_softness", "spatial_family", "residential_cue_family"))
    values = [scene.get(k, "") for k in keys]
    if near:
        # Grey/graphite/charcoal and plaster-like treatments can look almost alike.
        values[1] = "any-grey-value" if values[0] == "grey" else values[1]
        if values[2] in {"subtle limewash", "fine mineral plaster", "fine microcement", "textured plaster", "concrete"}:
            values[2] = "quiet mineral texture"
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def candidates(slot):
    result = []
    for h, (setting, architecture, depth, furniture, walls, source) in enumerate(HOMES[slot]):
        for w in walls:
            colour, family, lightness, group, finish = WALLS[w]
            for l, (direction, softness, light_family, placement) in enumerate(LIGHTS):
                light = f"{softness} from the {source} on the {direction}"
                if slot == 0:
                    light += "; gentle warm picture-light fill balanced with daylight"
                if slot == 0:
                    furniture = ("slim dark oak console at outer left", "restrained smoked walnut console/joinery at outer left", "narrow ebonised timber console at outer left")[h % 3]
                elif slot == 2:
                    architecture = architecture.removesuffix(" residential man cave") + " residential man cave"
                    furniture = ("one leather media-lounge edge at the outer perimeter", "one pool-table corner deep in the room", "one restrained home-bar joinery edge deep in the recess")[h % 3]
                scene = dict(scene_selection_version=VERSION, scene_id=f"{slot}:{h}:{w}:{l}", scene_slot=slot,
                    home_setting=setting, architecture_style=architecture,
                    room_type=(f"{architecture} collector hallway" if slot == 0 else
                               f"minimal {architecture} product wall" if slot == 1 else architecture),
                    wall_colour=colour, wall_colour_family=family, wall_lightness=lightness, wall_visual_group=group,
                    wall_material=finish, wall_finish=finish, architectural_cue=depth,
                    depth_family=source, primary_cue=depth if slot == 1 else furniture, furniture_cue=furniture,
                    lighting=light, light_source=source, light_direction=direction, light_softness=softness,
                    light_family=light_family, reflection_source=f"the actual {source} on the {direction}",
                    reflection_placement=placement)
                scene["spatial_family"] = SPATIAL_FAMILIES[slot][h]
                scene["residential_cue_family"] = cue_family(scene["primary_cue"], "architectural cue")
                scene["depth_position"] = (("far right background" if h % 2 == 0 else "far left background") if slot == 0 else
                    ("far left edge" if "left" in depth else "far right edge") if slot == 1 else INTERIOR_DEPTH_POSITIONS[h])
                scene["light_source_position"] = ("left side outside the composition", "right-side distant reveal", "rear-left at a grazing angle")[l]
                scene["scene_signature"] = signature(scene)
                scene["scene_near_signature"] = signature(scene, near=True)
                result.append(scene)
    return tuple(result)


SCENES = tuple(candidates(i) for i in range(3))


def different(a, b):
    wall_distinct = a["wall_visual_group"] != b["wall_visual_group"] and a["wall_lightness"] != b["wall_lightness"]
    # Sand and similarly lit beige/taupe are not strong contrast simply because
    # their labels and lightness buckets differ.
    if {a["wall_visual_group"], b["wall_visual_group"]} == {"stone", "taupe"}:
        wall_distinct = False
    depth_a = "left" if "left" in a.get("depth_position", "") else "right" if "right" in a.get("depth_position", "") else "rear"
    depth_b = "left" if "left" in b.get("depth_position", "") else "right" if "right" in b.get("depth_position", "") else "rear"
    attributes = ("home_setting", "architecture_style", "wall_colour_family", "wall_lightness", "wall_finish",
                  "depth_family", "light_family", "light_direction")
    return (wall_distinct and a["home_setting"] != b["home_setting"] and a["wall_finish"] != b["wall_finish"]
            and (a["light_family"] != b["light_family"] or a["light_direction"] != b["light_direction"])
            and a.get("spatial_family") != b.get("spatial_family")
            and a["architecture_style"] != b["architecture_style"]
            and a.get("residential_cue_family") != b.get("residential_cue_family")
            and a["primary_cue"] != b["primary_cue"]
            and depth_a != depth_b
            and sum(a[k] != b[k] for k in attributes) >= 3
            and (a["architecture_style"] != b["architecture_style"] or a["light_family"] != b["light_family"]))


def _history_conflict(scene, old):
    if old.get("scene_signature") == scene["scene_signature"] or old.get("scene_near_signature") == scene["scene_near_signature"]:
        return True
    if old.get("scene_selection_version"):
        if not old.get("spatial_family") and old.get("depth_position"):
            return json.loads(signature(old, near=True))[:6] == json.loads(signature(scene, near=True))[:6]
        if not old.get("depth_position"):
            # Earlier resolved drafts stored the same five appearance dimensions,
            # without opening position. Reuse that evidence without rewriting it.
            return json.loads(signature(old, near=True))[:5] == json.loads(signature(scene, near=True))[:5]
        return signature(old, near=True) == scene["scene_near_signature"]
    # Use older saved appearance fields where present; they have no signature.
    wall = str(old.get("wall_colour_family", "")).lower()
    finish = str(old.get("wall_finish") or old.get("wall_material") or "").lower()
    lighting = str(old.get("lighting_direction") or old.get("lighting") or "").lower()
    groups = {"grey": ("grey", "slate", "graphite", "charcoal"), "ivory": ("ivory", "chalk", "white"),
              "stone": ("limestone", "sand", "stone"), "olive": ("olive", "eucalyptus"),
              "blue": ("navy", "blue"), "taupe": ("mushroom", "taupe"), "forest": ("forest",)}
    group = next((key for key, words in groups.items() if any(w in wall for w in words)), "")
    finish_matches = (scene["wall_finish"] in finish or
                      (scene["wall_finish"] in {"subtle limewash", "fine mineral plaster", "fine microcement", "textured plaster", "concrete"}
                       and any(w in finish for w in ("limewash", "plaster", "microcement", "concrete"))))
    source_matches = scene["depth_family"].split()[0] in lighting and "window" in lighting
    if group == scene["wall_visual_group"] and finish_matches and source_matches:
        return True
    return old.get("room_type") == scene["room_type"]


def select(seed, context, recent=(), selections=()):
    history = [r for r in list(recent)[:HISTORY_LIMIT] if isinstance(r, dict)]
    recency_history = list(history)
    product_key = context.get("scene_product_key")
    if product_key:
        # Same-product exclusions survive longest; broader history still reduces
        # repeated homes across products. Recency stays intact within each group.
        history.sort(key=lambda old: old.get("copy_product_key") != product_key)
    metadata = context.get("product_metadata") or {}
    # Verified/supplied palette and era guide ranking, never invent metadata from a sport.
    palette = " ".join(str(metadata.get(k, "")) for k in ("artwork_colours", "artwork_colors", "dominant_colours", "dominant_colors", "colour_palette")).casefold()
    heritage = context.get("product_era") == "historic" or context.get("artwork_mood") == "heritage"
    frame = str(context.get("frame_finish", "")).casefold()
    def slot_of(old):
        if isinstance(old.get("scene_slot"), int):
            return old["scene_slot"]
        route = str(old.get("route_key") or "")
        if route in ("premium_scarcity_right", "premium_scarcity_front", "premium_scarcity_left"):
            return ("premium_scarcity_right", "premium_scarcity_front", "premium_scarcity_left").index(route)
        camera = str(old.get("assigned_camera_angle") or old.get("camera_role") or "").upper()
        return next((i for i, name in enumerate(("RIGHT", "FRONT", "LEFT")) if camera.startswith(name)), None)
    # Keep actual recency across ALL products for role-level palette/layout ranking.
    # Same-product ordering above still governs bounded exact/near exclusions.
    role_history = [[old for old in recency_history if slot_of(old) == i] for i in range(3)]
    def rank(scene, slot):
        compatible = (heritage and any(w in scene["architecture_style"].lower() for w in ("heritage", "victorian", "edwardian", "georgian")))
        related = any(word in palette for word in scene["wall_colour"].split() if word in {"olive", "navy", "forest", "ivory", "sand", "taupe", "grey"})
        contrast = ("black" in frame and scene["wall_lightness"] == "light") or ("white" in frame and scene["wall_lightness"] == "dark")
        recent_role = role_history[slot]
        latest = recent_role[:1]
        palette_use = sum((HISTORY_LIMIT - i) for i, old in enumerate(recent_role)
                          if old.get("wall_visual_group") == scene["wall_visual_group"])
        layout_use = sum((HISTORY_LIMIT - i) for i, old in enumerate(recent_role)
                         if old.get("architecture_style") == scene["architecture_style"])
        return (any(old.get("wall_visual_group") == scene["wall_visual_group"] for old in latest),
                any(old.get("architecture_style") == scene["architecture_style"] for old in latest),
                any(old.get("depth_position") == scene["depth_position"] for old in latest),
                any(old.get("light_family") == scene["light_family"] for old in latest),
                palette_use, layout_use,
                int.from_bytes(_rank(seed, scene["scene_signature"]), "big") // (1 + compatible + related + contrast))
    pools = []
    for i, slot in enumerate(SCENES):
        saved = selections[i] if i < len(selections) and isinstance(selections[i], dict) else {}
        pool = []
        for candidate in slot:
            scene = {**candidate, **{k: v for k, v in saved.items() if k in SCENE_FIELDS and v not in (None, "")}}
            if saved.get("wall_colour") and not saved.get("wall_colour_family"):
                wall = next((w for w in WALLS if w[0] == saved["wall_colour"]), None)
                scene.update(wall_colour_family=wall[1] if wall else saved["wall_colour"],
                             wall_lightness=wall[2] if wall else "explicit unclassified colour",
                             wall_visual_group=wall[3] if wall else "explicit colour override")
            if saved.get("wall_finish"):
                scene["wall_material"] = saved["wall_finish"]
            if saved.get("primary_cue") and not saved.get("residential_cue_family"):
                scene["residential_cue_family"] = cue_family(saved["primary_cue"], scene["residential_cue_family"])
            scene["scene_signature"] = signature(scene)
            scene["scene_near_signature"] = signature(scene, near=True)
            pool.append(scene)
        pools.append(sorted(pool, key=lambda scene: rank(scene, i)))
    # Bounded search: first fit with backtracking over fixed finite curated pools.
    # Relax only oldest scene exclusions; never relax same-pack differentiation.
    for keep in range(len(history), -1, -1):
        unseen = [[s for s in pool if not any(_history_conflict(s, old) for old in history[:keep])] for pool in pools]
        # Coordinate rotation as a pack, so a greedy first scene cannot force a
        # later role back into its previous palette. Fall back finitely for
        # constrained explicit selections; exact/near exclusions remain stronger.
        for rotation_axes in (2, 1, 0):
            eligible = [[s for s in pool if not any(rank(s, i)[:rotation_axes])]
                        for i, pool in enumerate(unseen)]
            for a in eligible[0]:
                for b in eligible[1]:
                    if different(a, b):
                        c = next((c for c in eligible[2] if different(a, c) and different(b, c)
                                  and any(s["wall_finish"] in {"matte painted brick", "natural stone", "aged timber"} for s in (a, b, c))), None)
                        if c:
                            return [dict(s, history_exclusions_relaxed=len(history) - keep) for s in (a, b, c)]
    raise ValueError("Curated scene library needs three compatible differentiated homes.")


# Detail choices are independent of the home/layout draw and saved with the scene.
# Families prevent similar accessories in sibling images.
COLLECTOR_DETAILS = (
    (
        ("dark timber console with a leather catchall resting on it", "console"),
        ("slim leather bench", "seating"),
        ("small stack of sports books resting on a console", "books"),
        ("discreet brass lamp resting on a narrow side table", "lamp"),
        ("aged timber ledge with one book resting on it", "books"),
        ("dark built-in cabinet", "cabinet"),
        ("distant leather study chair", "seating"),
        ("clean architectural setting with no accessory", "none"),
    ),
    (
        ("leather armchair edge", "seating"),
        ("dark media cabinet", "cabinet"),
        ("timber study-desk corner", "desk"),
        ("recessed sports-book shelf", "books"),
        ("side table with one whisky tumbler resting on it", "drinks"),
        ("record cabinet", "music"),
        ("understated home-bar cabinetry", "cabinet"),
        ("dark fabric sofa edge", "seating"),
    ),
    (
        ("pool-table corner", "games"),
        ("distant dartboard mounted on a background wall", "games"),
        ("whisky tumbler resting on a side table", "drinks"),
        ("small decanter-and-glasses arrangement resting on a side table", "drinks"),
        ("leather recliner edge", "seating"),
        ("restrained drinks cabinet", "cabinet"),
        ("turntable resting on timber cabinetry", "music"),
        ("peripheral cue rack secured to a background wall", "games"),
        ("chessboard corner resting on a table", "games"),
        ("leather sofa edge with a wool throw", "seating"),
    ),
)
COLLECTOR_DETAIL_RULES = (
    " Use only the resolved collector-home detail or small coherent arrangement, replacing the previous peripheral cue, "
    "never adding to it. Keep it small, secondary and partially visible at the perimeter or softly in the background; "
    "Image 2 confines it to the existing tiny residential glimpse. Never widen the shot, shrink the edition or clutter "
    "the room to fit it; the edition remains the clear focal point at realistic physical scale. "
    "Use believable construction and placement on a real supporting surface where applicable, realistic proportions, "
    "materials, perspective, lighting and contact shadows. No decorative plants, flowers or vases; incidental natural "
    "outdoor greenery through a window is allowed. No warped, floating, duplicated or fake-looking objects, invented "
    "memorabilia, prominent alcohol branding, neon signs or competing wall displays."
)


def resolve_collector_details(chosen, seed, recent=(), selections=()):
    """Resolve once before export; existing saved peripheral cues are never replaced."""
    history = [r for r in list(recent)[:HISTORY_LIMIT] if isinstance(r, dict)]
    used = {s.get("collector_detail_family") for s in selections if isinstance(s, dict)}
    for slot, scene in enumerate(chosen):
        saved = selections[slot] if slot < len(selections) and isinstance(selections[slot], dict) else {}
        if saved.get("primary_cue") or saved.get("collector_detail"):
            continue
        options = [(text, family) for text, family in COLLECTOR_DETAILS[slot] if family not in used]
        def rank(option):
            text, _ = option
            uses = [i for i, old in enumerate(history) if old.get("collector_detail") == text]
            return (bool(uses), -min(uses) if uses else 0, len(uses), _rank(seed, text))
        detail, family = min(options, key=rank)
        used.add(family)
        # Retain the architectural opening/volume, replacing embedded old furnishings.
        depth = scene["architectural_cue"]
        for old, new in (
            ("a distant furniture silhouette", "a tiny residential glimpse"),
            ("a partial distant furniture silhouette", "a tiny residential glimpse"),
            ("a distant seating silhouette", "a tiny residential glimpse"),
            ("a softly lit recessed window seat", "a softly lit residential glimpse"),
            ("a softly lit recessed bench edge", "a softly lit residential glimpse"),
            ("bay-window seating recess", "bay-window recess"),
            ("around a shallow reading bench", "around a shallow alcove"),
            ("low residential seating corner", "low residential corner"),
        ):
            depth = depth.replace(old, new)
        placement = ("small and peripheral at the outer edge or distant passage",
                     "only inside the existing tiny residential glimpse",
                     "only a subtle peripheral or background portion")[slot]
        scene.update(collector_detail=detail, collector_detail_family=family,
                     primary_cue=f"{detail}; {placement}", furniture_cue=detail,
                     residential_cue_family=family, architectural_cue=depth)
