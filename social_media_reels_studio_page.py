from __future__ import annotations

import base64
import html
import hashlib
import io
import json
import mimetypes
import re
import shutil
import zipfile
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, UnidentifiedImageError

BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "output" / "runs"
PASTE_COMPONENT_DIR = BASE_DIR / "components" / "reels_image_paste_zone"
PAGE_STATE_KEY = "smrs_state"
IMAGE_UPLOAD_TYPES = ["jpg", "jpeg", "png", "webp"]
MOCKUP_UPLOAD_TYPES = ["png"]
VIDEO_UPLOAD_TYPES = ["mp4"]
PACK_VERSION = "v01"
GENERIC_PRODUCT_HANDLE_PLACEHOLDER = "[PRODUCT HANDLE]"
GENERIC_PRODUCT_TITLE_PLACEHOLDER = "[PRODUCT TITLE]"
GENERIC_SPORT_PLACEHOLDER = "[SPORT]"
GENERIC_PRODUCT_ANGLE_PLACEHOLDER = "[PRODUCT ANGLE]"
FILENAME_HANDLE_PLACEHOLDER = "athlete-name-product-handle"
STATUS_OPTIONS = ["draft", "final", "posted", "ad-test", "winner", "archive"]
SPORT_CATEGORY_OPTIONS = [
    "",
    "Soccer",
    "Basketball",
    "Cricket",
    "Motorsport",
    "Tennis",
    "Combat Sports",
    "Golf",
    "Horse Racing",
    "AFL",
    "Baseball",
    "NFL",
]
WIZARD_FLAG_DEFAULTS = {
    "reels_step_1_complete": False,
    "reels_step_2_complete": False,
    "reels_step_3_complete": False,
    "reels_step_4_complete": False,
    "reels_product_generated": False,
    "reels_background_generated": False,
    "reels_image_prompts_generated": False,
    "reels_video_prompts_generated": False,
}
SPORT_KEYWORDS = (
    ("NFL", ("nfl", "superbowl", "super-bowl", "brady", "mahomes")),
    ("Soccer", ("soccer", "football", "ronaldo", "messi", "mbappe", "neymar", "haaland", "bellingham", "ronaldinho", "zidane")),
    ("Basketball", ("nba", "basketball", "jordan", "bryant", "kobe", "lebron", "curry", "wembanyama", "shaq")),
    ("Cricket", ("cricket", "warne", "bradman", "ponting", "cummins", "lillee")),
    ("Motorsport", ("motorsport", "motor-racing", "racing", "f1", "formula-one", "formula-1", "bathurst", "brock", "moffat", "lowndes", "supercars", "v8")),
    ("Tennis", ("tennis", "federer", "nadal", "djokovic", "alcaraz", "barty")),
    ("Combat Sports", ("ufc", "mma", "boxing", "ali", "tyson", "jones", "gaethje")),
    ("Golf", ("golf", "tiger", "woods", "masters")),
    ("Horse Racing", ("horse", "racing", "melbourne-cup", "black-caviar", "phar-lap")),
    ("AFL", ("afl", "footy", "ben-cousins", "taylor-walker")),
    ("Baseball", ("baseball", "mlb", "ohtani", "judge")),
)

_paste_zone_component = components.declare_component(
    "reels_image_paste_zone",
    path=str(PASTE_COMPONENT_DIR),
)


SCENES = (
    {
        "name": "Person Holding & Admiring",
        "slug": "collector-admire",
        "video_name": "Holding & Admiring - 5s Premium Reel",
        "has_person": True,
        "image_direction": (
            "Create a real everyday customer holding the black framed artwork at chest height, "
            "admiring it with an ownership feel. Hands must sit only on the outside frame edges. "
            "The artwork must remain fully visible. Use the selected premium room as the environment, "
            "with realistic glass, realistic frame weight, natural hand contact, believable scale, "
            "and premium UGC-style customer realism."
        ),
        "video_direction": (
            "A real customer holds and admires the artwork. Tiny breathing, slight hand grip adjustment, "
            "small head movement, slow cinematic push-in, soft glass reflection, realistic shadows."
        ),
    },
    {
        "name": "Person Hanging / Adjusting Frame",
        "slug": "wall-hanging-adjust",
        "video_name": "Hanging / Adjusting - 5s Premium Reel",
        "has_person": True,
        "image_direction": (
            "Create a real everyday customer making the final tiny adjustment after hanging the frame. "
            "Both hands must be on the outer frame edges only. Use a subtle straightening pose, with the "
            "frame mounted at realistic eye-level height, natural wall shadows, premium lighting, and "
            "realistic glass. The moment should feel like premium UGC-style home content."
        ),
        "video_direction": (
            "Customer makes final wall adjustment. Both hands gently straighten the frame, tiny left-right "
            "corrections, hands slowly release, frame settles level, slow push-in, realistic wall shadow, "
            "glass reflection."
        ),
    },
    {
        "name": "Person Standing Back Admiring Wall",
        "slug": "wall-admire",
        "video_name": "Standing Back Admiring - 5s Premium Reel",
        "has_person": True,
        "image_direction": (
            "Create the frame mounted on the wall with a real everyday customer standing a few steps back "
            "admiring it. The customer must not touch the frame, must not block the artwork, and should "
            "communicate quiet pride, ownership, and collector emotion in a natural UGC-style home moment."
        ),
        "video_direction": (
            "Customer stands back admiring the mounted frame. Subtle breathing, tiny head movement, slight "
            "stance shift, slow push-in, emotional pause, soft glass reflection."
        ),
    },
    {
        "name": "Artwork Only On Wall",
        "slug": "wall-only",
        "video_name": "Artwork Only Wall - 5s Premium Reel",
        "has_person": False,
        "image_direction": (
            "Create artwork only, mounted on the wall with no people. Use the selected premium room setting, "
            "realistic A1 or XL wall scale depending on the product, accurate black frame depth, realistic "
            "glass, natural shadows, and premium lighting."
        ),
        "video_direction": (
            "No people. Artwork mounted on wall. Slow push-in, subtle wall shadow shift, soft glass reflection, "
            "ambient light movement, luxury stillness."
        ),
    },
)


IMAGE_PROMPT_OPENING = """Create a 1024 x 1024 ultra-realistic Sports Cave lifestyle mockup using the uploaded references.

Image A is the exact Sports Cave black framed product mockup.
Image B is the selected background/reference room.
Use Image A for the product and Image B for the environment.

The uploaded product artwork is the hero. Preserve it exactly.
The output must look like a real premium Sports Cave lifestyle photograph, not AI.

Where helpful, make the scene feel suited to {product_title} for a {sport_category} collector audience.
Additional VA direction is {creative_notes}."""


IMAGE_PRODUCT_LOCK = """PRODUCT LOCK

Keep the uploaded Sports Cave artwork and black frame exactly the same.

Do not redesign the artwork.
Do not change the athlete, subject, team, colours, text, typography, badge, edition plate, plaque, layout, crop, frame colour, frame shape, or composition inside the frame.
Do not blur, stretch, warp, bend, squash, distort, repaint, redraw, replace, regenerate, or reinterpret the artwork.

The artwork must remain sharp, rectangular, correctly aligned, and physically believable inside the frame."""


IMAGE_PERSON_REALISM_HOLDING = """PERSON REALISM

Add one realistic male customer only.

He should look 30-50 years old.
Natural believable appearance.
Smart casual clothing.
Not model-like.
Realistic skin texture.
Realistic arms and hands.
realistic hands.
Correct number of fingers.
Natural finger placement.
No melted fingers.
No extra fingers.
No warped hands.

He should be looking at the artwork, not the camera.

His posture should show the natural weight of a real framed product.

Hands must hold the outside black frame edges only.
hands must only touch the outer frame edges.
Hands must never cover important artwork details.
Hands must not cover the title, player, badge, edition plate, signature, or main subject."""


IMAGE_PERSON_REALISM_HANGING = """PERSON REALISM

Add one realistic male customer only.

He should look 30-50 years old.
Natural believable appearance.
Smart casual clothing.
Realistic skin texture.
Realistic arms and hands.
realistic hands.
Correct number of fingers.
Natural finger placement.
No melted fingers.
No extra fingers.
No warped hands.
Natural body posture.
Realistic shoulder and arm positioning while holding a heavy frame.

He should be focused on lining up the artwork on the wall, not looking at the camera.

Hands must only touch the outer black frame edges.
hands must only touch the outer frame edges.
Hands must never cover the title, player, badge, edition plate, signature, or main subject."""


IMAGE_PERSON_REALISM_ADMIRE = """PERSON REALISM

Add one realistic male customer only.

He should look 30-50 years old.
Natural believable appearance.
Smart casual clothing.
Realistic skin texture.
realistic hands.
Correct number of fingers.
Realistic body scale.
Natural posture.
Relaxed stance.
Slightly turned toward the artwork.
Not looking at the camera.

No warped limbs.
No extra fingers.
No warped hands.
No distorted body.
No fake model pose.

The person must not block the artwork."""


HUMAN_ANATOMY_LOCK = """HUMAN ANATOMY LOCK:
The scene must contain exactly one real everyday adult customer.
The person must have a physically possible pose with all visible body parts connected naturally.
Both shoulders, upper arms, elbows, forearms, wrists, hands, torso, hips, legs, and feet must align anatomically.
No detached limbs.
No floating hands.
No hands appearing without visible wrists and arms.
No arm emerging from behind the frame unless the full arm connection to the shoulder is clearly visible.
No duplicated arms.
No extra hands.
No missing elbows.
No twisted wrists.
No broken fingers.
No stretched arms.
No rubbery limbs.
No impossible reach across the frame.
No cropped-off body parts that make limbs look disconnected.
No mannequin, model, waxy, or AI-looking body.
Keep the person's pose simple, natural, and believable."""


NEGATIVE_HUMAN_ANATOMY = """NEGATIVE HUMAN ANATOMY:
Do not create detached arms, floating hands, disconnected wrists, duplicate limbs, extra fingers, missing fingers, twisted fingers, broken elbows, impossible shoulders, arms coming from the wrong body position, hands appearing from behind the artwork, cropped limbs, warped anatomy, mannequin body, stock-photo model pose, waxy skin, plastic skin, uncanny face, or AI-looking human proportions."""


HUMAN_ANATOMY_QA_REJECT = """Reject and regenerate if any hand, wrist, forearm, elbow, upper arm, shoulder, leg, foot, head, or torso is detached, duplicated, warped, hidden in an impossible way, or not physically connected to the same person."""


WALL_HANGING_SAFE_POSE = """A single customer stands centered in front of the frame, back or three-quarter back view, with full torso and both shoulders visible. Both arms are visible and naturally connected from shoulder to hand. The customer lightly holds the left and right outer edges of the frame with both hands while making a tiny final straightening adjustment. Elbows are slightly bent. Wrists and fingers are normal. The hands touch only the outer frame edges and do not cover important artwork details. The pose must be physically possible and natural."""


IMAGE_GLASS_REALISM = """GLASS REALISM

Add ultra-realistic museum-quality glass over the artwork.

The glass should have soft natural room reflections.
Use subtle premium glare only.
The glare must never hide or ruin the artwork.
The artwork must remain sharp and readable."""


IMAGE_ROOM_REALISM = """ROOM REALISM

Use the selected background/reference room as the base environment.

The room must remain realistic, premium, and believable.

Do not distort walls, furniture, lamps, sofas, curtains, shelves, floors, or architecture.
No warped walls.
No impossible furniture.
No random logos.
No fake trophies.
No clutter.
No messy room.
No obvious AI room.
No neon signs unless extremely subtle and already suited to the background.
No extra wall art competing with the product.

The framed artwork must look mounted, held, or placed naturally in the room, not pasted on."""


VIDEO_PROMPT_OPENING = """Create an ultra-realistic 5 second cinematic lifestyle video from this exact image.

This is a premium Sports Cave advertisement.

The uploaded Sports Cave artwork and black timber frame are the hero and MUST remain EXACTLY the same.

NON-NEGOTIABLE:

Do NOT regenerate the artwork.
Do NOT redraw the artwork.
Do NOT alter the colours.
Do NOT alter the typography.
Do NOT alter the badge.
Do NOT alter the edition plate.
Do NOT blur the artwork.
Do NOT crop the artwork.
Do NOT stretch, warp, bend or distort the frame.
Do NOT change the proportions.
Do NOT replace any part of the frame or artwork.
Do NOT change the room from the uploaded still image.
Do NOT add fake logos.
Do NOT add fake readable text.
{people_rule}
Do NOT make the frame float.
Do NOT create AI shimmer or flickering.

The artwork must stay razor sharp throughout the entire video."""


VIDEO_CAMERA_BLOCK = """CAMERA

Professional cinema camera.

50mm lens.

Slow cinematic push-in.

Extremely subtle handheld micro movement.

Natural focus breathing.

No dramatic camera movement.

No spinning.

No zoom effects.

No cinematic gimmicks."""


VIDEO_GLASS_BLOCK = """GLASS

Ultra-realistic museum glass.

Very soft moving reflections.

Natural ambient reflections only.

Subtle premium glare moving across the glass.

Reflections must never hide the artwork."""


VIDEO_OUTPUT_BLOCK = """OUTPUT

9:16 vertical.

5 seconds.

Photorealistic.

4K quality.

Smooth natural motion.

Luxury commercial quality.

Meta Ads ready.

Indistinguishable from a professionally filmed product commercial."""


VIDEO_PROMPTS_BY_SCENE = {
    "collector-admire": f"""{VIDEO_PROMPT_OPENING.format(people_rule="Do NOT add extra people.")}

SCENE

A lifelong sports collector stands inside his dream Sports Cave or premium collector room.

Use the existing room from the uploaded still image.
The existing room from the uploaded still image must remain the same. Do not remodel the room. Do not add new major furniture, new wall art, random memorabilia, fake trophies, or extra logos. Only add subtle natural motion, light movement, reflections, and realistic human micro-movement if a person is already part of the scene.
The room must remain authentic, premium and believable.
Do not remodel the room.
Do not add new major furniture.
Do not add random memorabilia.
Do not add fake trophies.
Do not add extra wall art competing with the product.

The collector is holding the framed artwork naturally with both hands at chest height.

He slowly studies the artwork with genuine admiration.

He is imagining exactly where it will go in his collection.

The artwork is always fully visible.

His hands never cover important parts of the design, badge, title, edition plate, player, signature or frame.

{VIDEO_CAMERA_BLOCK}

MOVEMENT

Very small natural breathing.

Tiny shifts in body weight.

Slight movement of wrists while supporting the frame.

Tiny movement in fingers from the weight of the frame.

Natural blink.

Very subtle head movement while admiring the artwork.

Nothing exaggerated.

FRAME REALISM

Premium matte black timber frame.

Realistic frame depth.

Sharp corners.

Museum-quality glass.

Natural weight in the collector's hands.

Perfect landscape proportions.

The frame must never wobble unnaturally.

{VIDEO_GLASS_BLOCK}

LIGHTING

Warm cinematic lighting.

Natural window fill if present in the still image.

Soft LED or lamp glow if present in the still image.

Realistic shadows.

Natural shadow movement.

Soft ambient bounce light.

The lighting should feel like a luxury home, not a studio.

BACKGROUND

Everything behind the artwork remains softly out of focus.

The Sports Cave feels expensive, authentic and collector owned.

No clutter.

No fake trophies.

No distorted memorabilia.

No random sports logos.

No extra wall art competing with the product.

ENDING

The collector pauses.

Looks proudly at the artwork.

Small smile of satisfaction.

Camera settles on the framed artwork.

Hold for one second.

The viewer should immediately imagine this exact piece becoming the centrepiece of their own Sports Cave.

{VIDEO_OUTPUT_BLOCK}""",
    "wall-hanging-adjust": f"""{VIDEO_PROMPT_OPENING.format(people_rule="Do NOT add extra people.")}

SCENE

A lifelong sports collector is making the final adjustment after hanging his Sports Cave framed artwork on the wall.

Use the existing room from the uploaded still image.
The existing room from the uploaded still image must remain the same. Do not remodel the room. Do not add new major furniture, new wall art, random memorabilia, fake trophies, or extra logos. Only add subtle natural motion, light movement, reflections, and realistic human micro-movement if a person is already part of the scene.
The room must remain the same.
Do not remodel the room.
Do not add new furniture, fake trophies, random memorabilia, random sports logos or extra wall art.

The framed artwork is already mounted on the wall.

The collector gently holds the outside edges of the frame and carefully straightens it.

The movement feels real, slow and controlled.

The artwork is always fully visible.

Hands only touch the outer frame edges.

Hands never cover the title, badge, edition plate, player, signature or main artwork details.

{VIDEO_CAMERA_BLOCK}

MOVEMENT

Both hands gently straighten the frame.

Tiny left-right correction.

Small final level adjustment.

Hands slowly release.

The frame settles perfectly level on the wall.

The collector's hands move out of frame naturally or relax by his side.

Nothing exaggerated.

No sudden movements.

FRAME REALISM

Premium matte black timber frame.

Realistic frame depth.

Sharp corners.

Museum-quality glass.

Perfect landscape proportions.

The frame must feel physically mounted to the wall.

The frame must never float.

The frame must never wobble unnaturally.

{VIDEO_GLASS_BLOCK}

LIGHTING

Warm cinematic lighting.

Natural window fill if present in the still image.

Soft LED or lamp glow if present in the still image.

Realistic shadows.

Subtle wall shadow behind the frame.

Natural shadow movement from the hands and frame.

Soft ambient bounce light.

The lighting should feel like a luxury home, not a studio.

BACKGROUND

The existing room remains softly cinematic and believable.

No clutter.

No fake trophies.

No distorted memorabilia.

No random sports logos.

No extra wall art competing with the product.

The artwork remains the clear hero.

ENDING

The frame is perfectly level.

The collector releases it.

Camera settles on the framed artwork.

Hold for one second.

It should feel like the final moment after installing a limited-edition collector piece in a dream Sports Cave.

{VIDEO_OUTPUT_BLOCK}""",
    "wall-admire": f"""{VIDEO_PROMPT_OPENING.format(people_rule="Do NOT add extra people.")}

SCENE

A lifelong sports collector stands a few steps back inside his dream Sports Cave or premium collector room.

The framed Sports Cave artwork is already mounted on the wall.

Use the existing room from the uploaded still image.
The existing room from the uploaded still image must remain the same. Do not remodel the room. Do not add new major furniture, new wall art, random memorabilia, fake trophies, or extra logos. Only add subtle natural motion, light movement, reflections, and realistic human micro-movement if a person is already part of the scene.
The room must remain the same.
Do not remodel the room.
Do not add new furniture, fake trophies, random memorabilia, random sports logos or extra wall art.

The collector quietly admires the finished wall.

He is not touching the frame.

He looks at the artwork with pride, nostalgia and satisfaction.

The artwork is always fully visible and remains the hero.

{VIDEO_CAMERA_BLOCK}

MOVEMENT

Very small natural breathing.

Tiny shift in stance.

Subtle head movement while looking at the artwork.

Natural blink.

Small emotional pause.

Optional small satisfied smile.

Nothing exaggerated.

No pointing.

No dramatic gestures.

FRAME REALISM

Premium matte black timber frame.

Realistic frame depth.

Sharp corners.

Museum-quality glass.

Perfect landscape proportions.

The frame must feel physically mounted to the wall.

The frame must never float.

The frame must never wobble or distort.

{VIDEO_GLASS_BLOCK}

LIGHTING

Warm cinematic lighting.

Natural window fill if present in the still image.

Soft LED or lamp glow if present in the still image.

Realistic shadows.

Subtle wall shadow behind the frame.

Natural shadow movement.

Soft ambient bounce light.

The lighting should feel like a luxury home, not a studio.

BACKGROUND

Everything behind the artwork remains premium, softly cinematic and believable.

No clutter.

No fake trophies.

No distorted memorabilia.

No random sports logos.

No extra wall art competing with the product.

The Sports Cave feels expensive, authentic and collector owned.

ENDING

The collector pauses and keeps admiring the piece.

Camera settles on the framed artwork.

Hold for one second.

The viewer should immediately imagine this exact artwork hanging in their own Sports Cave.

{VIDEO_OUTPUT_BLOCK}""",
    "wall-only": f"""{VIDEO_PROMPT_OPENING.format(people_rule="Do NOT add people.")}

SCENE

The framed Sports Cave artwork is mounted on the wall inside a premium Sports Cave, collector room, man cave, lounge, office or private retreat.

Use the existing room from the uploaded still image.
The existing room from the uploaded still image must remain the same. Do not remodel the room. Do not add new major furniture, new wall art, random memorabilia, fake trophies, or extra logos. Only add subtle natural motion, light movement, reflections, and realistic human micro-movement if a person is already part of the scene.
The room must remain the same.
Do not remodel the room.
Do not add new furniture.
Do not add fake trophies.
Do not add random memorabilia.
Do not add random sports logos.
Do not add extra wall art.

No people.

The artwork is the centrepiece.

The video should feel like a luxury product reveal after the piece has just been installed.

{VIDEO_CAMERA_BLOCK}

MOVEMENT

No movement inside the artwork.

No movement of the frame.

No people entering.

Only subtle environmental motion:
soft ambient light shift,
tiny natural shadow movement,
very soft glass reflection movement,
luxury stillness.

FRAME REALISM

Premium matte black timber frame.

Realistic frame depth.

Sharp corners.

Museum-quality glass.

Perfect landscape proportions.

The frame must feel physically mounted to the wall.

The frame must never float.

The frame must never wobble or distort.

{VIDEO_GLASS_BLOCK}

LIGHTING

Warm cinematic lighting.

Natural window fill if present in the still image.

Soft LED or lamp glow if present in the still image.

Realistic shadows.

Subtle wall shadow behind the frame.

Natural shadow movement.

Soft ambient bounce light.

The lighting should feel like a luxury home, not a studio.

BACKGROUND

Everything around the artwork remains premium, softly cinematic and believable.

No clutter.

No fake trophies.

No distorted memorabilia.

No random sports logos.

No extra wall art competing with the product.

The Sports Cave feels expensive, authentic and collector owned.

ENDING

Camera settles on the framed artwork.

Hold for one second.

The viewer should immediately imagine this exact piece becoming the centrepiece of their own Sports Cave.

{VIDEO_OUTPUT_BLOCK}""",
}


def sanitize_handle(value: str, fallback: str = "") -> str:
    slug = str(value or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or fallback


def strip_trailing_random_id(slug: str) -> str:
    cleaned = sanitize_handle(slug)
    cleaned = re.sub(
        r"-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    while True:
        trimmed = re.sub(r"-[0-9a-f]{10,}$", "", cleaned, flags=re.IGNORECASE)
        trimmed = re.sub(r"-[a-z0-9]{16,}$", "", trimmed, flags=re.IGNORECASE)
        if trimmed == cleaned:
            break
        cleaned = trimmed
    return cleaned.strip("-")


def title_from_handle(product_handle: str) -> str:
    words = []
    for part in sanitize_handle(product_handle).split("-"):
        if not part:
            continue
        if part in {"f1", "v8", "nba", "nfl", "afl", "ufc", "mma", "mlb"}:
            words.append(part.upper())
        else:
            words.append(part.capitalize())
    return " ".join(words)


def detect_sport_category(value: str) -> str:
    handle = sanitize_handle(value)
    padded = f"-{handle}-"
    for sport, keywords in SPORT_KEYWORDS:
        for keyword in keywords:
            if f"-{sanitize_handle(keyword)}-" in padded:
                return sport
    return ""


def derive_product_details_from_filename(filename: str) -> dict[str, str]:
    stem = Path(str(filename or "")).stem
    product_handle = strip_trailing_random_id(stem)
    product_handle = sanitize_handle(product_handle)
    return {
        "product_handle": product_handle,
        "product_title": title_from_handle(product_handle),
        "sport_category": detect_sport_category(product_handle),
    }


def derive_product_details_from_asset(asset: dict | None) -> dict[str, str]:
    if not asset:
        return {"product_handle": "", "product_title": "", "sport_category": ""}
    filename = asset.get("original_name") or asset.get("filename") or ""
    details = derive_product_details_from_filename(filename)
    is_generated_paste_name = asset.get("source") in {"paste", "drop"} and "pasted" in sanitize_handle(filename)
    if is_generated_paste_name and sanitize_handle(filename).startswith("sports-cave"):
        return {
            "product_handle": "pasted-product-mockup",
            "product_title": "Pasted Product Mockup",
            "sport_category": "",
        }
    return details


def suggest_handle_from_filename(filename: str) -> str:
    return derive_product_details_from_filename(filename)["product_handle"]


def wizard_unlocks(flags: dict) -> dict[str, bool]:
    flags = flags or {}
    return {
        "step_1": True,
        "step_2": bool(flags.get("reels_step_1_complete")),
        "step_3": bool(flags.get("reels_step_2_complete")),
        "step_4": bool(flags.get("reels_step_3_complete")),
        "step_5": bool(flags.get("reels_step_4_complete")),
    }


def mime_type_from_filename(filename: str, fallback: str = "image/png") -> str:
    guessed, _ = mimetypes.guess_type(str(filename or ""))
    if guessed in {"image/png", "image/jpeg", "image/webp"}:
        return guessed
    suffix = Path(str(filename or "")).suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    if suffix == ".png":
        return "image/png"
    return fallback


def extension_from_mime(mime_type: str, fallback: str = ".png") -> str:
    mime_type = str(mime_type or "").lower()
    if mime_type == "image/jpeg":
        return ".jpg"
    if mime_type == "image/webp":
        return ".webp"
    if mime_type == "image/png":
        return ".png"
    return fallback


def format_file_size(size_bytes: int | None) -> str:
    size = int(size_bytes or 0)
    if size >= 1024 * 1024:
        return f"{size / 1024 / 1024:.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def generated_pasted_filename(product_handle: str, asset_type: str, scene_slug: str = "", mime_type: str = "image/png") -> str:
    handle = sanitize_handle(product_handle, "sports-cave")
    clean_asset_type = sanitize_handle(asset_type, "image")
    ext = extension_from_mime(mime_type, ".png")
    parts = [handle, clean_asset_type]
    if scene_slug:
        parts.append(sanitize_handle(scene_slug, "scene"))
    parts.extend(["pasted", "v01"])
    return "__".join(parts) + ext


def _image_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image.size
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None


def image_asset_from_bytes(
    image_bytes: bytes,
    filename: str,
    mime_type: str = "",
    source: str = "upload",
) -> dict:
    data = bytes(image_bytes or b"")
    safe_filename = Path(sanitize_handle(Path(filename or "image").stem, "image")).with_suffix(
        Path(filename or "").suffix.lower() or extension_from_mime(mime_type)
    ).name
    resolved_mime = mime_type or mime_type_from_filename(safe_filename)
    width, height = _image_dimensions(data)
    return {
        "filename": filename or safe_filename,
        "safe_filename": safe_filename,
        "mime_type": resolved_mime,
        "bytes": data,
        "source": source if source in {"upload", "paste", "drop"} else "upload",
        "width": width,
        "height": height,
        "size_bytes": len(data),
        "created_at": _now_iso(),
    }


def image_asset_from_uploaded_file(uploaded_file, source: str = "upload") -> dict:
    uploaded_file.seek(0)
    data = uploaded_file.read()
    uploaded_file.seek(0)
    return image_asset_from_bytes(
        data,
        getattr(uploaded_file, "name", "uploaded-image.png"),
        mime_type_from_filename(getattr(uploaded_file, "name", "")),
        source=source,
    )


def image_asset_from_paste_payload(payload: dict | None, product_handle: str, asset_type: str, scene_slug: str = "") -> dict | None:
    if not isinstance(payload, dict):
        return None
    data_base64 = str(payload.get("data_base64") or "").strip()
    if not data_base64:
        return None
    if "," in data_base64 and data_base64.lower().startswith("data:"):
        data_base64 = data_base64.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(data_base64, validate=False)
    except (ValueError, TypeError):
        return None
    mime_type = str(payload.get("mime") or payload.get("mime_type") or "image/png")
    filename = str(payload.get("filename") or "").strip()
    if not filename or filename.lower() in {"image.png", "clipboard.png", "pasted-image.png"}:
        filename = generated_pasted_filename(product_handle, asset_type, scene_slug, mime_type)
    source = str(payload.get("source") or "paste").strip().lower()
    return image_asset_from_bytes(image_bytes, filename, mime_type, source=source)


def _asset_bytes(asset: dict | None) -> bytes:
    if not asset:
        return b""
    data = asset.get("bytes")
    if isinstance(data, bytes):
        return data
    if isinstance(data, bytearray):
        return bytes(data)
    path = Path(asset.get("path", ""))
    if path.exists() and path.is_file():
        return path.read_bytes()
    return b""


def has_valid_image_asset(asset: dict | None) -> bool:
    if not asset:
        return False
    image_bytes = _asset_bytes(asset)
    mime_type = str(asset.get("mime_type") or mime_type_from_filename(asset.get("filename", ""))).lower()
    width = asset.get("width")
    height = asset.get("height")
    return bool(
        image_bytes
        and mime_type.startswith("image/")
        and isinstance(width, int)
        and isinstance(height, int)
        and width > 0
        and height > 0
    )


def has_any_valid_image_asset(records: dict | None) -> bool:
    return any(has_valid_image_asset(asset) for asset in (records or {}).values())


def _sync_wizard_completion_from_assets(state: dict) -> None:
    files = state.get("files", {})
    product_complete = has_valid_image_asset(files.get("product_mockup"))
    background_complete = has_valid_image_asset(files.get("selected_background"))
    mockups_complete = has_any_valid_image_asset(files.get("image_mockups"))
    videos_complete = bool(files.get("videos"))

    st.session_state["reels_step_1_complete"] = product_complete
    st.session_state["reels_step_2_complete"] = background_complete
    st.session_state["reels_step_3_complete"] = mockups_complete
    st.session_state["reels_step_4_complete"] = videos_complete
    st.session_state["reels_background_generated"] = background_complete
    st.session_state["reels_image_prompts_generated"] = background_complete
    st.session_state["reels_video_prompts_generated"] = mockups_complete


def image_mockup_filename(product_handle: str, scene_slug: str) -> str:
    return f"{sanitize_handle(product_handle, 'product')}__mockup__{scene_slug}__1x1__v01__final.png"


def image_mockup_filename_with_meta(product_handle: str, scene_slug: str, version: str = "v01", status: str = "final") -> str:
    clean_version = sanitize_version(version)
    clean_status = sanitize_status(status)
    return (
        f"{sanitize_handle(product_handle, FILENAME_HANDLE_PLACEHOLDER)}__mockup__{scene_slug}"
        f"__1x1__{clean_version}__{clean_status}.png"
    )


def video_filename(product_handle: str, scene_slug: str, version: str = "v01", status: str = "final") -> str:
    clean_version = sanitize_version(version)
    clean_status = sanitize_status(status)
    return (
        f"{sanitize_handle(product_handle, 'product')}__meta-reel__{scene_slug}"
        f"__9x16__{clean_version}__{clean_status}.mp4"
    )


def sanitize_version(value: str) -> str:
    text = str(value or "").strip().lower()
    match = re.search(r"(\d+)", text)
    if not match:
        return "v01"
    return f"v{int(match.group(1)):02d}"


def next_version(value: str) -> str:
    current = sanitize_version(value)
    number = int(current[1:]) + 1
    return f"v{number:02d}"


def sanitize_status(value: str) -> str:
    status = sanitize_handle(value, "final")
    return status if status in STATUS_OPTIONS else "final"


def build_background_finder_prompt(product_handle: str, product_title: str, sport_category: str, creative_notes: str) -> str:
    product_handle = sanitize_handle(product_handle, "product-handle")
    product_title = str(product_title or "").strip() or "Untitled Sports Cave product"
    sport_category = str(sport_category or "").strip() or "sport"
    creative_notes = str(creative_notes or "").strip() or "No extra creative notes supplied."
    creative_context = ""
    if creative_notes != "No extra creative notes supplied.":
        creative_context = f"\n\nAdditional creative direction from the VA: {creative_notes}"
    return f"""Act as the premium creative director for Sports Cave.

Use the uploaded black framed Sports Cave product mockup as the product reference.
Analyse the uploaded product image directly instead of relying on product metadata.
Use the supplied image, not a screenshot or compressed preview.{creative_context}

Your job is to find the perfect background / room reference for social media reel content and lifestyle mockups for this exact product.

Analyse the uploaded artwork carefully:
- sport
- athlete/team/moment
- artwork colours
- mood
- energy
- room style that would make this product feel premium
- likely buyer identity
- best collector-room environment

Search the web for realistic room/background ideas that would suit this product.
Look for backgrounds that would work as a realistic base image for placing this framed Sports Cave artwork into the scene.

Give me multiple strong background directions, including:
- luxury {sport_category} collector room
- premium {sport_category} man cave
- minimal {sport_category} living room
- dark cinematic collector room
- modern neutral lounge
- home office / study
- sports bar room
- trophy room
- bedroom/private retreat
- hallway/entry statement wall
- fireplace wall
- home gym if relevant
- garage/workshop only if sport is motorsport
- clean close-up wall setup

For each background option, provide:
1. Room style name
2. Why it suits this artwork
3. Best mood for Meta ads
4. Colour fit with the artwork
5. What to avoid
6. Suggested image search phrase
7. Whether it suits:
   - person holding/admires artwork
   - person hanging/adjusting artwork
   - person standing back admiring wall
   - artwork-only wall mockup
8. Score out of 10

Then choose the top 3 best background options and tell me which one is the best overall.

Prioritise:
- premium realism
- believable scale
- masculine collector appeal
- dark/warm Sports Cave feeling
- luxury sports memorabilia styling
- colours that blend naturally with the artwork
- room references that make the frame look real, not pasted on

Avoid:
- messy rooms
- cheap-looking rooms
- obvious AI rooms
- clutter
- neon signs unless very subtle
- random sports logos
- fake trophies
- distorted architecture
- busy backgrounds that compete with the artwork
- rooms where the frame placement would look unrealistic

Return the answer as a clean carousel/list of background options I can choose from.

Do not generate the mockup yet.
Only help me choose the best background/reference room for this product."""


def build_image_prompt(scene: dict, product_handle: str, product_title: str, sport_category: str, creative_notes: str) -> str:
    product_title = str(product_title or "").strip() or "the uploaded Sports Cave product"
    sport_category = str(sport_category or "").strip() or "sports"
    creative_notes = str(creative_notes or "").strip() or "No extra creative notes supplied."
    opening = IMAGE_PROMPT_OPENING.format(
        product_title=product_title,
        sport_category=sport_category,
        creative_notes=creative_notes,
    )
    slug = scene.get("slug")

    if slug == "collector-admire":
        return f"""{opening}

{IMAGE_PRODUCT_LOCK}

SCENE

Create a premium Sports Cave lifestyle scene inside the selected background/reference room.

A lifelong {sport_category} collector is holding the framed artwork naturally with both hands at chest height.

He is admiring the artwork before deciding where to hang it in his Sports Cave.

The moment should feel authentic, quiet, proud, and collector-driven.

The room should feel masculine, premium, warm, and believable.

Use the selected background as the base environment.
Keep the background restrained and realistic.

{IMAGE_PERSON_REALISM_HOLDING}

{HUMAN_ANATOMY_LOCK}

{NEGATIVE_HUMAN_ANATOMY}

{HUMAN_ANATOMY_QA_REJECT}

FRAME REALISM

The black frame must look like a real premium framed product:
- premium matte black timber frame
- realistic timber or frame depth
- sharp square mitred corners
- subtle frame texture
- accurate landscape proportions
- believable thickness
- realistic physical weight in the hands
- natural pressure where hands touch the frame
- realistic contact shadows around the fingers
- frame edges remain perfectly straight
- no bending
- no wobbling
- no rubbery frame
- no pasted-on look
- no floating frame

GLASS REALISM

Add ultra-realistic museum-quality glass over the artwork.

The glass should have soft natural reflections from the room.
Use subtle premium glare only.
The glare must never hide or ruin the artwork.
The artwork must remain sharp and readable.

ROOM REALISM

Use the selected background/reference room as the base.

The room must remain realistic, premium, and believable.

Do not distort walls, furniture, lamps, sofas, curtains, shelves, floors, or architecture.
No warped walls.
No impossible furniture.
No random logos.
No fake trophies.
No clutter.
No messy room.
No obvious AI room.
No extra wall art competing with the product.

The scene should feel like a real customer has just received the framed Sports Cave artwork and is about to place it in his dream room.

LIGHTING

Use premium cinematic lighting.

Soft natural light.
Warm interior glow.
Controlled highlights.
Realistic shadows.
Soft ambient bounce light.
Subtle reflection on glass.
The lighting should feel like a luxury home, not a studio.

COMPOSITION

Square 1024 x 1024 canvas.

The framed artwork is the hero.

Show the full artwork and full frame clearly.
Show believable scale.
Use a professional DSLR / 50mm lens look.
Slight natural viewing angle is allowed, but the frame and artwork must keep correct landscape proportions.
The person should support the artwork naturally without blocking it.

NEGATIVE RULES

Do not add text overlays.
Do not add watermarks.
Do not add fake logos.
Do not add extra people.
Do not add random sports branding.
Do not make the room cluttered.
Do not make the person look AI.
Do not make the hands distorted.
Do not make the frame float.
Do not make the frame glossy, cartoon, CGI, rubbery, warped, or fake.

FINAL RESULT

Photorealistic premium Sports Cave collector-room mockup with a realistic customer holding the exact uploaded framed artwork, perfect frame realism, realistic hands, museum glass, premium shadows, and believable lighting."""

    if slug == "wall-hanging-adjust":
        return f"""{opening}

{IMAGE_PRODUCT_LOCK}

SCENE

Create a premium Sports Cave installation scene inside the selected background/reference room.

A lifelong {sport_category} collector is holding the framed artwork up against the wall and is about to hang it or make the final adjustment.

This should feel like the real moment just before the artwork becomes the centrepiece of his Sports Cave.

The frame is close to the wall at realistic eye-level height.

{WALL_HANGING_SAFE_POSE}

The artwork must be fully visible.

{IMAGE_PERSON_REALISM_HANGING}

{HUMAN_ANATOMY_LOCK}

{NEGATIVE_HUMAN_ANATOMY}

{HUMAN_ANATOMY_QA_REJECT}

FRAME REALISM

The black frame must look like a real premium framed product:
- premium matte black timber frame
- realistic timber or frame depth
- sharp square mitred corners
- subtle frame texture
- accurate landscape proportions
- believable thickness
- realistic physical weight
- realistic pressure where hands hold the frame
- realistic contact shadow between the frame and hands
- realistic near-wall shadow behind the frame
- believable gap or contact point near the wall
- frame must feel physically held and about to be mounted
- no floating frame
- no warped frame
- no bent corners
- no rubbery edges
- no pasted-on look

GLASS REALISM

Add ultra-realistic museum-quality glass over the artwork.

The glass should show soft room reflections.
Use subtle controlled glare only.
The glare must never hide the artwork.
The artwork must stay sharp, readable, and undistorted.

ROOM REALISM

Use the selected background/reference room as the base environment.

The wall must look physically real.
The frame must sit naturally against or close to the wall.
The wall shadow must match the light direction.

Do not distort walls, furniture, lamps, sofas, curtains, shelves, floors, or architecture.
No warped walls.
No impossible furniture.
No random logos.
No fake trophies.
No clutter.
No messy room.
No obvious AI room.
No extra wall art competing with the product.

LIGHTING

Use premium cinematic lighting.

Soft natural light.
Warm room glow.
Controlled highlights.
Realistic shadows behind the frame and person.
Soft ambient bounce light.
Subtle glass reflection.
Luxury home atmosphere, not a studio.

COMPOSITION

Square 1024 x 1024 canvas.

The framed artwork is the hero.

Show full frame and full artwork.
Show believable human scale.
Place the frame at realistic eye-level wall height.
Use a professional DSLR / 50mm lens look.
A slight natural angle is allowed, but frame proportions must stay correct.
The scene should be close enough to feel personal but wide enough to show the room and installation moment.

NEGATIVE RULES

Do not add text overlays.
Do not add watermarks.
Do not add fake logos.
Do not add extra people.
Do not add random sports branding.
Do not make the person look AI.
Do not make the hands distorted.
Do not make the frame float.
Do not make the frame bend.
Do not cover the artwork.
Do not make it CGI, cartoon, glossy, fake, or over-staged.

FINAL RESULT

Photorealistic premium Sports Cave installation mockup showing a realistic customer holding the exact uploaded framed artwork against the wall, about to hang it, with perfect frame realism, natural hands, museum glass, realistic wall shadows, and believable luxury-room lighting."""

    if slug == "wall-admire":
        return f"""{opening}

{IMAGE_PRODUCT_LOCK}

SCENE

Create a premium Sports Cave lifestyle scene inside the selected background/reference room.

The exact framed artwork is already mounted cleanly on the wall.

A lifelong {sport_category} collector stands a few steps back, admiring the finished wall.

He is not touching the frame.

He is looking at the artwork with pride, nostalgia, and satisfaction.

The room should feel like a real collector-owned Sports Cave, not a staged showroom.

{IMAGE_PERSON_REALISM_ADMIRE}

{HUMAN_ANATOMY_LOCK}

{NEGATIVE_HUMAN_ANATOMY}

{HUMAN_ANATOMY_QA_REJECT}

FRAME REALISM

The black frame must look like a real premium framed product mounted on the wall:
- premium matte black timber frame
- realistic timber or frame depth
- sharp square mitred corners
- subtle frame texture
- accurate landscape proportions
- believable thickness
- perfectly straight edges
- realistic wall mounting
- realistic wall shadow behind and below the frame
- believable scale relative to the person and room
- no floating frame
- no warped frame
- no bent edges
- no pasted-on look

GLASS REALISM

Add ultra-realistic museum-quality glass over the artwork.

The glass should have soft natural room reflections.
Use subtle premium glare only.
The glare must never hide the artwork.
The artwork must remain sharp and readable.

ROOM REALISM

Use the selected background/reference room as the base environment.

The room must remain realistic, premium, and believable.

Do not distort walls, furniture, lamps, sofas, curtains, shelves, floors, or architecture.
No warped walls.
No impossible furniture.
No random logos.
No fake trophies.
No clutter.
No messy room.
No obvious AI room.
No extra wall art competing with the product.

The artwork should feel naturally installed as the centrepiece of the room.

LIGHTING

Use premium cinematic lighting.

Soft natural light.
Warm room glow.
Controlled highlights.
Realistic wall shadows behind the frame.
Soft ambient bounce light.
Subtle glass reflection.
Luxury home atmosphere.

COMPOSITION

Square 1024 x 1024 canvas.

The framed artwork is the hero.

Show the full frame and full artwork.
Show believable scale relative to the person.
Place the frame at realistic eye-level height.
Use a professional DSLR / 50mm lens look.
The person should add emotional ownership without overpowering the product.

NEGATIVE RULES

Do not add text overlays.
Do not add watermarks.
Do not add fake logos.
Do not add extra people.
Do not add random sports branding.
Do not make the person look AI.
Do not distort the room.
Do not make the frame float.
Do not make the frame look pasted on.
Do not make the frame glossy, cartoon, CGI, rubbery, warped, or fake.

FINAL RESULT

Photorealistic premium Sports Cave lifestyle mockup showing the exact uploaded framed artwork mounted on the wall with a realistic collector standing back admiring it, perfect frame realism, museum glass, premium wall shadows, believable room scale, and cinematic lighting."""

    return f"""{opening}

{IMAGE_PRODUCT_LOCK}

SCENE

Create a premium Sports Cave wall mockup inside the selected background/reference room.

No people.

The exact framed artwork is mounted cleanly on the wall as the centrepiece of the room.

The room should feel masculine, premium, minimal, warm, collector-driven, and believable.

Use the selected background as the base environment.
Keep the room restrained and realistic.

FRAME REALISM

The black frame must look like a real premium framed product mounted on the wall:
- premium matte black timber frame
- realistic timber or frame depth
- sharp square mitred corners
- subtle frame texture
- accurate landscape proportions
- believable thickness
- perfectly straight edges
- realistic wall mounting
- believable contact with the wall
- realistic wall shadow behind and below the frame
- accurate perspective
- correct scale relative to the room
- no floating frame
- no warped frame
- no bent edges
- no rubbery frame
- no pasted-on look

GLASS REALISM

Add ultra-realistic museum-quality glass over the artwork.

The glass should have soft natural room reflections.
Use subtle premium glare only.
The glare must never hide or ruin the artwork.
The artwork must remain sharp, readable, and undistorted.

ROOM REALISM

Use the selected background/reference room as the base environment.

The room must remain realistic, premium, and believable.

Do not distort walls, furniture, lamps, sofas, curtains, shelves, floors, or architecture.
No warped walls.
No impossible furniture.
No random logos.
No fake trophies.
No clutter.
No messy room.
No obvious AI room.
No neon signs unless extremely subtle and already suited to the background.
No extra wall art competing with the product.

The artwork should look physically mounted, not pasted on.

LIGHTING

Use premium cinematic lighting.

Soft natural light.
Warm interior glow.
Controlled highlights.
Realistic shadow falloff behind and below the frame.
Soft ambient bounce light.
Subtle glass reflection.
The lighting should feel like a luxury home, not a studio.

COMPOSITION

Square 1024 x 1024 canvas.

The framed artwork is the hero.

Show the full frame and full artwork.
Place it at realistic eye-level height.
Show believable scale.
Use a professional DSLR / 50mm lens look.
Slight natural viewing angle is allowed, but frame and artwork proportions must stay correct.
Keep the background minimal and premium.

NEGATIVE RULES

Do not add people.
Do not add text overlays.
Do not add watermarks.
Do not add fake logos.
Do not add random sports branding.
Do not add fake trophies.
Do not add extra wall art.
Do not add clutter.
Do not distort the room.
Do not make the frame float.
Do not make the frame look pasted on.
Do not make it CGI, cartoon, glossy, fake, or over-staged.

FINAL RESULT

Photorealistic premium Sports Cave wall mockup showing the exact uploaded framed artwork mounted naturally in the selected room, with perfect black frame realism, museum glass, realistic shadows, believable wall mounting, premium lighting, and no people."""


def build_video_prompt(scene: dict, product_handle: str, product_title: str, sport_category: str, version: str = "v01", status: str = "final") -> str:
    return VIDEO_PROMPTS_BY_SCENE.get(scene.get("slug"), VIDEO_PROMPTS_BY_SCENE["wall-only"])


def build_image_prompts(product_handle: str, product_title: str, sport_category: str, creative_notes: str) -> dict[str, str]:
    return {
        scene["slug"]: build_image_prompt(scene, product_handle, product_title, sport_category, creative_notes)
        for scene in SCENES
    }


def build_video_prompts(product_handle: str, product_title: str, sport_category: str, video_meta: dict[str, dict] | None = None) -> dict[str, str]:
    video_meta = video_meta or {}
    prompts = {}
    for scene in SCENES:
        meta = video_meta.get(scene["slug"], {})
        prompts[scene["slug"]] = build_video_prompt(
            scene,
            product_handle,
            product_title,
            sport_category,
            version=meta.get("version", "v01"),
            status=meta.get("status", "final"),
        )
    return prompts


def readme_text(product_handle: str) -> str:
    return f"""Sports Cave Social Media Reels Pack

Product handle: {sanitize_handle(product_handle, "product")}

Instructions:
1. Unzip this pack.
2. Move files into the matching Sports Cave folders:
   - mockup-backgrounds
   - social-media-mockups
   - social-media-reels
   - social-media-video-content
   - sport-videos
3. Keep filenames unchanged.
4. Product handle is the source of truth.
5. Final videos are ready for Meta Reels/Stories testing.
6. Prompt files are included for traceability.
7. Do not rename files manually unless updating version/status.
8. Image files are preserved at original full resolution.
"""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _empty_state() -> dict:
    token = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return {
        "run_dir": str(RUNS_DIR / f"social-media-reels-studio-{token}"),
        "created_at": _now_iso(),
        "files": {
            "product_mockup": None,
            "selected_background": None,
            "image_mockups": {},
            "videos": {},
        },
        "zip_path": None,
    }


def _state() -> dict:
    if PAGE_STATE_KEY not in st.session_state:
        st.session_state[PAGE_STATE_KEY] = _empty_state()
    return st.session_state[PAGE_STATE_KEY]


def _ensure_wizard_flags() -> None:
    for key, default in WIZARD_FLAG_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def _reset_reels_studio_session_state() -> None:
    for key in list(st.session_state.keys()):
        if key == "smrs_start_new_pack":
            continue
        if key == PAGE_STATE_KEY or str(key).startswith("smrs_") or str(key).startswith("reels_"):
            del st.session_state[key]


def _wizard_flags() -> dict:
    return {key: bool(st.session_state.get(key, default)) for key, default in WIZARD_FLAG_DEFAULTS.items()}


def _run_dir(state: dict) -> Path:
    run_dir = Path(state["run_dir"])
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def _safe_ext(filename: str, allowed: list[str], default: str) -> str:
    ext = Path(str(filename or "")).suffix.lower().lstrip(".")
    if ext in allowed:
        return f".{ext}"
    return default


def _uploaded_signature(uploaded_file) -> str:
    return f"{getattr(uploaded_file, 'name', '')}:{getattr(uploaded_file, 'size', '')}"


def _asset_signature(asset: dict | None) -> str:
    if not asset:
        return ""
    digest = hashlib.sha1(_asset_bytes(asset)).hexdigest()[:16]
    return f"{asset.get('filename', '')}:{asset.get('size_bytes', '')}:{digest}"


def _save_upload(uploaded_file, target_path: Path, record_type: str, extra: dict | None = None) -> dict:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    uploaded_file.seek(0)
    with target_path.open("wb") as output_handle:
        shutil.copyfileobj(uploaded_file, output_handle)
    uploaded_file.seek(0)
    record = {
        "type": record_type,
        "path": str(target_path),
        "filename": target_path.name,
        "original_name": getattr(uploaded_file, "name", target_path.name),
        "size": getattr(uploaded_file, "size", None),
        "signature": _uploaded_signature(uploaded_file),
        "saved_at": _now_iso(),
    }
    record.update(extra or {})
    return record


def _save_image_asset_to_path(asset: dict, target_path: Path, record_type: str, extra: dict | None = None) -> dict:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    image_bytes = _asset_bytes(asset)
    target_path.write_bytes(image_bytes)
    record = {
        **asset,
        "type": record_type,
        "path": str(target_path),
        "filename": target_path.name,
        "original_name": asset.get("filename") or target_path.name,
        "safe_filename": target_path.name,
        "size": len(image_bytes),
        "size_bytes": len(image_bytes),
        "signature": _asset_signature(asset),
        "saved_at": _now_iso(),
    }
    record.update(extra or {})
    return record


def _store_source_image_asset(state: dict, asset: dict | None, field: str, target_stem: str, label: str) -> dict | None:
    if asset is None:
        return state["files"].get(field)

    current = state["files"].get(field)
    signature = _asset_signature(asset)
    if current and current.get("signature") == signature and Path(current.get("path", "")).exists():
        return current

    ext = extension_from_mime(asset.get("mime_type") or "", _safe_ext(asset.get("filename", ""), IMAGE_UPLOAD_TYPES, ".png"))
    target = _run_dir(state) / "source" / f"{target_stem}{ext}"
    record = _save_image_asset_to_path(asset, target, label)
    state["files"][field] = record
    if field == "product_mockup":
        st.session_state["reels_product_mockup_asset"] = record
    elif field == "selected_background":
        st.session_state["reels_background_asset"] = record
    state["zip_path"] = None
    return record


def _store_source_upload(state: dict, uploaded_file, field: str, target_stem: str, label: str) -> dict | None:
    if uploaded_file is None:
        return state["files"].get(field)
    return _store_source_image_asset(
        state,
        image_asset_from_uploaded_file(uploaded_file),
        field,
        target_stem,
        label,
    )


def _unique_video_target(state: dict, product_handle: str, scene_slug: str, version: str, status: str) -> tuple[Path, str]:
    clean_version = sanitize_version(version)
    target = _run_dir(state) / "social-media-reels" / video_filename(product_handle, scene_slug, clean_version, status)
    while target.exists():
        clean_version = next_version(clean_version)
        target = _run_dir(state) / "social-media-reels" / video_filename(product_handle, scene_slug, clean_version, status)
    return target, clean_version


def _store_image_mockup_asset(state: dict, asset: dict | None, product_handle: str, scene_slug: str) -> dict | None:
    records = state["files"]["image_mockups"]
    current = records.get(scene_slug)
    if asset is None:
        return current

    signature = _asset_signature(asset)
    expected_name = image_mockup_filename(product_handle, scene_slug)
    if current and current.get("signature") == signature and current.get("filename") == expected_name and Path(current.get("path", "")).exists():
        return current

    target = _run_dir(state) / "social-media-mockups" / expected_name
    if current and Path(current.get("path", "")).exists() and current.get("filename") != expected_name:
        with suppress(FileNotFoundError, PermissionError):
            Path(current["path"]).rename(target)
        if target.exists():
            current.update({"path": str(target), "filename": target.name})
            return current

    record = _save_image_asset_to_path(asset, target, "image_mockup", {"scene_slug": scene_slug})
    records[scene_slug] = record
    generated_assets = st.session_state.setdefault("reels_generated_mockup_assets", {})
    generated_assets[scene_slug] = record
    state["zip_path"] = None
    return record


def _store_image_mockup_upload(state: dict, uploaded_file, product_handle: str, scene_slug: str) -> dict | None:
    if uploaded_file is None:
        return state["files"]["image_mockups"].get(scene_slug)
    return _store_image_mockup_asset(
        state,
        image_asset_from_uploaded_file(uploaded_file),
        product_handle,
        scene_slug,
    )


def _store_video_upload(state: dict, uploaded_file, product_handle: str, scene_slug: str, version: str, status: str) -> dict | None:
    records = state["files"]["videos"]
    current = records.get(scene_slug)
    clean_version = sanitize_version(version)
    clean_status = sanitize_status(status)
    expected_name = video_filename(product_handle, scene_slug, clean_version, clean_status)

    if current and Path(current.get("path", "")).exists() and current.get("filename") != expected_name:
        target = _run_dir(state) / "social-media-reels" / expected_name
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            with suppress(FileNotFoundError, PermissionError):
                Path(current["path"]).rename(target)
            if target.exists():
                current.update(
                    {
                        "path": str(target),
                        "filename": target.name,
                        "version": clean_version,
                        "status": clean_status,
                    }
                )
                state["zip_path"] = None

    if uploaded_file is None:
        return records.get(scene_slug)

    signature = _uploaded_signature(uploaded_file)
    current = records.get(scene_slug)
    if current and current.get("signature") == signature and current.get("filename") == expected_name and Path(current.get("path", "")).exists():
        return current

    target = _run_dir(state) / "social-media-reels" / expected_name
    used_version = clean_version
    if target.exists() and (not current or Path(current.get("path", "")) != target):
        target, used_version = _unique_video_target(state, product_handle, scene_slug, clean_version, clean_status)

    record = _save_upload(
        uploaded_file,
        target,
        "video",
        {"scene_slug": scene_slug, "version": used_version, "status": clean_status},
    )
    records[scene_slug] = record
    state["zip_path"] = None
    return record


def _sync_scene_filenames(state: dict, product_handle: str) -> None:
    for scene in SCENES:
        slug = scene["slug"]
        image_record = state["files"]["image_mockups"].get(slug)
        expected_image = image_mockup_filename(product_handle, slug)
        if image_record and image_record.get("filename") != expected_image:
            old_path = Path(image_record.get("path", ""))
            new_path = old_path.with_name(expected_image)
            if old_path.exists() and not new_path.exists():
                old_path.rename(new_path)
                image_record.update({"path": str(new_path), "filename": new_path.name})
                state["zip_path"] = None

        video_record = state["files"]["videos"].get(slug)
        if video_record:
            expected_video = video_filename(
                product_handle,
                slug,
                video_record.get("version", "v01"),
                video_record.get("status", "final"),
            )
            old_path = Path(video_record.get("path", ""))
            new_path = old_path.with_name(expected_video)
            if old_path.exists() and old_path.name != expected_video and not new_path.exists():
                old_path.rename(new_path)
                video_record.update({"path": str(new_path), "filename": new_path.name})
                state["zip_path"] = None


def _prompt_files(background_prompt: str, image_prompts: dict[str, str], video_prompts: dict[str, str]) -> dict[str, str]:
    image_text = []
    for scene in SCENES:
        image_text.append(f"# {scene['name']} ({scene['slug']})")
        image_text.append(image_prompts[scene["slug"]].strip())
        image_text.append("")
    video_text = []
    for scene in SCENES:
        video_text.append(f"# {scene['video_name']} ({scene['slug']})")
        video_text.append(video_prompts[scene["slug"]].strip())
        video_text.append("")
    return {
        "background-finder-prompt.txt": background_prompt.strip() + "\n",
        "image-prompts.txt": "\n".join(image_text).strip() + "\n",
        "video-prompts.txt": "\n".join(video_text).strip() + "\n",
    }


def _manifest(
    product_handle: str,
    product_title: str,
    sport_category: str,
    state: dict,
    prompt_files: dict[str, str],
    version: str,
) -> dict:
    files = state["files"]
    image_records = files.get("image_mockups") or {}
    video_records = files.get("videos") or {}
    return {
        "product_handle": sanitize_handle(product_handle, "product"),
        "product_title": str(product_title or "").strip(),
        "sport_category": str(sport_category or "").strip(),
        "created_at": _now_iso(),
        "product_mockup_filename": (files.get("product_mockup") or {}).get("filename"),
        "selected_background_filename": (files.get("selected_background") or {}).get("filename"),
        "product_mockup_source": (files.get("product_mockup") or {}).get("source"),
        "selected_background_source": (files.get("selected_background") or {}).get("source"),
        "product_mockup_width": (files.get("product_mockup") or {}).get("width"),
        "product_mockup_height": (files.get("product_mockup") or {}).get("height"),
        "product_mockup_size_bytes": (files.get("product_mockup") or {}).get("size_bytes"),
        "selected_background_width": (files.get("selected_background") or {}).get("width"),
        "selected_background_height": (files.get("selected_background") or {}).get("height"),
        "selected_background_size_bytes": (files.get("selected_background") or {}).get("size_bytes"),
        "image_mockups": [
            {
                "scene_slug": scene["slug"],
                "scene_name": scene["name"],
                "filename": (image_records.get(scene["slug"]) or {}).get("filename"),
                "uploaded": bool(image_records.get(scene["slug"])),
                "original_filename": (image_records.get(scene["slug"]) or {}).get("original_name"),
                "source": (image_records.get(scene["slug"]) or {}).get("source"),
                "width": (image_records.get(scene["slug"]) or {}).get("width"),
                "height": (image_records.get(scene["slug"]) or {}).get("height"),
                "size_bytes": (image_records.get(scene["slug"]) or {}).get("size_bytes"),
            }
            for scene in SCENES
        ],
        "videos": [
            {
                "scene_slug": scene["slug"],
                "scene_name": scene["video_name"],
                "filename": (video_records.get(scene["slug"]) or {}).get("filename"),
                "uploaded": bool(video_records.get(scene["slug"])),
                "status": (video_records.get(scene["slug"]) or {}).get("status"),
                "version": (video_records.get(scene["slug"]) or {}).get("version"),
                "original_filename": (video_records.get(scene["slug"]) or {}).get("original_name"),
            }
            for scene in SCENES
        ],
        "prompt_files": sorted(prompt_files),
        "status": {
            "product_mockup_uploaded": bool(files.get("product_mockup")),
            "selected_background_uploaded": bool(files.get("selected_background")),
            "image_mockup_count": len(image_records),
            "video_count": len(video_records),
        },
        "version": version,
    }


def _zip_write_record(zipf: zipfile.ZipFile, record: dict | None, arcname: str) -> None:
    if not record:
        return
    image_bytes = _asset_bytes(record)
    if image_bytes:
        zipf.writestr(arcname, image_bytes)


def build_social_media_reels_zip(
    run_dir: Path,
    product_handle: str,
    product_title: str,
    sport_category: str,
    state: dict,
    background_prompt: str,
    image_prompts: dict[str, str],
    video_prompts: dict[str, str],
    pack_version: str = PACK_VERSION,
) -> Path:
    handle = sanitize_handle(product_handle, "product")
    sport_folder = sanitize_handle(sport_category, "sport")
    zip_dir = Path(run_dir) / "zip"
    zip_dir.mkdir(parents=True, exist_ok=True)
    zip_path = zip_dir / f"{handle}__social-media-reels-pack__{sanitize_version(pack_version)}.zip"
    prompts = _prompt_files(background_prompt, image_prompts, video_prompts)
    files = state["files"]

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for top_level in (
            "mockup-backgrounds",
            "social-media-mockups",
            "social-media-reels",
            "social-media-video-content",
            "sport-videos",
        ):
            zipf.writestr(f"{top_level}/", "")

        background_root = f"mockup-backgrounds/{handle}"
        mockups_root = f"social-media-mockups/{handle}"
        reels_root = f"social-media-reels/{handle}"
        video_content_root = f"social-media-video-content/{handle}/final"
        sport_root = f"sport-videos/{sport_folder}/{handle}"

        product_mockup = files.get("product_mockup")
        background = files.get("selected_background")
        product_ext = Path((product_mockup or {}).get("filename", "")).suffix or ".png"
        background_ext = Path((background or {}).get("filename", "")).suffix or ".png"

        _zip_write_record(zipf, background, f"{background_root}/selected-background-original{background_ext}")
        _zip_write_record(zipf, product_mockup, f"{background_root}/product-mockup-original{product_ext}")
        zipf.writestr(f"{background_root}/background-finder-prompt.txt", prompts["background-finder-prompt.txt"])

        for scene in SCENES:
            record = (files.get("image_mockups") or {}).get(scene["slug"])
            if record:
                _zip_write_record(zipf, record, f"{mockups_root}/{record['filename']}")
        zipf.writestr(f"{mockups_root}/image-prompts.txt", prompts["image-prompts.txt"])

        for scene in SCENES:
            record = (files.get("videos") or {}).get(scene["slug"])
            if record:
                _zip_write_record(zipf, record, f"{reels_root}/{record['filename']}")
                _zip_write_record(zipf, record, f"{video_content_root}/{record['filename']}")
                _zip_write_record(zipf, record, f"{sport_root}/{record['filename']}")
        zipf.writestr(f"{reels_root}/video-prompts.txt", prompts["video-prompts.txt"])

        zipf.writestr("README-INSTRUCTIONS.txt", readme_text(handle))
        zipf.writestr(
            "manifest.json",
            json.dumps(
                _manifest(handle, product_title, sport_category, state, prompts, sanitize_version(pack_version)),
                indent=2,
            ),
        )

    return zip_path


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        .smrs-header {
            border: 1px solid rgba(212, 165, 76, 0.28);
            background: linear-gradient(135deg, #0B0B0D 0%, #22201D 100%);
            border-radius: 8px;
            padding: 16px 18px;
            margin: 0 0 12px 0;
        }
        .smrs-header h1 {
            color: #F5F2EA;
            font-size: 1.65rem;
            line-height: 1.12;
            margin: 0 0 5px 0;
            letter-spacing: 0;
        }
        .smrs-header p {
            color: #A6A19A;
            margin: 0;
            font-size: 0.92rem;
        }
        .smrs-step-label {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            border: 1px solid rgba(212, 165, 76, 0.45);
            background: #F5F2EA;
            color: #0B0B0D;
            padding: 4px 9px;
            font-size: 0.76rem;
            font-weight: 800;
            margin-bottom: 8px;
        }
        .smrs-card-title {
            font-size: 1rem;
            line-height: 1.2;
            font-weight: 800;
            color: #0B0B0D;
            margin: 0 0 4px 0;
        }
        .smrs-helper {
            color: #66615A;
            font-size: 0.86rem;
            margin-bottom: 8px;
        }
        .smrs-warning-list {
            border: 1px solid rgba(247, 160, 7, 0.35);
            border-left: 4px solid #D4A54C;
            background: #FFF8E8;
            border-radius: 8px;
            padding: 10px 12px;
            margin: 8px 0 10px;
            color: #0B0B0D;
            font-size: 0.9rem;
        }
        .smrs-filename {
            font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
            color: #0B0B0D;
            background: #F5F2EA;
            border: 1px solid #E5E1D8;
            border-radius: 7px;
            padding: 6px 8px;
            overflow-wrap: anywhere;
            font-size: 0.78rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _copy_button(text: str, key: str, label: str = "Copy Prompt", large: bool = False) -> None:
    text_json = json.dumps(str(text or ""))
    safe_key = sanitize_handle(key, "copy")
    safe_label = html.escape(label)
    button_height = 52 if large else 44
    font_size = "15px" if large else "14px"
    components.html(
        f"""
        <button id="smrs-{safe_key}" type="button" style="
          width:100%;
          min-height:{button_height}px;
          border:1px solid rgba(212,165,76,0.7);
          border-radius:7px;
          background:#D4A54C;
          color:#0B0B0D;
          font-weight:800;
          font-size:{font_size};
          cursor:pointer;
          box-sizing:border-box;
        ">{safe_label}</button>
        <script>
        (() => {{
          const button = document.getElementById("smrs-{safe_key}");
          const text = {text_json};
          const original = button.innerText;
          async function copyText(event) {{
            event.preventDefault();
            try {{
              if (navigator.clipboard && window.isSecureContext) {{
                await navigator.clipboard.writeText(text);
              }} else {{
                const textarea = document.createElement("textarea");
                textarea.value = text;
                textarea.style.position = "fixed";
                textarea.style.opacity = "0";
                document.body.appendChild(textarea);
                textarea.focus();
                textarea.select();
                document.execCommand("copy");
                document.body.removeChild(textarea);
              }}
            }} catch (error) {{
              const textarea = document.createElement("textarea");
              textarea.value = text;
              textarea.style.position = "fixed";
              textarea.style.opacity = "0";
              document.body.appendChild(textarea);
              textarea.focus();
              textarea.select();
              document.execCommand("copy");
              document.body.removeChild(textarea);
            }}
            button.innerText = "Prompt copied";
            setTimeout(() => {{ button.innerText = original; }}, 1400);
          }}
          button.addEventListener("click", copyText);
        }})();
        </script>
        """,
        height=button_height + 8,
    )


def _paste_zone(key: str, label: str, asset_type: str, product_handle: str = "", scene_slug: str = "") -> dict | None:
    return _paste_zone_component(
        label=label,
        asset_type=asset_type,
        product_handle=sanitize_handle(product_handle, ""),
        scene_slug=sanitize_handle(scene_slug, ""),
        key=f"smrs_paste_zone_{key}",
        default=None,
    )


def _image_asset_state_key(key: str) -> str:
    return f"smrs_image_asset::{key}"


def reels_image_input(
    label: str,
    key: str,
    help_text: str,
    asset_type: str,
    accepted_types: tuple[str, ...] = ("png", "jpg", "jpeg", "webp"),
    product_handle: str = "",
    scene_slug: str = "",
) -> dict | None:
    st.caption("Upload, drag and drop, or paste an image.")
    if help_text:
        st.caption(help_text)
    st.caption("Do not use screenshots if the original image download is available. Screenshots reduce quality.")

    state_key = _image_asset_state_key(key)
    uploaded_file = st.file_uploader(
        label,
        key=f"{key}_uploader",
        help=(
            "Upload, drag and drop, or paste an image below. "
            f"Supported image types: {', '.join(accepted_types)}."
        ),
    )
    if uploaded_file is not None:
        uploaded_asset = image_asset_from_uploaded_file(uploaded_file, source="upload")
        if has_valid_image_asset(uploaded_asset):
            st.session_state[state_key] = uploaded_asset
        else:
            st.error("That file could not be read as a valid image. Please upload a PNG, JPG, JPEG, or WEBP file.")

    payload = _paste_zone(key, "Paste image here", asset_type, product_handle, scene_slug)
    pasted_asset = image_asset_from_paste_payload(payload, product_handle, asset_type, scene_slug)
    if pasted_asset:
        st.session_state[state_key] = pasted_asset
        st.success(f"Image received from {pasted_asset.get('source', 'paste')}.")

    return st.session_state.get(state_key)


def _prompt_preview_key(prefix: str, slug: str, text: str) -> str:
    digest = hashlib.sha1(str(text or "").encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{sanitize_handle(slug, 'prompt')}_{digest}"


def _step_header(title: str, complete: bool) -> None:
    status = "Complete" if complete else "Needs attention"
    st.markdown(
        f'<div class="smrs-step-label">{html.escape(status)}</div>',
        unsafe_allow_html=True,
    )
    st.subheader(title)


def render_full_resolution_image_tools(asset: dict | None, label: str, key: str) -> None:
    if not asset:
        st.caption("No image available yet.")
        return

    image_bytes = _asset_bytes(asset)
    if not image_bytes:
        st.caption("Original image bytes are not available.")
        return

    filename = asset.get("filename") or asset.get("safe_filename") or "image.png"
    mime_type = asset.get("mime_type") or mime_type_from_filename(filename)
    width = asset.get("width")
    height = asset.get("height")
    dimensions = f"{width} x {height}" if width and height else "Unknown"
    size = asset.get("size_bytes") or len(image_bytes)

    st.markdown(f"**{label}**")
    st.caption(
        f"`{filename}` | Dimensions: `{dimensions}` | "
        f"Size: `{format_file_size(size)}` | Type: `{mime_type}` | Source: `{asset.get('source', 'upload')}`"
    )
    st.caption("Original source bytes are preserved. The image below is visually constrained only.")
    st.image(image_bytes, caption=filename, width=320)


def _render_video_preview(record: dict | None) -> None:
    if not record:
        st.caption("No video uploaded yet.")
        return
    path = Path(record.get("path", ""))
    if path.exists():
        with suppress(Exception):
            st.video(str(path))
        st.markdown(f'<div class="smrs-filename">{html.escape(record.get("filename") or path.name)}</div>', unsafe_allow_html=True)
    else:
        st.caption("Saved video is missing on disk.")


def _step_statuses(state: dict, product_handle: str) -> list[tuple[str, bool]]:
    files = state["files"]
    image_mockups = files.get("image_mockups") or {}
    step1 = has_valid_image_asset(files.get("product_mockup"))
    step2 = has_valid_image_asset(files.get("selected_background"))
    step3 = any(has_valid_image_asset(asset) for asset in image_mockups.values())
    step4 = bool(files.get("videos"))
    return [
        ("1 Product", step1),
        ("2 Background", step2),
        ("3 Mockups", step3),
        ("4 Reels", step4),
    ]


def _render_progress(state: dict, product_handle: str) -> None:
    statuses = _step_statuses(state, product_handle)
    cols = st.columns(len(statuses))
    for column, (label, complete) in zip(cols, statuses):
        column.metric(label, "Done" if complete else "Open")


def _render_warning_block() -> None:
    st.markdown(
        """
        <div class="smrs-warning-list">
          <strong>VA quality warnings</strong><br>
          Do not use low-resolution backgrounds. Do not use backgrounds with clutter or strong logos.
          Do not accept outputs where the frame/artwork is distorted. Reject and regenerate if text,
          badge, edition plate, or frame shape changes.
        </div>
        """,
        unsafe_allow_html=True,
    )


def _locked_step(title: str, message: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{html.escape(title)}**")
        st.info(message)


def _summary_card(title: str, product_handle: str, sport_category: str) -> None:
    st.markdown(
        f"""
        <div class="smrs-warning-list">
          <strong>Detected product:</strong><br>
          Title: {html.escape(title or "Not detected")}<br>
          Handle: {html.escape(product_handle or "Not detected")}<br>
          Sport: {html.escape(sport_category or "Not detected")}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _sport_selectbox(current_value: str) -> str:
    options = list(SPORT_CATEGORY_OPTIONS)
    if current_value and current_value not in options:
        options.append(current_value)
    index = options.index(current_value) if current_value in options else 0
    return st.selectbox(
        "Sport category",
        options,
        index=index,
        key="smrs_sport_category_edit",
        accept_new_options=True,
    )


def _render_reference_pair(state: dict) -> None:
    st.caption(
        "Use these exact original source images as Image A and Image B in ChatGPT. "
        "Do not screenshot the previews; the app keeps the uploaded bytes at their original resolution."
    )
    columns = st.columns(2)
    with columns[0]:
        render_full_resolution_image_tools(
            state["files"].get("product_mockup"),
            "Image A - Product Mockup",
            "reference_product_mockup",
        )
    with columns[1]:
        render_full_resolution_image_tools(
            state["files"].get("selected_background"),
            "Image B - Selected Background",
            "reference_selected_background",
        )


def get_scene_by_slug(scene_slug: str) -> dict:
    clean_slug = sanitize_handle(scene_slug, "collector-admire")
    for scene in SCENES:
        if scene["slug"] == clean_slug:
            return scene
    return SCENES[0]


def build_save_instructions(product_handle: str, sport_category: str) -> str:
    handle = sanitize_handle(product_handle, FILENAME_HANDLE_PLACEHOLDER)
    sport_folder = sanitize_handle(sport_category, "sport-category")
    return (
        "Background/reference image:\n"
        f"mockup-backgrounds/{handle}/\n\n"
        "Finished realistic mockup:\n"
        f"social-media-mockups/{handle}/\n\n"
        "Final reel video:\n"
        f"social-media-reels/{handle}/\n\n"
        "Final archived video:\n"
        f"social-media-video-content/{handle}/final/\n\n"
        "Sport archive if used:\n"
        f"sport-videos/{sport_folder}/{handle}/"
    )


def build_reels_hub_payload(
    product_handle: str,
    product_title: str,
    sport_category: str,
    creative_notes: str,
    scene_slug: str,
    version: str = "v01",
    status: str = "final",
) -> dict[str, str]:
    handle = sanitize_handle(product_handle, "")
    filename_handle = handle or FILENAME_HANDLE_PLACEHOLDER
    prompt_handle = handle or GENERIC_PRODUCT_HANDLE_PLACEHOLDER
    prompt_title = str(product_title or "").strip() or GENERIC_PRODUCT_TITLE_PLACEHOLDER
    prompt_sport = str(sport_category or "").strip() or GENERIC_SPORT_PLACEHOLDER
    prompt_notes = str(creative_notes or "").strip() or GENERIC_PRODUCT_ANGLE_PLACEHOLDER
    scene = get_scene_by_slug(scene_slug)
    clean_version = sanitize_version(version)
    clean_status = sanitize_status(status)
    return {
        "product_handle": filename_handle,
        "prompt_product_handle": prompt_handle,
        "scene_slug": scene["slug"],
        "scene_name": scene["name"],
        "video_scene_name": scene["video_name"],
        "background_prompt": build_background_finder_prompt(prompt_handle, prompt_title, prompt_sport, prompt_notes),
        "image_prompt": build_image_prompt(scene, prompt_handle, prompt_title, prompt_sport, prompt_notes),
        "video_prompt": build_video_prompt(scene, prompt_handle, prompt_title, prompt_sport, clean_version, clean_status),
        "mockup_filename": image_mockup_filename_with_meta(filename_handle, scene["slug"], clean_version, clean_status),
        "video_filename": video_filename(filename_handle, scene["slug"], clean_version, clean_status),
        "save_instructions": build_save_instructions(filename_handle, sport_category),
        "version": clean_version,
        "status": clean_status,
    }


def _render_copyable_prompt(label: str, prompt_text: str, key: str, copy_label: str, height: int = 360) -> None:
    _copy_button(prompt_text, key, copy_label, large=True)
    st.text_area(
        label,
        value=prompt_text,
        height=height,
        key=_prompt_preview_key(f"smrs_hub_{key}", key, prompt_text),
        disabled=True,
    )


def render_page() -> None:
    _inject_styles()
    _ensure_wizard_flags()
    state = _state()
    files = state["files"]

    st.markdown(
        """
        <div class="smrs-header">
          <h1>Social Media Reels Studio</h1>
          <p>Create background references, lifestyle mockups, and image-to-video reels for Sports Cave products.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    scene_options = {scene["name"]: scene["slug"] for scene in SCENES}
    default_scene = st.session_state.get("smrs_selected_scene_slug", SCENES[0]["slug"])
    default_label = next((name for name, slug in scene_options.items() if slug == default_scene), SCENES[0]["name"])
    selected_scene_label = default_label

    payload = build_reels_hub_payload(
        "",
        "",
        "",
        "",
        default_scene,
    )

    with st.container(border=True):
        st.markdown('<div class="smrs-card-title">1. Find the Best Background</div>', unsafe_allow_html=True)
        with st.expander("How to use", expanded=False):
            st.markdown(
                f"""
Paste the black framed product image into ChatGPT with this prompt. ChatGPT will analyse the artwork directly and help choose the best background/reference room for this exact product. Save the selected background/reference image into:

`mockup-backgrounds/{GENERIC_PRODUCT_HANDLE_PLACEHOLDER}/`

Do not upload a screenshot. Use the full-resolution black framed product mockup.
                """.strip()
            )
        _render_copyable_prompt(
            "Background finder prompt",
            payload["background_prompt"],
            "background-finder",
            "Copy background prompt",
            height=420,
        )
        st.caption(f"Folder reminder: `mockup-backgrounds/{GENERIC_PRODUCT_HANDLE_PLACEHOLDER}/`")

    with st.container(border=True):
        st.markdown('<div class="smrs-card-title">2. Create the Real-Life Mockup</div>', unsafe_allow_html=True)
        selected_scene_label = st.radio(
            "Scene",
            list(scene_options.keys()),
            index=list(scene_options.keys()).index(default_label),
            key="smrs_selected_scene_label",
            horizontal=False,
        )
        selected_scene_slug = scene_options[selected_scene_label]
        st.session_state["smrs_selected_scene_slug"] = selected_scene_slug
        payload = build_reels_hub_payload(
            "",
            "",
            "",
            "",
            selected_scene_slug,
        )
        with st.expander("How to use", expanded=False):
            st.markdown(
                f"""
Upload the full-resolution black framed product image and the selected background/reference room image into ChatGPT. Use one of the prompts below to generate the realistic lifestyle mockup. Save the finished mockup image into:

`social-media-mockups/{GENERIC_PRODUCT_HANDLE_PLACEHOLDER}/`

Use the full-resolution generated mockup, not a screenshot.
                """.strip()
            )
        st.caption(f"Selected scene: {payload['scene_name']} | `{payload['scene_slug']}`")
        st.markdown(f'<div class="smrs-filename">{html.escape(payload["mockup_filename"])}</div>', unsafe_allow_html=True)
        _render_copyable_prompt(
            "Image mockup prompt",
            payload["image_prompt"],
            f"image-{payload['scene_slug']}",
            "Copy image prompt",
            height=520,
        )

    with st.container(border=True):
        st.markdown('<div class="smrs-card-title">3. Create the Reel Video</div>', unsafe_allow_html=True)
        with st.expander("How to use", expanded=False):
            st.markdown(
                f"""
Upload the finished realistic mockup image into your image-to-video editor. Paste the matching video prompt below. Export as a vertical 9:16 reel, 6-8 seconds, 1080p minimum. Save the final video into:

`social-media-reels/{GENERIC_PRODUCT_HANDLE_PLACEHOLDER}/`

Optional final archive location:
`social-media-video-content/{GENERIC_PRODUCT_HANDLE_PLACEHOLDER}/final/`
                """.strip()
            )
        st.caption(f"Matching scene: {payload['video_scene_name']} | `{payload['scene_slug']}`")
        st.markdown(f'<div class="smrs-filename">{html.escape(payload["video_filename"])}</div>', unsafe_allow_html=True)
        _render_copyable_prompt(
            "Image-to-video prompt",
            payload["video_prompt"],
            f"video-{payload['scene_slug']}",
            "Copy video prompt",
            height=520,
        )

    with st.container(border=True):
        st.markdown('<div class="smrs-card-title">4. Upload Final Reel / File Naming</div>', unsafe_allow_html=True)
        final_cols = st.columns([1, 1])
        raw_final_handle = final_cols[0].text_input(
            "Product handle",
            key="smrs_final_product_handle",
            placeholder="athlete-name-product-handle",
        )
        final_product_title = final_cols[1].text_input(
            "Product title",
            key="smrs_final_product_title",
            placeholder="Athlete Name Wall Art",
        )
        final_cols = st.columns([1, 1])
        athlete_or_product_name = final_cols[0].text_input(
            "Athlete / product name",
            key="smrs_final_athlete_product_name",
            placeholder="Athlete name",
        )
        final_sport_category = final_cols[1].text_input(
            "Sport category",
            key="smrs_final_sport_category",
            placeholder="Choose or add sport category",
        )
        final_scene_labels = list(scene_options.keys())
        final_scene_label = st.selectbox(
            "Scene",
            final_scene_labels,
            index=final_scene_labels.index(selected_scene_label) if selected_scene_label in final_scene_labels else 0,
            key="smrs_final_scene_label",
        )
        final_scene_slug = scene_options[final_scene_label]
        final_cols = st.columns([1, 1])
        version = final_cols[0].text_input(
            "Version",
            value=st.session_state.get("smrs_final_video_version", "v01"),
            key="smrs_final_video_version",
        )
        status = final_cols[1].selectbox(
            "Status",
            STATUS_OPTIONS,
            index=STATUS_OPTIONS.index(st.session_state.get("smrs_final_video_status", "final"))
            if st.session_state.get("smrs_final_video_status", "final") in STATUS_OPTIONS
            else STATUS_OPTIONS.index("final"),
            key="smrs_final_video_status",
        )
        final_product_handle = sanitize_handle(raw_final_handle, FILENAME_HANDLE_PLACEHOLDER)
        payload = build_reels_hub_payload(
            final_product_handle,
            final_product_title,
            final_sport_category,
            athlete_or_product_name,
            final_scene_slug,
            version,
            status,
        )
        _store_video_upload(state, None, final_product_handle, payload["scene_slug"], payload["version"], payload["status"])
        st.caption("Generated video filename")
        st.markdown(f'<div class="smrs-filename">{html.escape(payload["video_filename"])}</div>', unsafe_allow_html=True)
        st.caption("Matching mockup filename suggestion")
        st.markdown(f'<div class="smrs-filename">{html.escape(payload["mockup_filename"])}</div>', unsafe_allow_html=True)

        uploaded_video = st.file_uploader(
            "Upload final video",
            type=VIDEO_UPLOAD_TYPES,
            key=f"smrs_final_video_upload_{payload['scene_slug']}",
        )
        if uploaded_video is not None:
            record = _store_video_upload(state, uploaded_video, final_product_handle, payload["scene_slug"], payload["version"], payload["status"])
            if record:
                st.success(f"Saved as {record['filename']}")
                if record.get("version") != payload["version"]:
                    st.info(f"Filename already existed, so this upload was saved as {record['version']}.")

        st.caption("Save instructions")
        st.text_area(
            "Folder paths",
            value=payload["save_instructions"],
            height=220,
            key=_prompt_preview_key("smrs_save_instructions", payload["scene_slug"], payload["save_instructions"]),
            disabled=True,
        )
