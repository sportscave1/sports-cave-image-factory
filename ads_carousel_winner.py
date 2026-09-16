"""Standard Carousel winner copy and deterministic photographic scene selection.

No storage, API calls or independent product/edition lookup. Creative Refresh
continues using its existing contracts in ads_page.
"""
import hashlib
import json
import random
import re


# family: display label, architectural character, principal furniture, similarity group
ROOMS = {
    "sports_cave": ("Premium Man Cave / Sports Cave", "adult fan sanctuary with recessed media cabinetry", "low media cabinet and partial dark leather seat", "cave"),
    "executive_office": ("Executive Home Office", "mature home workspace with a deep window reveal", "executive desk and fitted cabinetry", "workspace"),
    "home_bar": ("Premium Residential Home Bar", "residential bar alcove with quiet joinery", "restrained bar counter and tasteful stools", "bar"),
    "games_room": ("Premium Games / Pool Table Room", "spacious private recreation room with modest ceiling beams", "partial pool table edge", "games"),
    "collector_lounge": ("Collector Lounge", "quiet private sitting room with a recessed display wall", "collector cabinet and partial reading chair", "sitting"),
    "media_room": ("Media Room", "home entertainment room with acoustic wall returns", "media seating with any television outside the focal zone and unreadable", "viewing"),
    "heritage_study": ("Heritage Study / Library", "warm timber library with restrained side bookshelves", "library writing table", "library"),
    "modern_study": ("Modern Study", "clean graphite and walnut architectural workspace", "slim contemporary desk", "workspace"),
    "basement_lounge": ("Finished Basement Sports Lounge", "high-end finished basement with believable lower ceiling", "low sectional seating", "basement"),
    "bedroom": ("Premium Adult Fan Bedroom", "quiet adult bedroom with a partial headboard zone", "restrained upholstered bed edge", "bedroom"),
    "home_gym": ("Premium Home Gym", "private residential training space with quiet rubber flooring", "one partial unbranded exercise bench", "gym"),
    "garage_lounge": ("Premium Garage Lounge", "finished residential garage with clean architectural door reveals", "low garage lounge bench", "garage"),
    "workshop_office": ("Workshop / Garage Office", "refined practical workspace with metal and timber architecture", "dark workshop cabinetry and clear worktop", "garage"),
    "clubroom": ("Private Clubhouse Lounge", "heritage private clubroom with quiet timber wall returns", "club lounge banquette", "club"),
    "home_theater": ("Premium Home Theater", "residential cinema with restrained acoustic architecture", "partial cinema seating", "cinema"),
    "entry_gallery": ("Residential Entry / Hall Gallery", "narrow residential entry with a quiet side passage", "slender entry console", "entry"),
    "loft_den": ("Residential Loft / Industrial Den", "believable converted loft with restrained concrete detailing", "low industrial timber bench", "loft"),
    "penthouse": ("Modern Penthouse Lounge", "restrained contemporary residential architecture", "partial low modern sofa", "sitting"),
    "pavilion": ("Enclosed Pavilion / Veranda Clubroom", "heritage enclosed private pavilion with side glazing", "timber pavilion bench", "pavilion"),
    "locker_room": ("Locker-Inspired Private Sports Room", "private collector room with premium locker-style cabinetry", "plain locker cabinetry and seating bench", "locker"),
}
SPORT_ROOMS = {
    "cricket": ("pavilion", "clubroom", "heritage_study"),
    "nfl": ("locker_room", "basement_lounge"),
    "baseball": ("heritage_study", "clubroom", "collector_lounge"),
    "nba": ("locker_room", "home_gym", "loft_den"),
    "ice hockey": ("locker_room", "clubroom"),
    "motorsport": ("garage_lounge", "workshop_office"),
    "horse racing": ("pavilion", "clubroom", "heritage_study"),
    "rugby union": ("clubroom", "home_bar"),
    "rugby league": ("clubroom", "home_bar"),
    "football": ("clubroom", "collector_lounge"),
    "golf": ("pavilion", "heritage_study", "executive_office"),
    "tennis": ("clubroom", "executive_office"),
    "combat": ("home_gym", "loft_den"),
    "australian rules": ("clubroom", "pavilion"),
}
SPECIALIST_ROOMS = {"garage_lounge", "workshop_office", "clubroom", "pavilion", "locker_room", "home_gym"}
LIGHT_WALLS = ("warm stone mineral plaster", "soft taupe plaster", "warm greige render",
               "warm off-white plaster", "soft concrete grey", "clean cream gallery wall",
               "soft sand-coloured mineral finish")
DARK_WALLS = ("charcoal mineral plaster", "graphite limewash", "muted heritage green",
              "dark olive charcoal", "muted bronze brown", "deep navy-grey",
              "restrained clay/tobacco", "walnut architectural wall section")
CAMERAS = ("straight-on with 1° natural offset", "slight left 6°", "slight right 6°",
           "left three-quarter 9°", "right three-quarter 9°",
           "slightly above centre with 4° downward view", "slightly below centre with 3° upward view")
LIGHTS = (
    ("soft morning window light from camera-left", "morning"),
    ("clean midday side light from camera-right", "midday"),
    ("quiet afternoon side daylight", "afternoon"),
    ("soft overcast daylight through a side window", "overcast midday"),
    ("warm early-evening practical light with restrained ambient fill", "early evening"),
    ("restrained architectural picture light with soft ambient fill", "evening"),
    ("side-window daylight with low practical fill", "late afternoon"),
    ("dim residential ambient light with readable artwork illumination", "evening"),
    ("warm heritage interior practical light", "dusk"),
    ("cool-neutral window daylight", "late morning"),
)


def _rng(*parts):
    seed = hashlib.sha256(json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str).encode()).digest()
    return random.Random(int.from_bytes(seed[:8], "big"))


def resolve_room_set(*, product_name, sport, market, variation_token="", metadata=None, campaign_context=None):
    metadata = metadata or {}
    visual_context = {key: metadata.get(key) for key in (
        "artwork_mood", "era", "artwork_palette", "palette", "artwork_brightness", "frame_colour", "collections")}
    seed = (product_name, sport, market, variation_token or "standard", visual_context, campaign_context)
    rng = _rng(*seed)
    hints = list(SPORT_ROOMS.get(sport, ()))
    specialist = rng.choice(hints) if hints else None
    selected = {4: "sports_cave"}
    specialist_slot = rng.choice((2, 3, 5)) if specialist else None
    if specialist:
        selected[specialist_slot] = specialist
    for index in (2, 3, 5):
        if index in selected:
            continue
        used_groups = {ROOMS[room][3] for room in selected.values()}
        lounge_groups = {"sitting", "viewing", "basement", "cinema"}
        candidates = [room for room in ROOMS if room not in selected.values()
                      and room not in SPECIALIST_ROOMS and ROOMS[room][3] not in used_groups
                      and not (used_groups & lounge_groups and ROOMS[room][3] in lounge_groups)]
        # Historic visual cues bias room suitability; they never establish copy claims.
        historic = any(word in f"{product_name} {visual_context}".casefold() for word in ("heritage", "historic", "legacy", "vintage"))
        weights = [3 if historic and room == "heritage_study" else 0.3 if room == "penthouse" else 1 for room in candidates]
        selected[index] = rng.choices(candidates, weights=weights, k=1)[0]
    cameras = rng.sample(CAMERAS, 4)
    lighting = rng.sample(LIGHTS, 4)
    # Two light and two dark walls; the mandatory cave is always in the dark pair.
    other_dark = rng.choice((2, 3, 5))
    light_pool = rng.sample(LIGHT_WALLS, 2)
    dark_pool = rng.sample(DARK_WALLS, 2)
    hero_rng = _rng(*seed, 1)
    hero_walls = list(LIGHT_WALLS + DARK_WALLS)
    if metadata.get("artwork_brightness") == "dark":
        hero_walls = list(LIGHT_WALLS)
    hero = dict(card=1, room_family="close_up_wall_hero", room="Premium close-up wall hero",
                wall_family=hero_rng.choice(hero_walls), camera_family=hero_rng.choice(("slight left 7°", "slight right 7°")),
                lighting_family="soft controlled side daylight", time_of_day="late morning",
                furniture_family="none", architecture="narrow premium wall context only",
                artwork_placement="large centred complete frame", sport_specific_setting="none")
    placements = rng.sample(("slightly left of centre on the main wall", "slightly right of centre on the main wall", "centred on a dedicated wall bay", "above the low furniture with negative space to the left", "on the main wall with negative space to the right"), 4)
    scenes = [hero]
    for offset, index in enumerate((2, 3, 4, 5)):
        card_rng = _rng(*seed, index)
        family = selected[index]
        label, architecture, furniture, _ = ROOMS[family]
        if index == 4:
            architecture = card_rng.choice((architecture, "private split-level fan den with low media joinery", "intimate sports sanctuary with a recessed seating bay"))
            furniture = card_rng.choice((furniture, "dark leather chair crop beside timber media drawers", "partial leather sofa and built-in media storage"))
        light, time = lighting[offset]
        scenes.append(dict(card=index, room_family=family, room=label,
                           wall_family=(dark_pool if index in (4, other_dark) else light_pool).pop(),
                           camera_family=cameras[offset], lighting_family=light, time_of_day=time,
                           furniture_family=furniture, architecture=architecture,
                           artwork_placement=placements[offset],
                           sport_specific_setting=f"{sport} private fan atmosphere" if index == specialist_slot else "none"))
    return tuple(scenes)


def scene_block(scene, token):
    return f"""RESOLVED CAROUSEL SCENE — FOLLOW ONE COHERENT SCENE
CREATIVE_VARIATION_TOKEN: {token or 'standard'} (creative cue only; never visible ad text)
Room: {scene['room']}
Architecture: {scene['architecture']}
Wall: {scene['wall_family']}
Camera: {scene['camera_family']}
Light: {scene['lighting_family']}
Time of day: {scene['time_of_day']}
Main furniture: {scene['furniture_family']}
Artwork placement: {scene['artwork_placement']}
Sport-specific setting: {scene['sport_specific_setting']}
Inspect the attached product's actual palette, brightness, mood, era and frame colour, plus selected market and campaign context. Preserve frame separation and artwork readability. If a suitability correction is essential, resolve one compatible wall/light treatment before printing the final prompt; retain the assigned room family and cross-card distinctions. Never print a menu of alternatives.
Keep this room believable as a different property from the other cards: changing only wall colour or angle is insufficient. Use the resolved camera family and preserve the whole frame as one rigid object. Perspective must never distort the printed artwork.
No invented vehicles, athletes, team marks, club logos, player names, jerseys, trophies, sports equipment displays, neon, fake memorabilia or official stadium branding. Any sport association comes from architecture and materials, never unsupported product facts. No commercial pub styling or cheap novelty decor. No extreme golden-hour beams, haze, fog, glowing frame edges, conflicting shadows or orange AI interiors.
Keep correct source-frame mitres, real physical depth, realistic mounting, a contact shadow, softer secondary wall shadow and ambient occlusion. Require clear acrylic/glass, restrained reflections, real highlight falloff and no glare hiding artwork.
No on-image Meta headline, description, Primary Text, prices, discount stickers, fake buttons, UI, slogans or watermarks.
Visual fingerprint (metadata only): {json.dumps(scene, ensure_ascii=False, sort_keys=True)}"""


CARD_FIVE = """CARD 5 PRODUCT-PROMINENT LIFESTYLE SCARCITY — MANDATORY:
Use the fourth distinct premium lifestyle room after Cards 2–4, with a stronger medium-close collector composition. Target approximately 45-65% of the useful square composition; never zoom out into a distant wide room. Keep the complete outer frame visible. Convey collectibility through the premium setting, frame prominence and restrained lighting.
Keep a genuine edition plate/badge readable when it exists in the immutable product; use composition and light only. Never alter or magnify printed pixels artificially, invent an edition number or require an edition-detail asset when none is present. No magnifier prop or added scarcity text. Scarcity belongs in the verified Meta copy. Preserve all shared artwork, frame, glass, mounting, shadow and realism rules."""


def preferred_copy(product_name, metadata, edition_limit, limited_verified, numbered_verified):
    """Return only short supported preferred fields; the existing model writes the full copy."""
    metadata = metadata or {}
    names = metadata.get("athlete_names") or []
    if isinstance(names, str):
        names = [names]
    title = re.sub(r"\s*(?:[-–—|:]\s*)?(?:Limited Edition Wall Art|Framed Art|Wall Art|Sports Art)\s*$", "", product_name, flags=re.I).strip()
    candidates = ([" vs ".join(names)] if len(names) > 1 else names) + [title]
    identity = next((text for text in candidates if text and len(text) <= 17 and not any(c in text for c in ',.')), None)
    scarcity = f"Only {edition_limit} Made" if edition_limit else ""
    if not scarcity or len(scarcity) > 17:
        scarcity = "Limited Release" if limited_verified else ""
    return {"card_1_headline": identity, "card_1_description": "Limited Edition" if limited_verified else None,
            "card_4_headline": "For The Cave", "card_5_headline": scarcity or None,
            "card_5_description": "Numbered Run" if numbered_verified else "Collector Run" if limited_verified else None}


def winner_story(category):
    return f"""CONNECTED STORY STRUCTURE — CAROUSEL WINNER STANDARD
Create exactly five cards. Preserve the current template's machine-facing role labels and positions: Product Identity; Moment / Legacy; Emotional Hook; Fan Ownership; Scarcity (including existing Motorsport aliases).
Card 1 — Product Identity: strongest recognisable verified identity, preferred order athlete/person, paired/rivalry identity, artwork title/defining phrase, car/horse/team, event/moment. Remove generic Wall Art, Framed Art, Limited Edition Wall Art and Sports Art suffixes. Never blindly copy an overlong Shopify title or truncate words. Resolve a truthful shortened identity within 17 characters. Prefer description exactly Limited Edition only when verified; otherwise use an existing fact-safe alternative.
Card 2 — Moment / Legacy: FAN IDENTITY / MEMORY. Prefer a supported team, athlete, driver, club or sport plus Fans; pair with a relevant short response such as Remember This, Still Remember, You Know This, That Feeling, Never Forgotten, Still Matters or Remember When. Never infer a team from appearance. Do not force historical/past-tense memory for current subjects without verified history; use a safe present-day fan connection.
Card 3 — Emotional Hook: DEFINING PRODUCT HOOK. Use a second verified product anchor, distinct from Card 1: artwork title, nickname, moment, circuit, event, year, venue, rivalry, achievement, car, mentality, theme or era. Headline and complementary description must be specific enough not to transfer unchanged to unrelated artwork. Never invent a second fact to satisfy specificity.
Card 4 — Fan Ownership: MAN CAVE OWNERSHIP. Default headline exactly For The Cave. Description uses a verified product-specific place, era, phrase, emotional anchor or subject cue; if none fits, choose a premium ownership line not repeated elsewhere. Image MUST use Premium Man Cave / Sports Cave.
Card 5 — Scarcity: prefer Only {{verified edition limit}} Made when Python len() is <=17. If it cannot fit, use Limited Release only when limited status is verified. Prefer Numbered Run only when numbering is explicitly verified. Otherwise use a supported Limited Run, Collector Run or Limited Release without duplicating Card 1's description. Without scarcity evidence use a fact-safe collector close, never invent a quantity, numbering, no second run, no reprint or never-again claim.
PRODUCT SPECIFICITY TEST: select different supported identity anchors across Cards 1–4. Prefer the winner sequence WHO/WHAT → FAN RECOGNITION → DEFINING HOOK → CAVE OWNERSHIP → AUTHENTIC SCARCITY. Product facts win when supplied details are sparse. Selected sport: {category}.
Keep the existing five Primary Text variants, CTA Claim Your Edition, factual wording gates, localisation and output structure. Do not put Meta copy inside the image."""


WINNER_QUALITY = """HIGH-CONVERSION CAROUSEL QUALITY — WINNER STANDARD
Select the strongest connected five-card sequence from verified product data. No duplicate headlines or descriptions, no commas or full stops, no truncated words or awkward abbreviations. Count every headline and description using Python len(): maximum 17 characters including spaces. Rewrite failures before returning the campaign.
Prefer short recognisable identity, supported fan recognition, a different defining product hook, For The Cave ownership, and verified scarcity. Limited Edition is the approved Card 1 description when verified; it is not banned generic filler. For The Cave is the approved standard Card 4 headline. Reusing an identity in a fan phrase is allowed when useful; do not duplicate whole lines or weaken clarity to enforce arbitrary word bans.
Match each headline, description, creative direction and image prompt. Card 1 remains the close-up product hero; Cards 2–5 use four different fan environments, Card 4 always the Sports Cave. Card 5 is lifestyle scarcity, not a detail-prop photograph.
Never invent athlete/team identities, achievements, dates, quantities, numbering, signatures, licensing, manufacturing or product features. Keep current country language, sport terminology, CTA, URLs, UTM parameters and five Primary Text variants. Silently reject weak or invalid candidates and output only the finished campaign."""
