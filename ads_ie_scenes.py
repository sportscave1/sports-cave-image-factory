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
    "depth_position", "light_source_position",
)

# Colour and construction are authored together, not independently randomised.
WALLS = (
    ("warm ivory", "warm ivory and chalk", "light", "ivory", "smooth matte paint"),
    ("chalk", "warm ivory and chalk", "light", "ivory", "restrained painted wall panelling"),
    ("pale limestone", "pale limestone and sand", "light", "stone", "honed limestone"),
    ("pale sand", "pale limestone and sand", "light", "stone", "fine microcement"),
    ("mushroom", "mushroom and smoked taupe", "mid", "taupe", "fine mineral plaster"),
    ("smoked taupe", "mushroom and smoked taupe", "mid", "taupe", "smooth matte paint"),
    ("mineral grey", "mineral grey and slate", "mid", "grey", "fine microcement"),
    ("slate", "mineral grey and slate", "mid", "grey", "smooth matte paint"),
    ("graphite", "graphite and charcoal", "dark", "grey", "restrained painted wall panelling"),
    ("charcoal", "graphite and charcoal", "dark", "grey", "smooth matte paint"),
    ("muted olive", "muted olive and eucalyptus", "mid", "olive", "subtle limewash"),
    ("pale eucalyptus", "muted olive and eucalyptus", "light", "olive", "smooth matte paint"),
    ("desaturated navy", "desaturated navy and blue-grey", "dark", "blue", "restrained painted wall panelling"),
    ("blue-grey", "desaturated navy and blue-grey", "mid", "blue", "fine mineral plaster"),
    ("deep muted forest green", "deep muted forest green", "dark", "forest", "smooth matte paint"),
    ("deep muted forest green", "deep muted forest green", "dark", "forest", "subtle limewash"),
    ("warm ivory", "warm ivory and chalk", "light", "ivory", "subtle limewash"),
    ("pale sand", "pale limestone and sand", "light", "stone", "smooth matte paint"),
    ("mushroom", "mushroom and smoked taupe", "mid", "taupe", "restrained painted wall panelling"),
    ("pale limestone", "pale limestone and sand", "light", "stone", "fine mineral plaster"),
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
        ("Refined apartment living corner", "quiet contemporary apartment", "one small doorway glimpse into a softly focused room at the far left", "none; architecture is the single peripheral cue", (0, 3, 5, 7, 9, 13, 14, 17), "tall window"),
        ("Contemporary courtyard home", "single-storey courtyard house", "one shallow corridor return at the far right", "none; architecture is the single peripheral cue", (2, 3, 6, 10, 14, 17), "courtyard window"),
        ("Heritage collector hallway", "quiet heritage townhouse interior", "one doorway sliver at the far left into a distant residential passage", "none; architecture is the single peripheral cue", (0, 1, 4, 8, 12, 18), "side window"),
        ("Bay-window sitting room", "restrained bay-window home", "one window recess with a partial distant furniture silhouette at the far right", "none beyond the silhouette inside the single window recess", (0, 4, 11, 12, 15, 16), "bay window"),
        ("Quiet home study", "garden-facing reading home", "one narrow doorway into a softly focused study at the far right", "none; no desk in the photographic foreground", (0, 4, 5, 10, 14, 19), "garden window"),
        ("Architectural entry alcove", "oak-accented architectural home", "one shallow oak-lined corridor return at the far left", "none; architecture is the single peripheral cue", (2, 3, 5, 10, 15, 17), "clerestory window"),
        ("Split-level lounge", "mid-century split-level home", "one distant room glimpse through an offset opening at the far right", "none; architecture is the single peripheral cue", (2, 6, 7, 9, 10, 13, 17), "high side window"),
        ("Restrained media lounge", "contemporary private residential retreat", "one doorway glimpse into a softly focused room at the far left", "none; architecture is the single peripheral cue", (0, 5, 6, 9, 11, 14, 16), "corner window"),
    ),
    (
        ("Bay-window sitting room", "refined Victorian sitting room", "off-centre bay-window seating recess", "one oatmeal wool banquette edge at the outer perimeter", (0, 1, 4, 11, 12, 15), "bay window"),
        ("Split-level lounge", "mid-century split-level lounge", "sunken living alcove with a distant floor-level change and high window", "one ink-blue fabric settee edge at the far side", (2, 3, 6, 7, 10, 14), "high side window"),
        ("Quiet home study", "heritage library retreat", "off-centre reading alcove with a deep side-window reveal", "one painted reading-bench edge deep in the alcove", (0, 1, 4, 8, 12, 18), "garden window"),
        ("Restrained media lounge", "quiet contemporary media retreat", "low residential seating alcove with a deep corner-window recess", "one moss wool banquette edge at the far side", (0, 5, 6, 9, 11, 15, 16), "corner window"),
        ("Contemporary courtyard home", "refined contemporary courtyard sitting room", "off-centre living recess looking toward a courtyard opening", "one cream woven settee edge near the distant opening", (2, 3, 6, 10, 14, 17), "courtyard window"),
        ("Refined apartment living corner", "high-ceiling apartment living corner", "double-height living alcove with an off-centre tall-window reveal", "one pale grey linen seating edge at the outer perimeter", (0, 5, 7, 9, 13, 16, 19), "tall window"),
        ("Architectural entry alcove", "architectural home adjoining-room retreat", "deep oak-lined adjoining sitting-room alcove", "one quiet woven bench edge deep in the recess", (2, 3, 5, 10, 15, 17), "clerestory window"),
        ("Quiet home study", "contemporary garden library lounge", "off-centre reading recess overlooking a softly focused garden", "one pale oak reading-bench edge at the outer perimeter", (0, 4, 5, 10, 14, 19), "side window"),
    ),
)

LIGHTS = (
    ("left", "soft directional morning daylight", "morning-side", "soft upper-left peripheral window shape"),
    ("right", "broad diffused overcast daylight", "overcast-side", "broad faint upper-right peripheral tonal sheen"),
    ("left", "soft raking late-afternoon daylight", "afternoon-raking", "restrained lower-left peripheral window sheen"),
)


def _rank(seed, value):
    return hashlib.sha256(f"{seed}|{value}".encode("utf-8")).digest()


def signature(scene, *, near=False):
    # Deliberately excludes token, adjectives, IDs, camera role and copy.
    keys = (("wall_visual_group", "wall_lightness", "wall_finish", "depth_family", "light_family", "depth_position") if near else
            ("home_setting", "architecture_style", "wall_colour", "wall_lightness", "wall_finish",
             "architectural_cue", "depth_position", "furniture_cue", "light_source", "light_source_position", "light_direction", "light_softness"))
    values = [scene.get(k, "") for k in keys]
    if near:
        # Grey/graphite/charcoal and plaster-like treatments can look almost alike.
        values[1] = "any-grey-value" if values[0] == "grey" else values[1]
        if values[2] in {"subtle limewash", "fine mineral plaster", "fine microcement"}:
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
                scene = dict(scene_selection_version=VERSION, scene_id=f"{slot}:{h}:{w}:{l}",
                    home_setting=setting, architecture_style=architecture,
                    room_type=(f"{architecture} collector hallway" if slot == 0 else
                               f"minimal {architecture} product wall" if slot == 1 else architecture),
                    wall_colour=colour, wall_colour_family=family, wall_lightness=lightness, wall_visual_group=group,
                    wall_material=finish, wall_finish=finish, architectural_cue=depth,
                    depth_family=source, primary_cue=depth if slot == 1 else furniture, furniture_cue=furniture,
                    lighting=light, light_source=source, light_direction=direction, light_softness=softness,
                    light_family=light_family, reflection_source=f"the actual {source} on the {direction}",
                    reflection_placement=placement)
                scene["depth_position"] = (("far right background" if h % 2 == 0 else "far left background") if slot == 0 else
                    ("far left edge" if "left" in depth else "far right edge") if slot == 1 else "deep off-centre rear recess")
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
            and a["light_family"] != b["light_family"]
            and depth_a != depth_b
            and sum(a[k] != b[k] for k in attributes) >= 3
            and (a["architecture_style"] != b["architecture_style"] or a["light_family"] != b["light_family"]))


def _history_conflict(scene, old):
    if old.get("scene_signature") == scene["scene_signature"] or old.get("scene_near_signature") == scene["scene_near_signature"]:
        return True
    if old.get("scene_selection_version"):
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
                      (scene["wall_finish"] in {"subtle limewash", "fine mineral plaster", "fine microcement"}
                       and any(w in finish for w in ("limewash", "plaster", "microcement"))))
    source_matches = scene["depth_family"].split()[0] in lighting and "window" in lighting
    if group == scene["wall_visual_group"] and finish_matches and source_matches:
        return True
    return old.get("room_type") == scene["room_type"]


def select(seed, context, recent=(), selections=()):
    history = [r for r in list(recent)[:HISTORY_LIMIT] if isinstance(r, dict)]
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
    def rank(scene):
        compatible = (heritage and any(w in scene["architecture_style"].lower() for w in ("heritage", "victorian", "edwardian", "georgian")))
        related = any(word in palette for word in scene["wall_colour"].split() if word in {"olive", "navy", "forest", "ivory", "sand", "taupe", "grey"})
        contrast = ("black" in frame and scene["wall_lightness"] == "light") or ("white" in frame and scene["wall_lightness"] == "dark")
        return int.from_bytes(_rank(seed, scene["scene_signature"]), "big") // (1 + compatible + related + contrast)
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
            scene["scene_signature"] = signature(scene)
            scene["scene_near_signature"] = signature(scene, near=True)
            pool.append(scene)
        pools.append(sorted(pool, key=rank))
    # Bounded search: first fit with backtracking over fixed finite curated pools.
    # Relax only oldest scene exclusions; never relax same-pack differentiation.
    for keep in range(len(history), -1, -1):
        eligible = [[s for s in pool if not any(_history_conflict(s, old) for old in history[:keep])] for pool in pools]
        for a in eligible[0]:
            for b in eligible[1]:
                if different(a, b):
                    c = next((c for c in eligible[2] if different(a, c) and different(b, c)
                              and any(s["wall_finish"] in {"smooth matte paint", "restrained painted wall panelling", "honed limestone"} for s in (a, b, c))), None)
                    if c:
                        return [dict(s, history_exclusions_relaxed=len(history) - keep) for s in (a, b, c)]
    raise ValueError("Curated scene library needs three compatible differentiated homes.")
