"""Visual-only composition for standard IE; persisted slot identities stay unchanged."""
import hashlib
import random


FAMILIES = ("premium_scarcity_smart_hybrid", "private_gallery", "the_cave")
CAMERAS = ("STRAIGHT, 0–2° natural offset", "SLIGHT RIGHT, 4–7° right of centre",
           "SLIGHT LEFT, 4–7° left of centre", "SUBTLE THREE-QUARTER, 7–10° right of centre")
GALLERY_CAMERAS = ("STRAIGHT GALLERY, 0–2°", "VIEWER RIGHT, 4–8°",
                   "VIEWER LEFT, 4–8°", "SLIGHT EDITORIAL THREE-QUARTER, 8–12° right of centre")
SCARCITY_RULE = ('ON-IMAGE SCARCITY WORDING: When writing a limited-edition label use LIMITED TO {verified limit} or LIMITED EDITION '
                 'when approved. Never append worldwide, world wide, globally, or any geographic '
                 'scope to an edition claim, even when source metadata or description copy uses it. '
                 'Never invent a limit. Immutable wording already inside the source artwork stays untouched.')


def resolve_visual_system(visual, index, context, variation_token):
    """Extend the existing resolved product context, never resolve commercial facts here."""
    seed = hashlib.sha256(f"{visual['resolved_seed']}:{variation_token}:{visual['route_key']}".encode()).digest()
    rng = random.Random(int.from_bytes(seed[:8], "big"))
    camera = rng.choice(GALLERY_CAMERAS if index == 1 else CAMERAS)
    visual.update(visual_family=FAMILIES[index], camera_role=camera.split(',')[0],
                  camera_side=camera, camera_instruction=f"Use {camera}. Keep readability excellent, verticals straight and the complete frame rigid. Never mirror artwork.",
                  creative_variation_token=variation_token or "standard")
    if index == 0:
        return
    heritage = context.get("product_era") == "historic" or context.get("artwork_mood") == "heritage"
    walls = (("warm taupe Venetian plaster", "aged warm stone plaster", "warm cream/stone gallery plaster")
             if heritage else ("deep charcoal mineral plaster", "smoked graphite limewash", "restrained architectural concrete"))
    if index == 2:
        walls = (("muted bronze-brown limewash", "warm dark taupe plaster", "dark chocolate mineral")
                 if heritage else ("deep warm charcoal plaster", "graphite mineral plaster", "restrained warm grey concrete-like plaster"))
    wall = rng.choice(walls)
    limit = context.get("edition_limit")
    scarcity = f"LIMITED TO {limit}" if limit else "LIMITED COLLECTOR RELEASE"
    visual.update(wall_colour=wall, wall_material=wall, wall_finish=wall,
                  room_profile="sophisticated private collector gallery" if index == 1 else "real premium fan sanctuary",
                  room_type="private gallery" if index == 1 else "premium collector den",
                  room_materials="restrained dark timber and quiet mineral plaster",
                  primary_cue="minimal low gallery cabinet" if index == 1 else "low credenza with completely empty cabinet top",
                  secondary_cue="none", architectural_cue="quiet seamless collector wall",
                  lighting="one gallery picture light with restrained natural ambient fill",
                  shot_distance="dominant complete framed artwork within the photographic zone",
                  overlay_position="small flat editorial branding in negative space" if index == 1 else "full-height flat right graphic column, 32–34% width",
                  product_position="dominant gallery wall artwork" if index == 1 else "dominant in the left 66–68% photographic zone",
                  composition="1024 x 1024 private-gallery photograph, no scarcity footer" if index == 1 else "1024 x 1024, left 66–68% room, right 32–34% graphic column",
                  headline_text="FOR THE ROOM THAT REMEMBERS." if index == 1 else "THE CAVE\nSTARTS\nHERE.",
                  supporting_line=scarcity, cta_text="", typography_mode=FAMILIES[index])


def camera_wall_rules(visual):
    cameras = GALLERY_CAMERAS if visual["visual_family"] == "private_gallery" else CAMERAS
    return f"""SMART CAMERA / ROOM / WALL RESOLUTION
CREATIVE_VARIATION_TOKEN: {visual['creative_variation_token']}
Use the token only for creative freshness; never display it or internal metadata on the image.
Permissible camera families at planning time: {'; '.join(cameras)}.
Selected camera: {visual['camera_side']}.
Resolve exactly ONE camera before printing the final standalone prompt; omit the alternatives from that final prompt. A three-quarter view is permitted only while product readability remains excellent.
Analyse the actual attached product, SPORT, MARKET, title, palette, brightness, frame colour, emotional mood, era/nostalgia and campaign context. The actual product wins over sport tendencies.
Use the resolved scene below as the product-aware starting selection. If the uploaded artwork requires better contrast or frame separation, resolve ONE suitable wall and room before returning the standalone prompt. Never leave alternatives unresolved.
For Smart Hybrid, base the room on premium neutral living, heritage collector study or refined masculine collector lounge; an understated home office, premium media room or quiet collector den is also suitable. Match seamless greige stone render, warm stone mineral plaster, soft taupe limewash, warm charcoal, graphite, restrained warm grey or muted stone to the product.
Private Gallery uses charcoal mineral plaster, smoked graphite limewash, taupe Venetian plaster, aged stone, chocolate mineral, restrained concrete, olive-charcoal or cream/stone gallery plaster; architectural timber stays outside the artwork area.
The Cave uses warm charcoal, graphite mineral, bronze-brown limewash, dark taupe, aged stone-charcoal, chocolate mineral, warm grey concrete-like plaster or dark olive-charcoal.
Choose one primary environmental cue and at most one secondary cue. Keep The Cave cabinet completely empty.
Avoid identical wall/camera combinations across recent fingerprints and this package where suitable; product matching wins. Vary only visual interpretation, never product identity, branding, edition limits or verified facts.
{SCARCITY_RULE}"""


def render_editorial_prompt(visual, *, product_name, category, country, product_url,
                            metadata, shared_rules, core_rules, adaptation, campaign_context):
    gallery = visual["visual_family"] == "private_gallery"
    layout = ("""SPORTS HISTORY DISPLAYED LIKE COLLECTIBLE ART.
Artwork dominates a sophisticated private collector/gallery environment with minimal premium furniture, deliberate gallery lighting, genuine frame depth and premium clear acrylic/glazing.
No Premium Scarcity fixed bottom footer. Small SPORTS CAVE branding; flat editorial typography in clear negative space.
Signature on two lines: FOR THE ROOM / THAT REMEMBERS.
No fake CTA, sale banner, discount graphics, obvious sports props or generic man-cave clutter.""" if gallery else """A REAL PREMIUM FAN SANCTUARY.
LEFT VISUAL: 66–68% width, premium realistic room with dominant framed product.
RIGHT GRAPHIC COLUMN: 32–34% width, full height, flush top, flush bottom and flush right; flat matte near-black 2D advertising design. No wall texture, perspective, room shadows or physical plaque effect. No bottom footer.
Exact hierarchy: SPORTS CAVE, then THE CAVE / STARTS / HERE., then the resolved scarcity line, then COLLECTOR SERIES.
White / warm ivory headline, never gold. Restrained antique-gold accent rules only. Premium vintage/editorial/collector typography.
Room core: framed product, premium collector wall, one gallery picture light, low cabinet / credenza. An optional small partial leather-chair crop is the only extra furniture cue.
CABINET TOP MUST BE COMPLETELY EMPTY. No generated filler: no books, bowls, plants, alcohol, mugs, sports objects, clocks, trophies, helmets, jerseys or decorative clutter.""")
    return f"""IMAGE GENERATION PROMPT

Copy this prompt into a fresh image-generation conversation with the exact uploaded Sports Cave product image attached.
Do not generate the image automatically from this Ads-planning response.
SPORTS CAVE — {visual['route'].upper()} META AD SYSTEM
PRODUCT AND VERIFIED METADATA
Product name: {product_name}
Sport/category: {category}
Country/market: {country}
Destination URL for ad setup only: {product_url}
Route key: {visual['route_key']}
Product era/mood classification: {visual['product_era']} / {visual['artwork_mood']}
Edition limit used: {visual['edition_limit_used']}
Edition limit source: {visual['edition_limit_source']}

{camera_wall_rules(visual)}
RESOLVED ROUTE VARIABLES
Camera: {visual['camera_side']}
Room: {visual['room_profile']}
Wall: {visual['wall_colour']}
Furniture: {visual['primary_cue']}
Secondary cue: {visual['secondary_cue']}
Lighting: {visual['lighting']}
{layout}
Only permitted advertising wording:
SPORTS CAVE
{visual['headline_text']}
{visual['supporting_line']}
{'COLLECTOR SERIES' if not gallery else ''}
Never place description copy or a CTA on this image. Add text as a deterministic flat post-production layer with real fonts. Keep safe margins and readable type at a 256 x 256 preview.
Resolved prompt metadata (never visible ad text):
{metadata}
{core_rules}
AUTHORITATIVE APP-WIDE PRODUCT AND REALISM LOCK
{shared_rules}
{adaptation}
{campaign_context}
FINAL REJECTION GATE
Correct or regenerate if artwork, frame, faces, words, numbers, signatures, badges, logos, composition or edition plate changes; if artwork is mirrored; if frame depth, clear glazing, physical contact/secondary/lower frame shadows or mounting gap is missing; if lighting/reflections disagree; if the room looks AI-generated or cluttered; if typography is misspelled, duplicated, unreadable or outside its layout; if unverified scarcity is invented; or if any other visual family's footer or campaign text appears.
Require a true square, exactly 1024 x 1024 pixels, sRGB. If native output differs, resize the approved square deterministically; never stretch a non-square image. Check product fidelity, photographic realism, mobile readability and this format's layout before delivery. Do not print scores or reasoning.
"""
