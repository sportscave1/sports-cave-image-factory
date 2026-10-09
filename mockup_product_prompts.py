"""Curated product-page scenes; draw once per generated prompt, never per UI rerun."""
import random
import re

ROOMS = {
    '01-man-cave-prompt.txt': (
        'Modern man cave with pool table',
        'Sports collector room with tasteful display shelving',
        'Luxury media room / entertainment den',
        'Premium garage lounge / workshop retreat',
        'Whiskey lounge / gentleman’s retreat',
    ),
    '02-office-prompt.txt': (
        'Modern home office', 'Executive office', 'Creative studio workspace',
        'Reading study / library nook', 'Minimal work-from-home nook',
    ),
    '03-living-room-prompt.txt': (
        'Minimal living room', 'Luxury apartment lounge', 'Minimal bedroom',
        'Hotel-style bedroom suite', 'Family lounge / relaxed sitting room',
    ),
}
ANGLES = (
    'Straight on',
    'Slightly angled from the left',
    'Slightly angled from the right',
    'Gently elevated from the left',
    'Gently elevated from the right',
)
ANGLE_GUIDANCE = {
    ANGLES[0]: 'Camera level with the centre of the frame, directly front-facing, balanced and clean.',
    ANGLES[1]: 'Position the camera slightly left, approximately 5–8 degrees off-axis; show subtle physical frame depth.',
    ANGLES[2]: 'Position the camera slightly right, approximately 5–8 degrees off-axis; show subtle physical frame depth.',
    ANGLES[3]: 'Position the camera subtly above centre and a little left, within a natural 5–8 degree perspective; keep frame edges complete and readable.',
    ANGLES[4]: 'Position the camera subtly above centre and a little right, within a natural 5–8 degree perspective; keep frame edges complete and readable.',
}
MARKER = 'SPORTS CAVE PRODUCT PAGE SCENE V1'
END = 'END PRODUCT PAGE SCENE'
SCENE = re.compile(re.escape(MARKER) + r'.*?' + re.escape(END), re.S)
TEMPLATE = '''Create a 1024 x 1024 photorealistic ecommerce lifestyle mockup using the supplied framed Sports Cave artwork as the exact reference.
Preserve the supplied artwork and frame exactly: colours, text, badge, layout, complete outer frame and landscape proportions. Do not redesign, crop, blur, stretch, warp or distort the artwork.
Place the frame realistically on a wall at eye level with believable scale, physical mounting, natural contact shadows and restrained glass reflections that do not obscure the artwork.
Keep the framed artwork the clear focal hero. Use a premium, clean, minimal, polished and uncluttered room that supports rather than competes with the product.
Use believable natural light, controlled highlights and realistic material texture. Avoid excessive darkness, noisy props, neon signs, distracting memorabilia, extra wall art, people, text overlays and watermarks.
Use the single selected room and camera direction below. Allow subtle variation in furniture layout, lighting direction, wall material, decor, room proportions and composition within that room style. Preserve editable scene instructions; the selected angle must remain stable after generation or editing.
Keep perspective natural and architectural lines straight. No extreme side angles, awkward perspective, fisheye or independently distorted frame/artwork. The design must remain clearly readable.
The final scene must look like real professional interior photography, not an AI-generated or over-styled room.'''


def build(filename, base=None, *, avoid_angles=()):
    room = random.choice(ROOMS[filename])
    available_angles = tuple(a for a in ANGLES if a not in avoid_angles) or ANGLES
    angle = random.choice(available_angles)
    body = SCENE.sub('', base or TEMPLATE).strip()
    return (
        f'{body}\n\n{MARKER}\nSelected room: {room}\n'
        f'Selected camera angle: {angle}\n{ANGLE_GUIDANCE[angle]}\n'
        'Use only this selected room and angle; they replace any earlier room or '
        'camera direction. Keep the artwork unchanged and the room premium, '
        f'minimal and product-page friendly.\n{END}'
    )


def preserve_selection(override, generated):
    """A stored prompt edit must not erase the run's resolved room/angle choice."""
    scene = SCENE.search(generated)
    if not scene or override == generated:
        return override
    return SCENE.sub('', override).strip() + '\n\n' + scene.group(0)
