from __future__ import annotations


SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER = "SPORTS_CAVE_IMAGE_REALISM_RULES_V1"


SPORTS_CAVE_GLOBAL_PHOTOGRAPHIC_REALISM_BLOCK = """GLOBAL PHOTOGRAPHIC REALISM RULES - MANDATORY
PHOTOREALISM AND HUMAN REALISM - MANDATORY
These rules apply to every ChatGPT request that creates, transforms, extends, composites, animates or otherwise produces a Sports Cave image or visual. These rules override any conflicting creative direction, style request, workflow note, room idea, camera idea, campaign concept or platform instruction.

The final output must look like genuine professional photography or physically believable real-world footage. It must not look AI-generated, CGI, rendered, illustrated, painted, plastic, glossy, video-game-like, synthetic, over-smoothed, over-sharpened or fake.

Use natural professional photography:
- believable camera perspective, scale, lens choice and depth
- straight architectural lines and physically possible room geometry
- realistic furniture, wall, floor, ceiling and material proportions
- natural textures on timber, paper, glass, plaster, fabric, metal and skin
- consistent light direction, colour temperature, reflections and shadows
- realistic contact shadows, ambient occlusion and object weight
- no excessive HDR, bloom, glow, sharpening, fisheye distortion, fake blur or synthetic colour grading
- no floating, melted, duplicated, malformed, impossible, intersecting or physically incoherent objects
- no warped walls, bent shelves, impossible windows, distorted furniture, fake luxury clutter or random generated props

When people appear, they must look like real people photographed in the scene:
- Faces must remain natural, recognisable and anatomically correct
- realistic faces, skin texture, hair, eyes, teeth, hands, fingers, wrists, arms, anatomy, posture and clothing
- natural asymmetry and believable imperfections
- correct number of limbs and fingers
- no waxy skin, mannequin bodies, duplicated fingers, melted hands, disconnected limbs, uncanny eyes, fake smiles or stock-model posing
- people, hands, furniture, glare, logos, branding and overlays must never cover the hero product or important product details unless the workflow explicitly asks for a separate deterministic branded export layer

Respect the requested output format exactly:
- use the exact requested dimensions and aspect ratio
- compose for that canvas from the start rather than cropping from another format
- keep all critical subject matter inside platform-safe areas when safe areas are supplied
- before returning, inspect the final result for correct dimensions, clean geometry, realistic materials, consistent light, readable product details and absence of obvious AI artifacts"""


SPORTS_CAVE_PRODUCT_MOCKUP_LOCK_BLOCK = """SPORTS CAVE PRODUCT AND MOCKUP LOCK - MANDATORY
PRODUCT LOCK:
PRODUCT AND ARTWORK LOCK - MANDATORY
Apply this product lock whenever an uploaded Sports Cave product, artwork, framed product, framed mockup or product reference image is used as the source.

Treat the uploaded full-resolution product as an immutable physical asset. Use the uploaded image directly as the source, not a screenshot, thumbnail, compressed preview, metadata description, memory of the image, rough approximation or AI recreation.

Preserve the complete artwork exactly:
- every athlete, face, body, team, vehicle, stadium, crowd, background, equipment and supporting image
- every word, letter, number, logo, signature, title, subtitle, font, colour, border, crop, layout and design element
- every limited-edition badge, plaque, collector badge, numbered detail and edition plate exactly as supplied
- the exact artwork aspect ratio inside the frame
- the exact frame colour, material, thickness, depth, proportions, crop and outer geometry
- the exact black frame colour, material, thickness and proportions when the supplied product uses a black frame

Never fabricate, repair, replace or invent product details:
- Do not redesign the artwork.
- Do not change the athlete, subject, team, colours, text, typography, badge, edition plate, plaque, layout, crop, frame colour, frame shape, or composition inside the frame.
- Never invent or change an edition number.
- no fake edition numbers, unreadable plaque information, invented signatures, fake logos, new team marks, new sporting details or made-up text
- do not recolour, enhance, repaint, sharpen, soften, upscale, regenerate, reinterpret, redraw, approximate or create a lookalike version of the artwork
- do not mirror the artwork if it reverses text, numbers, logos, livery, jersey details or signatures
- do not crop, zoom, stretch, squash, bend, bow, twist, curve, taper, warp, blur, melt, reshape or distort the product, artwork, frame, glass, plaque, badge or typography

FRAME REALISM:
Lock the frame geometry:
- keep all four outer frame edges straight and all corners structurally correct
- keep the complete outer frame visible whenever the product is shown as a framed product
- preserve the rectangular landscape proportions of the frame and artwork
- natural camera perspective may affect the whole product only as one rigid rectangular physical object
- never allow conflicting perspective between the frame, artwork, glass, wall, furniture and room
- never make the product larger by cutting off its outer edges; move the camera closer while preserving the complete frame

Require genuine physical frame construction:
- believable timber or frame depth
- consistent thickness on all visible sides
- sharp square corners and clean mitred joins
- subtle realistic frame texture
- realistic bevels, edges, weight and scale
- physical mounting, contact shadows, ambient occlusion and light direction that match the room

GLASS REALISM:
Require realistic transparent glass:
- genuine clear glass over the artwork, not fake shine or missing glazing
- restrained room-based reflections, subtle natural glare and realistic highlight falloff
- reflections consistent with the windows, lights and camera angle
- glass must never obscure, wash out, rewrite, distort or hide faces, typography, logos, artwork, badge, plaque or edition details

ROOM REALISM:
Require believable placement:
- the product must look mounted, held or placed naturally in the room
- it must never float, sink into a wall, intersect furniture, bend around a corner, detach from shadows or look digitally pasted on
- wall shadows, contact shadows and ambient occlusion must match the product size, mounting depth and room lighting

Keep the Sports Cave product as the visual hero:
- the room supports the product; Sports Cave is selling the framed edition, not the room
- keep the framed product prominent, dominant and large enough to understand on mobile
- avoid distant wide-room compositions that make the frame small or secondary
- prevent people, hands, furniture, glare, decor, branding, overlays or platform UI space from covering the product or important details

Mandatory final product inspection:
- confirm the uploaded artwork and frame remain unchanged
- confirm every face, word, number, colour, logo, signature, badge, plaque and edition plate is preserved
- confirm the product is straight, rigid, complete, correctly proportioned, physically mounted or held, realistically lit, protected by transparent glass and free from obvious AI artifacts"""


def build_sports_cave_image_realism_rules(*, include_product_lock: bool = True) -> str:
    sections = [
        SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER,
        "AUTHORITATIVE SPORTS CAVE IMAGE REALISM RULES",
        "This shared master block is mandatory and overrides conflicting creative direction.",
        SPORTS_CAVE_GLOBAL_PHOTOGRAPHIC_REALISM_BLOCK,
    ]
    if include_product_lock:
        sections.append(SPORTS_CAVE_PRODUCT_MOCKUP_LOCK_BLOCK)
    else:
        sections.append(
            "ORIGINAL ARTWORK MODE - PRODUCT LOCK EXCLUSION\n"
            "This prompt creates a brand-new Sports Cave artwork or reference search output rather than placing an existing completed framed product into a scene. Apply the global photographic realism and accuracy rules above, but do not treat a nonexistent completed product as immutable."
        )
    return "\n\n".join(section.strip() for section in sections if str(section).strip())


def prompt_has_sports_cave_image_realism_rules(prompt_text: str) -> bool:
    return SPORTS_CAVE_IMAGE_REALISM_RULES_MARKER.casefold() in str(prompt_text or "").casefold()


def append_sports_cave_image_realism_rules(
    prompt_text: str,
    *,
    include_product_lock: bool = True,
    required_ending: str = "",
) -> str:
    prompt_text = str(prompt_text or "").strip()
    if prompt_has_sports_cave_image_realism_rules(prompt_text):
        return prompt_text

    block = build_sports_cave_image_realism_rules(
        include_product_lock=include_product_lock
    )
    ending = str(required_ending or "").strip()
    if ending and prompt_text.rstrip().endswith(ending):
        body = prompt_text.rstrip()[: -len(ending)].rstrip()
        return f"{body}\n\n{block}\n\n{ending}" if body else f"{block}\n\n{ending}"
    return f"{prompt_text}\n\n{block}" if prompt_text else block


SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK = """UGC HUMAN REALISM REQUIREMENTS:
If a person appears in the scene, make them look like a real everyday customer captured on a modern phone camera, not a model, actor, mannequin, stock-photo subject, or AI-generated person.

The person must look naturally human:
- realistic facial structure
- natural asymmetry
- real skin texture with pores
- subtle under-eye detail
- natural hairline and hair texture
- realistic beard/stubble if present
- normal hands and fingers
- believable wrists, arms, shoulders, neck, posture, and body proportions
- natural clothing folds, seams, cuffs, fabric weight, and slight wrinkles
- realistic shoes, socks, sleeves, hoodie, t-shirt, jeans, shorts, or casual homewear
- believable body language and natural customer posture
- relaxed facial expression, not over-posed
- normal eye direction and natural head angle
- subtle imperfections that real phone footage would capture

The person should feel like a happy customer casually filming or appearing in a real UGC-style home video:
- natural movement
- slightly imperfect posture
- casual handling of the frame
- believable grip on the frame
- realistic hand placement on the frame edges
- natural scale compared to the artwork, sofa, wall, room, and furniture
- no glamour posing
- no fashion-shoot lighting on the person
- no overly perfect skin
- no waxy texture
- no plastic skin
- no airbrushed face
- no distorted hands
- no twisted fingers
- no fake smile
- no uncanny eyes
- no blurred facial features
- no duplicated limbs
- no warped anatomy

Camera style:
The scene should feel like premium UGC captured on an iPhone or modern phone camera by a real customer in their home.
Use natural handheld realism, subtle camera imperfection, slight lens softness, realistic depth of field, true-to-life lighting, and believable motion.
It should still feel premium and cinematic, but not staged like a commercial photoshoot.

Lighting:
Match the person naturally to the room lighting.
The face, hands, clothing, and body must share the same light direction, shadow softness, colour temperature, and contrast as the room.
Add realistic contact shadows where the person touches the floor, wall, frame, sofa, table, or nearby objects.
The person must feel physically inside the room, not pasted on.

Clothing:
Use realistic casual customer clothing that fits the room:
- black hoodie
- plain t-shirt
- relaxed jacket
- jeans
- joggers
- casual sneakers
- neutral colours
- no loud branding
- no fake logos
- no unreadable graphic text
- no sports team logos unless supplied
- no luxury fashion styling
- no costumes

Age and identity:
Use a believable adult customer, usually male 25-55 unless the prompt specifically asks otherwise.
Do not make the person look like a celebrity, athlete, influencer, model, or fake AI character.
Do not over-muscularize the body.
Do not exaggerate jawline, cheekbones, hands, height, or body shape.

UGC realism target:
The final scene should look like a real happy customer has just installed, received, held, or admired their Sports Cave artwork in their own home.
A viewer should feel the product is real, the room is real, the person is real, and the moment is believable."""


SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK = SPORTS_CAVE_PRODUCT_MOCKUP_LOCK_BLOCK


SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK = """UGC VIDEO REALISM:
For video/reel prompts with people, make the motion feel like real customer phone footage.
The movement should be natural, slightly imperfect, and believable:
- person walks into frame naturally
- person lifts or adjusts the frame carefully
- hands grip the frame edges realistically
- slight body shift as they balance the frame
- natural breathing and posture
- subtle head movement
- realistic arm movement
- realistic clothing movement
- realistic shadows moving with the person
- no robotic motion
- no floating frame
- no sliding hands
- no hands passing through frame
- no frame warping during movement
- no room distortion during camera movement
- no face melting
- no flickering facial features
- no changing clothing between frames
- no changing frame size between frames
- no artwork morphing, flickering, blurring, or changing

The video should feel like a real happy customer or friend filmed it on a phone after receiving or installing the artwork.
Premium UGC, not fake commercial footage."""


SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK = """ARTWORK FREEZE LOCK - CRITICAL

The framed Sports Cave artwork is a locked source image and must remain visually identical for the entire video.

Treat the artwork inside the frame as a flat, frozen, printed poster texture.
Do not regenerate, repaint, redraw, reinterpret, enhance, upscale, sharpen, stylise, or re-render the artwork.
Do not alter any text, typography, title, plaque, badge, edition number, athlete, face, uniform, colours, layout, signatures, border, or composition inside the frame.

The artwork must remain perfectly stable frame-to-frame.
No morphing.
No melting.
No text changes.
No letter scrambling.
No plaque distortion.
No badge distortion.
No face changes.
No colour shifts.
No AI enhancement effects applied to the artwork.
No moving elements inside the printed artwork.
No animated artwork.
No changing reflections that obscure or rewrite the artwork.

The camera must not move aggressively toward the frame, zoom toward the print, move laterally over the artwork, tilt over the artwork, or crop into the artwork.
Avoid close-up moves over the text, faces, plaque, badge, or edition number.
Keep the full framed artwork visible and readable for the entire shot.
Keep the frame edges straight, rectangular, and locked to correct perspective.

Camera movement must be extremely subtle and slow:
- locked-off tripod shot preferred
- or very slow micro dolly / gentle handheld realism only
- no fast zoom
- no crash zoom
- no parallax warp across the artwork
- no orbiting movement around the frame
- no whip pan
- no rack-focus that blurs the artwork
- no motion blur over the artwork
- no lens distortion on the frame

Only the room environment may have subtle life:
soft natural light shift, tiny glass reflection movement, slight ambient camera breathing, realistic shadows, subtle customer movement if present.
The printed artwork itself must remain unchanged like a real physical poster behind glass.

If the model cannot preserve the artwork perfectly, choose the safest fallback:
use a mostly static camera, keep the full frame visible, animate only the surrounding room lighting/reflections very subtly, and do not move the camera closer to the artwork.

QUALITY CONTROL RULE:
Reject the video if the artwork text changes, the title becomes unreadable, the plaque or edition number changes, the player face changes, the frame bends, the artwork crops in, or the camera movement causes any warping.

SAFE VIDEO CAMERA DEFAULTS

Use a premium locked-off DSLR video shot with only very subtle motion.
The camera should feel mounted on a tripod with a tiny natural drift.
Keep the framed artwork fully visible for the entire video.
Do not zoom closer than the starting composition.
Do not crop into the artwork.
Do not move fast.
Do not create dramatic camera movement.
The product must remain readable, stable, and physically real from the first frame to the last frame."""


HUMAN_SCENE_TERMS = (
    "person holding",
    "person hanging",
    "person adjusting",
    "person standing",
    "person admiring",
    "person unboxing",
    "person opening",
    "person receiving",
    "person revealing",
    "with a person",
    "with one person",
    "customer holding",
    "customer holds",
    "customer making",
    "customer stands",
    "customer standing",
    "customer admiring",
    "customer unboxing",
    "customer opening",
    "customer receiving",
    "customer revealing",
    "with a customer",
    "customer in the room",
    "customer in a man cave",
    "customer in a living room",
    "customer in an office",
    "customer in a bedroom",
    "customer in a home gym",
    "realistic male customer",
    "real everyday customer",
    "hands grip",
    "hands on the outer frame",
    "hands must",
    "person walks",
    "person lifts",
    "standing back admiring",
)

NO_PERSON_TERMS = (
    "do not add people",
    "no people",
    "no person",
    "no faces",
    "do not add hands",
    "no hands",
)


def prompt_includes_human_scene(prompt_text: str) -> bool:
    text = str(prompt_text or "").lower()
    has_positive_human_scene = any(term in text for term in HUMAN_SCENE_TERMS)
    if not has_positive_human_scene:
        return False
    has_no_person_instruction = any(term in text for term in NO_PERSON_TERMS)
    return has_positive_human_scene and not has_no_person_instruction


def append_unique_block(prompt_text: str, block: str) -> str:
    prompt_text = str(prompt_text or "").strip()
    block = str(block or "").strip()
    if not block or block in prompt_text:
        return prompt_text
    return f"{prompt_text}\n\n{block}" if prompt_text else block


def append_sports_cave_prompt_blocks(
    prompt_text: str,
    *,
    include_human: bool = False,
    include_video: bool = False,
    include_product_lock: bool = True,
) -> str:
    result = str(prompt_text or "").strip()
    if include_human:
        result = append_unique_block(result, SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK)
    result = append_sports_cave_image_realism_rules(
        result,
        include_product_lock=include_product_lock,
    )
    if include_video:
        result = append_unique_block(result, SPORTS_CAVE_VIDEO_ARTWORK_FREEZE_LOCK)
    if include_human and include_video:
        result = append_unique_block(result, SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK)
    return result
