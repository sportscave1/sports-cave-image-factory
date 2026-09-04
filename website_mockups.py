"""Local audience briefs for the existing Mockups upload and product-slot pipeline."""

from dataclasses import dataclass
import re
from uuid import uuid4

import design_studio_styles
import image_factory
from sports_cave_prompt_blocks import build_sports_cave_image_realism_rules


WORKFLOW_VERSION = 2
SNAPSHOT_KEY = "website_mockup_brief"
SLOT_FILENAMES = tuple(spec["prompt_filename"] for spec in image_factory.PRODUCT_IMAGE_SLOT_SPECS if spec.get("prompt_filename"))

ERA_GUIDANCE = {
    "Pre-1950": "Restrained heritage materials, warm aged timber and traditional craftsmanship, maintained as a premium home today.",
    "1950-1969": "Warm timber, tailored classic furniture and restrained mid-century collector atmosphere in a present-day home.",
    "1970-1979": "Richer timber, warm earth-influenced upholstery and a few restrained retro material cues.",
    "1980-1989": "Deeper sporting-club colours, classic leather and timber combinations, with subtle period familiarity.",
    "1990-1999": "Warm 1990s fan nostalgia, familiar traditional sports-room materials and understated collector warmth in a present-day premium home.",
    "2000-2009": "Transitional contemporary interiors, cleaner surfaces and familiar sports-bar or home styling.",
    "2010-2019": "Contemporary architecture, clean furniture lines and natural modern materials with lived-in warmth.",
    "2020-Present": "Current architectural detailing, tactile contemporary materials and quiet integrated lighting.",
    "Timeless / Multiple Eras": "Balance classic craftsmanship with contemporary comfort; avoid tying the home to a single decade.",
    "Not Sure": "Use timeless premium materials and natural warmth without assuming an unverified historical era.",
}
ERA_OPTIONS = tuple(ERA_GUIDANCE)


@dataclass(frozen=True)
class RoomPreset:
    key: str
    label: str
    family: str
    brief: str
    source: str = ""
    heritage: bool = False

    @property
    def variant(self):
        return image_factory.LIFESTYLE_IMAGE_VARIANTS.get(self.source) or f"{image_factory.slugify(self.label)}-lifestyle"


# Existing room identities retain their existing filename variants. Near-duplicate
# bar/entry/pool-table/loft names are aliases, not extra recommendation candidates.
ROOMS = (
    RoomPreset("man-cave", "Man Cave", "entertainment", "A quiet personal fan retreat with one leather chair, restrained shelving and a product-forward wall; no pool table is required.", "01-man-cave-prompt.txt", True),
    RoomPreset("pool-table", "Man Cave with Pool Table", "entertainment", "A believable pool table beside, never in front of, the artwork; accurate rails, pockets, legs and cue clearances. Use pendant light and a slight three-quarter room view.", "16-man-cave-with-pool-table-prompt.txt", True),
    RoomPreset("premium-man-cave", "Premium Man Cave", "entertainment", "A tailored conversation lounge with built-in low cabinetry, wool upholstery and quiet acoustic wall detailing; a compact feature wall keeps the product dominant."),
    RoomPreset("sports-bar", "Premium Home Sports Bar", "bar", "A private home bar with stone benchtop, timber shelving and a few unbranded glasses; frame above or beside the counter, never hidden by bottles.", "07-home-sports-bar-prompt.txt"),
    RoomPreset("games-room", "Games Room", "entertainment", "A refined tabletop games room with a solid timber games table, two chairs and enclosed game storage. No arcade graphics or novelty decoration."),
    RoomPreset("entertainment-room", "Entertainment Room", "entertainment", "An open social room with compact modular seating and a low sideboard; use a dedicated uninterrupted artwork wall away from door swings."),
    RoomPreset("media-room", "Media Room / Home Theatre", "entertainment", "A domestic media room with fabric acoustic panels, a low sofa and recessed dimmable practical lights. Any screen is switched off and secondary; artwork remains brightly readable."),
    RoomPreset("basement-lounge", "Basement Sports Lounge", "entertainment", "A realistic finished basement with modest ceiling height, a high lightwell, warm layered lamps and low seating. No impossible tall windows or cavernous scale.", heritage=True),
    RoomPreset("clubhouse", "Clubhouse-Inspired Lounge", "bar", "A private residential lounge with tailored leather, warm timber, textured plaster and a small drinks cabinet; traditional sporting-club familiarity without logos or a commercial bar.", "10-private-club-lounge-prompt.txt", True),
    RoomPreset("collector-display", "Collector Display Room", "collector", "A quiet private collection room with closed timber cabinetry and a restrained glass vitrine. Empty display space or a few ordinary unbranded objects; never invent sports memorabilia.", "08-collector-display-room-prompt.txt", True),
    RoomPreset("collector-lounge", "Collector Lounge", "collector", "An intimate sitting room with paired armchairs, a low cabinet and a reading lamp. The single supplied framed edition is the focal piece, with no retail-style display racks.", heritage=True),
    RoomPreset("living-room", "Living Room", "living", "A believable everyday premium living room with a sofa edge, side table and natural daylight, keeping the artwork at eye level.", "03-living-room-prompt.txt"),
    RoomPreset("modern-living", "Modern Living Room", "living", "A compact contemporary living space with low linear seating, matte plaster and a simple timber floor; show architectural calm without an empty showroom."),
    RoomPreset("heritage-living", "Heritage Living Room", "living", "A restored residential sitting room with restrained cornice detail, sash-window light, wool upholstery and aged hardwood flooring, comfortably furnished today.", heritage=True),
    RoomPreset("family-living", "Premium Family Living Room", "living", "A welcoming family lounge with a durable woven sofa, closed storage and one ordinary book; comfortable, tidy and lived-in, with no toys or people blocking the frame."),
    RoomPreset("apartment-living", "Apartment Living Room", "living", "A realistically compact apartment sitting room with a two-seat sofa, a side window and narrow circulation clearances. Never enlarge the apartment to make the artwork tiny."),
    RoomPreset("office", "Home Office", "work", "A real residential workspace with desk edge, ergonomic chair and restrained books; artwork on the clear wall beside the desk, without laptop or monitor glare.", "02-office-prompt.txt"),
    RoomPreset("executive-office", "Executive Office", "work", "A premium home executive workspace with a substantial walnut desk, tailored chair and flush storage; avoid corporate reception styling and keep the artwork dominant."),
    RoomPreset("study-library", "Study / Library", "work", "A residential reading study with warm timber bookshelves, one leather reading chair and a shaded desk lamp; mount the artwork on a clear plaster section, never cover it with books.", heritage=True),
    RoomPreset("garage", "Garage", "garage", "A clean working home garage with sealed concrete, modest overhead door tracks and closed storage; frame safely on a clear dry wall, no vehicle or tools obscuring it."),
    RoomPreset("collector-garage", "Collector Garage", "garage", "A carefully kept enthusiast garage with timber cabinets, a plain workbench and at most a small partial vehicle edge. No invented racing liveries, number plates, badges or signs.", heritage=True),
    RoomPreset("luxury-garage", "Luxury Garage", "garage", "A restrained architectural residential garage with honed floor, flush cabinetry and soft linear light. Avoid a car-showroom scene; the mounted edition is larger in the composition than any vehicle fragment."),
    RoomPreset("home-gym", "Home Gym", "fitness", "A calm private exercise room with rubber flooring, a simple bench and neatly stored weights at realistic scale; mount the frame on a dry clear wall away from equipment. No gym slogans."),
    RoomPreset("entry", "Luxury Entry Statement Wall", "architectural", "A residential entry with a slim console, stone or timber flooring and controlled negative space; the artwork is the first focal point, never a distant hallway accessory.", "09-luxury-entry-wall-prompt.txt"),
    RoomPreset("hallway", "Hallway Gallery Wall", "architectural", "A modest residential corridor with one clear gallery wall and realistic door spacing; this supplied artwork is the only wall art. Compose close enough for its details to read."),
    RoomPreset("landing", "Staircase / Landing Gallery", "architectural", "A safe broad landing with believable handrails, stair treads and a single flat wall for the frame; do not bend the frame around a corner or shoot from an impossible stair position."),
    RoomPreset("industrial-loft", "Industrial Loft", "architectural", "A converted residential loft with refined brick or concrete, restrained black metal and tall side-window light. Keep human-scale furniture and a close artwork wall, not a vast warehouse.", "17-architectural-loft-prompt.txt"),
    RoomPreset("premium-apartment", "Premium Apartment", "architectural", "An urban apartment entry or dining alcove with precise joinery, tactile plaster and a small stone console; distinguish it from an apartment living room by the architectural threshold composition."),
    RoomPreset("contemporary-home", "Contemporary Architectural Home", "architectural", "A present-day home with an offset clerestory, sculpted plaster junctions and restrained natural stone; focus on one intimate wall bay, with furniture supporting realistic scale."),
    RoomPreset("heritage-home", "Heritage Character Home", "architectural", "A renovated character home's entry or dining alcove with original joinery, modest mouldings and a contemporary bench; authentic patina with present-day comfort, not a historical set.", heritage=True),
    RoomPreset("fireplace", "Luxury Fireplace Feature Wall", "living", "A low working fireplace with a realistic stone surround; mount the product safely beside or well clear of the heat source. Fireplace remains secondary.", "12-fireplace-feature-wall-prompt.txt", True),
    RoomPreset("bedroom", "Premium Bedroom / Private Retreat", "living", "A quiet personal retreat with quality linen, a timber bedside table and soft wall light; use the clear side wall, with no hotel catalogue styling.", "13-premium-bedroom-prompt.txt"),
    RoomPreset("workshop", "Premium Tool Shed / Workshop", "garage", "A clean domestic workshop with a hardwood workbench, closed tool storage and a small number of accurately formed tools; the artwork is safely mounted above a clear surface.", "15-premium-tool-shed-workshop-prompt.txt", True),
)
ROOM_BY_KEY = {room.key: room for room in ROOMS}
ROOM_ALIASES = {
    "office": "office", "home sports bar": "sports-bar", "entry statement wall": "entry",
    "premium man cave with pool table": "pool-table", "man cave with pool table": "pool-table",
    "private club lounge collector retreat": "clubhouse", "architectural loft statement wall": "industrial-loft",
}


def design_type_options():
    return design_studio_styles.style_labels()


def room_for(value):
    if value in ROOM_BY_KEY:
        return ROOM_BY_KEY[value]
    normalized = re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).strip()
    key = ROOM_ALIASES.get(normalized)
    if key:
        return ROOM_BY_KEY[key]
    for room in ROOMS:
        if normalized == re.sub(r"[^a-z0-9]+", " ", room.label.casefold()).strip():
            return room
    raise ValueError("Choose a room from the Website Mockup Brief library.")


STYLE_CONTEXT = {
    "nostalgic_tribute": (("study-library", "clubhouse", "heritage-living", "collector-display", "man-cave"), "Warm, heritage, emotionally familiar collector atmosphere; express the tribute through the surrounding materials only."),
    "minimalist_hero": (("contemporary-home", "modern-living", "executive-office", "premium-apartment", "collector-lounge"), "Cleaner architectural lines, restrained furniture and purposeful breathing room without shrinking the hero product."),
    "vintage_restoration": (("heritage-home", "study-library", "premium-man-cave", "clubhouse", "collector-display"), "Heritage craftsmanship, character surfaces and subtle aged warmth around the untouched finished artwork."),
    "championship_achievement": (("entry", "sports-bar", "collector-display", "executive-office", "family-living"), "Confident premium statement placement that conveys achievement through architecture and light, never added trophies or text."),
    "rivalry_faceoff": (("man-cave", "sports-bar", "collector-lounge", "games-room", "industrial-loft"), "Stronger controlled contrast and energetic material tension in a real home; never invent rival/team branding."),
    "legends_jersey_display": (("collector-display", "study-library", "premium-man-cave", "clubhouse", "heritage-living"), "Established collector display character and careful lighting; jerseys already in the artwork remain immutable and no extra jerseys are generated."),
    "ultimate_moment": (("entry", "collector-display", "modern-living", "sports-bar", "premium-man-cave"), "Dramatic but physically natural light and premium hero placement around the exact captured moment; avoid synthetic cinematic effects."),
    "motorsport_driver_car": (("collector-garage", "industrial-loft", "executive-office", "workshop", "collector-display"), "Precision joinery, restrained industrial materials and enthusiast garage heritage; do not reconstruct any driver, vehicle or livery in the source."),
    "update_existing": (("living-room", "office", "collector-display", "entry", "man-cave"), "Use timeless collector presentation. This design-type label grants no permission to update or alter the uploaded finished artwork."),
}

SPORT_PALETTES = {
    "cricket": ("muted pavilion green", "warm heritage clubhouse cream", "deep charcoal-green"),
    "afl": ("heritage oval green", "warm clubroom cream", "muted earthy charcoal"),
    "rugby": ("traditional clubroom green", "heritage navy", "aged cream"),
    "football": ("muted stadium tunnel green", "deep terrace navy", "aged terrace cream"),
    "basketball": ("warm hardwood tan", "muted arena burgundy", "deep vintage navy"),
    "nfl": ("heritage locker-room green", "aged leather tan", "stadium concrete grey"),
    "baseball": ("classic ballpark green", "aged cream", "muted brick burgundy"),
    "motorsport": ("heritage racing green", "muted petrol blue", "warm concrete charcoal"),
    "hockey": ("cool heritage navy", "muted rink blue-grey", "warm arena cream"),
    "tennis": ("heritage grass green", "muted clay terracotta", "traditional cream"),
    "golf": ("clubhouse green", "muted olive", "warm cream"),
    "combat": ("vintage gym burgundy", "aged leather brown", "warm charcoal"),
    "horse-racing": ("racecourse pavilion green", "warm grandstand cream", "muted saddle brown"),
    "other": ("muted gallery taupe", "warm off-white", "deep neutral green"),
}
SPORT_ALIASES = {
    "nba": "basketball", "basketball-nba": "basketball", "soccer": "football", "football-soccer": "football",
    "association-football": "football", "american-football": "nfl", "american-football-nfl": "nfl",
    "australian-rules": "afl", "australian-rules-football": "afl", "aussie-rules": "afl",
    "rugby-union": "rugby", "rugby-league": "rugby", "nrl": "rugby", "nhl": "hockey", "ice-hockey": "hockey",
    "boxing": "combat", "mma": "combat", "ufc": "combat", "combat-sports": "combat",
    "formula-1": "motorsport", "formula-one": "motorsport", "f1": "motorsport", "motor-racing": "motorsport",
}
SPORT_ROOMS = {
    "cricket": ("clubhouse", "study-library", "heritage-living"), "golf": ("clubhouse", "study-library", "heritage-home"),
    "tennis": ("heritage-living", "premium-apartment", "clubhouse"), "motorsport": ("collector-garage", "industrial-loft", "workshop"),
    "basketball": ("industrial-loft", "media-room", "apartment-living"), "combat": ("home-gym", "man-cave", "collector-lounge"),
    "baseball": ("heritage-living", "study-library", "man-cave"), "rugby": ("clubhouse", "man-cave", "family-living"),
    "afl": ("family-living", "sports-bar", "man-cave"), "football": ("sports-bar", "premium-apartment", "collector-lounge"),
    "nfl": ("basement-lounge", "sports-bar", "collector-display"), "hockey": ("media-room", "collector-display", "sports-bar"),
    "horse-racing": ("clubhouse", "heritage-home", "study-library"),
}


def sport_key(sport):
    key = image_factory.slugify(str(sport or "").replace("_", " "))
    key = SPORT_ALIASES.get(key, key)
    return key if key in SPORT_PALETTES else "other"


def recommend_rooms(sport, design_type, era, product_name=""):
    style = design_studio_styles.normalize_design_style(design_type)
    preferred = STYLE_CONTEXT.get(style, STYLE_CONTEXT["update_existing"])[0]
    sport_preferences = SPORT_ROOMS.get(sport_key(sport), ())
    heritage = era in ERA_OPTIONS[:5] or any(word in product_name.casefold() for word in ("legacy", "legend", "heritage", "vintage"))
    def score(room):
        value = 60 - preferred.index(room.key) * 6 if room.key in preferred else 0
        value += 24 - sport_preferences.index(room.key) * 5 if room.key in sport_preferences else 0
        value += 8 if heritage and room.heritage else 0
        value += 5 if era in ("2010-2019", "2020-Present") and not room.heritage else 0
        return value
    ranked = sorted(ROOMS, key=lambda room: (-score(room), room.key))
    selected, families = [], set()
    for room in ranked:
        if room.family not in families:
            selected.append(room.key)
            families.add(room.family)
        if len(selected) == 3:
            return tuple(selected)
    raise ValueError("The room library must contain three different families.")


def selected_slot(snapshot, prompt_filename):
    return next((slot for slot in (snapshot or {}).get("slots", ()) if slot["filename"] == prompt_filename), None)


def create_snapshot(product_name, sport, design_type, era, rooms):
    style = design_studio_styles.get_design_style(design_type)
    if not str(product_name or "").strip() or not str(sport or "").strip():
        raise ValueError("Generate the product assets with a product name and sport first.")
    if style is None or era not in ERA_GUIDANCE:
        raise ValueError("Choose a Design Type and Era from the available options.")
    selected = [room_for(value) for value in rooms]
    if len(selected) != 3 or len({room.key for room in selected}) != 3:
        raise ValueError("Choose three different room environments; duplicate rooms are not allowed.")
    snapshot = {
        "version": WORKFLOW_VERSION, "id": uuid4().hex,
        "product_name": str(product_name).strip(), "sport": str(sport).strip(),
        "design_type": style.label, "design_type_slug": style.slug, "era": era,
        "slots": [{"number": number, "filename": SLOT_FILENAMES[number - 1], "room_key": room.key,
                   "label": room.label, "variant": room.variant} for number, room in enumerate(selected, 1)],
    }
    snapshot["master_prompt"] = build_master_prompt(snapshot)
    return snapshot


def room_prompt(room):
    """Retain existing room detail, adapting only obsolete ad/source instructions."""
    if not room.source:
        return room.brief
    spec = image_factory.get_lifestyle_prompt_spec(room.source)
    body = spec["prompt"]
    body = body.replace(build_sports_cave_image_realism_rules(), "").strip()
    body = re.sub(r"^This image is for .*?$", "This is a standalone website product photograph in a real customer's home.", body, flags=re.MULTILINE)
    body = body.replace("Meta ad carousel mockup", "website lifestyle mockup").replace("Meta ad mockup", "website lifestyle mockup")
    body = body.replace("from the last image created", "from the original uploaded full-resolution reference")
    body = body.replace("same exact design and frame as the previous image", "exact original uploaded design and frame")
    body = body.replace("premium black timber frame", "physical frame in the exact supplied material and colour")
    body = body.replace("exact same black landscape frame", "exact same supplied landscape frame")
    body = body.replace("suitable for a high-performing Meta advertisement", "suitable for a premium website product page")
    body = re.sub(r"\bad mockup\b", "website mockup", body)
    body = body.replace("subtle memorabilia silhouettes", "restrained unbranded objects").replace("carefully placed collector items", "a few ordinary unbranded objects")
    # Original safeguards remain intact; exact palette/home assignments below
    # override older illustrative neutral palettes and references to prior rooms.
    return f"{body}\n\nROOM-SPECIFIC WEBSITE DIRECTION:\n{room.brief}"


HOME_TREATMENTS = (
    "Home 1: an intimate rectangular room bay with standard-height ceiling, left-side window, warm timber flooring, a compact furniture grouping and matte plaster wall. Product-forward slight off-axis photograph, roughly 50mm lens character.",
    "Home 2: a broader offset room plan with a different ceiling treatment, right-side window or lightwell, natural stone or a low-pile rug, different furniture placement and finely brushed painted wall. Environmental interior photograph, roughly 40mm lens character; artwork remains dominant.",
    "Home 3: an asymmetric architectural bay with a distinct ceiling height suited to the chosen room, rear-side daylight, different timber tone or floor finish, independent joinery and textured mineral-painted wall. Photograph from the opposite side at a different camera height, roughly 55mm lens character.",
)


def build_master_prompt(snapshot):
    palettes = SPORT_PALETTES[sport_key(snapshot["sport"])]
    style_context = STYLE_CONTEXT.get(snapshot["design_type_slug"], STYLE_CONTEXT["update_existing"])[1]
    slots = snapshot["slots"]
    lines = [build_sports_cave_image_realism_rules(), f"""WEBSITE MOCKUP BRIEF — THREE LOCKED PHOTOGRAPHS
PRODUCT NAME: {snapshot['product_name']}
SPORT: {snapshot['sport']}
DESIGN TYPE: {snapshot['design_type']}
ERA: {snapshot['era']}
REFERENCE PRODUCT: Upload the original full-resolution framed Sports Cave product using Load Full Resolution. Use that exact source for every image, never a preview or a previously generated mockup. If it is missing, request it before generating.

Design Type, Era and Sport influence ONLY the customer environment; never alter the finished artwork, uniforms, equipment, faces, text, badges, frame or any source detail. Do not mirror the product. Do not fabricate missing details or 'improve' the artwork.
DESIGN-TYPE ENVIRONMENT: {style_context}
ERA ENVIRONMENT: {ERA_GUIDANCE[snapshot['era']]}
These are believable premium homes TODAY, not historical movie sets or literal decade recreations. Do not infer the collector's age from an old artwork.
SPORT ENVIRONMENT: Use the assigned complementary sport-nostalgia palette through architecture, wall finishes, timber, furniture and light. Restrained saturation only. Do not copy team jerseys, add logos, slogans, fake team branding, random sports memorabilia or theme-park decor. The product must remain the visual hero.

THREE WEBSITE MOCKUPS ARE LOCKED:
"""]
    lines.extend(f"MOCKUP {slot['number']} — {slot['label']}" for slot in slots)
    lines.append("""Treat these as three separate standalone website product photographs in THREE DIFFERENT REAL CUSTOMER HOMES, not three corners of one property. Never combine them into a collage, triptych, contact sheet or one image. Never change their order or silently substitute another room.
Each home must differ in architecture, room dimensions, ceiling treatment, wall material/colour, flooring, furniture and placement, window position, natural-light source, practical lighting, timber and camera viewpoint. Changing cushions, one chair, one lamp or merely recolouring the same wall is insufficient. Use three separate professional interior-photography assignments.
The exact uploaded product stays identical in all three. Output exactly 1024 x 1024 per image, composed square from the start. Keep the complete frame and all artwork unobstructed, realistically mounted at eye level, prominent and readable on mobile; normally about 45–60% of useful composition. Never make the product tiny in a wide room shot.
Each room's strong camera brief may refine its assigned viewpoint, but it must remain different from the other two, with coherent rigid product perspective. Room-specific architectural constraints take precedence over an incompatible example ceiling/window; choose an equally distinct physically possible home.
Assigned wall treatments and environment-only context take precedence over older optional palette examples in reused room presets. Source/product locks always take precedence. No people, added text, watermarks or extra wall art. Never let decorative reflections obscure artwork or edition information.
""")
    for slot, palette, home in zip(slots, palettes, HOME_TREATMENTS):
        room = room_for(slot["room_key"])
        lines.append(f"MOCKUP {slot['number']} — {slot['label']} — LOCKED ROOM BRIEF\n{room_prompt(room)}\n\nASSIGNED CUSTOMER HOME: {home}\nASSIGNED WALL TREATMENT: {palette}; use the finish assigned to this home, with restrained saturation and realistic texture. This is this mockup's fixed palette, not a suggestion to repeat the other walls.")
    lines.append("""SEQUENTIAL CHATGPT GENERATION — KEEP THESE BRIEFS LOCKED
Generate MOCKUP 1 first, as one standalone image, then wait.
When the user says "Generate Mockup 2", generate only the locked Mockup 2 brief.
When the user says "Generate Mockup 3", generate only the locked Mockup 3 brief.
Do not generate all three simultaneously. Do not use Mockup 1's room for Mockup 2. Regenerating one image must not redesign the others or swap room order. Always return to the original uploaded full-resolution product.
Before returning each image, inspect dimensions, full frame visibility, exact artwork/text/edition fidelity, frame geometry, glass reflections, contact shadows, lighting, product prominence and the assigned room/home/palette. Correct failures within that locked brief without inventing product details.""")
    return "\n\n".join(lines).strip()


def prompt_items(snapshot):
    # Existing storage still has three permanent prompt/upload identities. All
    # files carry the same locked master, so a prompt pack retains the contract.
    return [{"key": image_factory.prompt_key_from_prompt_filename(slot["filename"]),
             "filename": slot["filename"], "label": f"{slot['number']:02d} — {slot['label']}",
             "prompt": snapshot["master_prompt"]} for slot in snapshot["slots"]]


def apply_slot_metadata(asset, slot):
    if slot:
        asset = dict(asset)
        asset.update(label=f"{slot['number']:02d} — {slot['label']}",
                     website_mockup_room=slot["label"], website_mockup_variant=slot["variant"])
    return asset


def apply_snapshot_assets(assets, snapshot):
    """Give existing permanent slots their submitted room metadata, even if empty."""
    result = [dict(asset) for asset in assets]
    by_key = {asset.get("key"): index for index, asset in enumerate(result)}
    for slot in snapshot["slots"]:
        key = f"lifestyle::{slot['filename']}"
        if key in by_key:
            index = by_key[key]
            result[index] = apply_slot_metadata(result[index], slot)
        else:
            result.append(apply_slot_metadata(image_factory.build_asset_record(
                key=key, label=slot["label"], asset_group="lifestyle",
                zip_group=image_factory.ASSET_CATEGORY_PRODUCT, prompt_filename=slot["filename"],
            ), slot))
    return result
