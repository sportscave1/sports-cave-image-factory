from __future__ import annotations


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


SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK = """SPORTS CAVE PRODUCT LOCK:
Keep the uploaded Sports Cave artwork and frame exactly the same.
Do not redesign the artwork.
Do not change the athlete, subject, colours, text, badge, edition plate, plaque, layout, crop, frame colour, frame shape, or composition inside the frame.
Do not blur, stretch, warp, bend, squash, distort, repaint, redraw, replace, or reinterpret the artwork.
The artwork must remain sharp, rectangular, correctly aligned, and physically believable inside the frame.

FRAME REALISM:
The black frame must look like a real premium framed product:
- realistic timber or frame depth
- sharp square corners
- believable glass over the artwork
- soft natural reflections
- subtle glare that does not hide the artwork
- realistic wall shadow
- accurate perspective
- correct scale relative to the person and room

ROOM REALISM:
The room must remain realistic, premium, and believable.
Do not distort walls, furniture, lamps, sofas, curtains, shelves, floors, or architecture.
No warped walls.
No impossible furniture.
No random logos.
No fake trophies.
No clutter.
No messy room.
No obvious AI room.
No neon signs unless very subtle.
The framed artwork must look mounted, held, or placed naturally in the room, not pasted on."""


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
    if include_product_lock:
        result = append_unique_block(result, SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK)
    if include_human and include_video:
        result = append_unique_block(result, SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK)
    return result
