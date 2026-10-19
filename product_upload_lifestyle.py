"""Product Upload's master brief. Shared Mockups templates/overrides are read only."""
import hashlib
import re

PROMPT_ID = 'lifestyle::product-upload-master-v1'
ROOMS = (
    ('contemporary collector lounge', 'industrial converted garage lounge', 'refined whiskey lounge', 'pool-table room', 'intimate media room'),
    ('bright architectural home office', 'dark timber executive study', 'creative studio', 'library office', 'minimalist workspace'),
    ('airy coastal room', 'modern city apartment', 'warm mid-century interior', 'restrained luxury lounge', 'textured contemporary family room'),
)
LABELS = ('Man Cave', 'Office', 'Living Room')
ROOM_COMBINATIONS = ((1,0,2),(2,2,0),(0,1,1),(3,4,4),(4,3,3))
FILENAMES = ('01-man-cave-prompt.txt', '02-office-prompt.txt', '03-living-room-prompt.txt')

INSTRUCTIONS = '''Use the attached full-resolution BLACK-FRAMED PRODUCT as the exact artwork/frame reference throughout this conversation. Do not reproduce its surrounding background or room lighting.
First provide THREE complete, separately labelled image-generation prompts: 1. Man Cave, 2. Office, 3. Living Room, matching the upload cards. Each must work independently: repeat the full exact-product, A1 physical-scale, premium-glazing, composition and output requirements in EACH prompt, never refer to another prompt for these requirements.
Then immediately start generating image 1. Generate each mockup as a SEPARATE image: never a collage, triptych, contact sheet or three rooms within one image. Wait until image 1 is approved/finalised before generating image 2, then await approval/finalisation before image 3. Keep using the ORIGINAL attached product reference, never a previously generated room image as the new product reference. These are instructions for our ChatGPT conversation; Sports Cave OS does not control that conversation.
The three scenes must be visibly different properties/interiors, not variations of one house. Choose strongly contrasting architecture, wall materials/colours, furniture, layout, lighting, styling, camera positions and surrounding objects. Changing only accessories or camera angle is insufficient. Honour explicitly selected room/angle directions. Keep all scenes premium and believable. If another version is requested, choose a substantially different room from those already generated in this conversation, retaining explicit user settings.
Available Man Cave directions: contemporary collector lounge; industrial converted garage lounge; refined whiskey lounge; pool-table room; intimate media room.
Available Office directions: bright architectural home office; dark timber executive study; creative studio; library office; minimalist workspace.
Available Living Room directions: airy coastal room; modern city apartment; warm mid-century interior; restrained luxury lounge; textured contemporary family room.
Use the three resolved scene briefs below, including their saved customisations. Preserve output aspect ratio/resolution independently of physical product size. If source proportions or verified construction/size specifications conflict, identify the conflict and request clarification rather than stretching, cropping, inventing dimensions or changing the product.'''

PER_IMAGE = '''EXACT PRODUCT: Preserve the attached original artwork, lettering, signatures, borders, colours, faces, details, proportions and black-frame appearance exactly. No redrawing, altered faces, invented details, added borders, stretching, cropping or redesign. Preserve the reference's artwork aspect ratio, orientation and frame proportions; legacy landscape wording applies only to landscape references. Use the framed product, not its surrounding background.
A1 PHYSICAL SCALE: Artwork/paper is 841 mm wide × 594 mm high in landscape, or 594 mm wide × 841 mm high in portrait. This is PAPER/ARTWORK size, not outer-frame size. Preserve actual verified frame/mount specifications and reference proportions. Never describe the outer frame as exactly A1 or invent moulding, mount allowances or depth dimensions. Standard A1 is not a replacement for verified outer-frame measurements. Report conflicting specifications before generation; never force the reference into an A1 ratio. Keep the same physical product size across all three rooms despite perspective/distance. Establish believable A1 scale with sofas, desks, chairs, shelving, doors and wall heights; no oversized mural or tiny print. Realistic hanging height and source-consistent frame depth. Make the artwork prominent through composition, not artificial enlargement, with enough surrounding context to establish scale. No rulers, measurement labels or dimension arrows.
PREMIUM GLAZING: Preserve accurate material claims, including acrylic/Perspex where specified; glass-like reflections are a visual requirement, not a change to manufactured materials. Subtle but visibly believable room-specific window/lamp reflections must follow this room's light sources, camera direction and glazing plane in direction, strength and perspective. Restrained highlights must make the protective glazing perceptible rather than an unglazed matte print. Each room needs its OWN reflection pattern, never a reused overlay or the reference background's lighting. Realistic frame depth, edge highlights, contact shadows and naturally soft wall cast shadows; natural exposure, believable materials and premium interior photography. Keep artwork clear and readable beneath glazing: no opaque white glare, mirror-like surface, artificial glow, fake HDR or plastic texture. Never obscure faces, typography or important details.
OUTPUT: One separate 1024 × 1024 image, retaining any explicitly authored output requirements below. Physical A1 dimensions do not describe the output canvas.'''


def scene_texts(result, current_text, saved_base):
    """A deterministic draw changes defaults only. Authored settings retain authority."""
    import mockup_product_prompts as scenes
    items = {item['filename']: item['prompt'] for item in result.get('final_prompt_items', ())}
    texts = []
    seed = str(result.get('_product_upload_intake') or result.get('run_dir', ''))
    combination=ROOM_COMBINATIONS[int(hashlib.sha256(seed.encode()).hexdigest(),16)%len(ROOM_COMBINATIONS)]
    for index, filename in enumerate(FILENAMES):
        default = items.get(filename, '')
        text = current_text(filename, default)
        # Never rewrite a saved custom room/angle, including old-format overrides.
        if saved_base(filename, scenes.TEMPLATE).strip() == scenes.TEMPLATE.strip():
            draw = combination[index]
            angle=scenes.ANGLES[(combination[0]+index)%len(scenes.ANGLES)]
            scene=(f'{scenes.MARKER}\nSelected room: {ROOMS[index][draw]}\nSelected camera angle: {angle}\n'
                   f'{scenes.ANGLE_GUIDANCE[angle]}\nKeep this resolved room and angle stable in this workflow.\n{scenes.END}')
            text=scenes.SCENE.sub(lambda _:scene,text)
        texts.append(text)
    return texts


def compose(instructions, texts):
    return instructions.strip() + '\n\n' + '\n\n'.join(
        f'{index + 1}. {label}\n{PER_IMAGE}\n\nSaved scene/composition/output requirements:\n{text}'
        for index, (label, text) in enumerate(zip(LABELS, texts)))
