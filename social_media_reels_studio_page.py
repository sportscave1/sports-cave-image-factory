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

from sports_cave_prompt_blocks import (
    SPORTS_CAVE_PRODUCT_AND_ROOM_LOCK_BLOCK,
    SPORTS_CAVE_UGC_HUMAN_REALISM_BLOCK,
    SPORTS_CAVE_UGC_VIDEO_REALISM_BLOCK,
    append_sports_cave_prompt_blocks,
)


BASE_DIR = Path(__file__).resolve().parent
RUNS_DIR = BASE_DIR / "output" / "runs"
PASTE_COMPONENT_DIR = BASE_DIR / "components" / "reels_image_paste_zone"
PAGE_STATE_KEY = "smrs_state"
IMAGE_UPLOAD_TYPES = ["jpg", "jpeg", "png", "webp"]
MOCKUP_UPLOAD_TYPES = ["png"]
VIDEO_UPLOAD_TYPES = ["mp4"]
PACK_VERSION = "v01"
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
        "video_name": "Holding & Admiring Video",
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
        "video_name": "Hanging / Adjusting Video",
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
        "video_name": "Standing Back Admiring Video",
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
        "video_name": "Artwork Only Wall Video",
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


IMAGE_MASTER_RULES = """Image A is the exact Sports Cave black framed product mockup.
Image B is the selected background/reference room.
Use Image A for the product and Image B for the environment.
The uploaded product artwork is the hero. Preserve it exactly.
The output must look like a real premium Sports Cave lifestyle photograph, not AI.

Non-negotiables:
- The uploaded Sports Cave artwork and black frame must remain 100% unchanged
- Do not redesign the artwork
- Do not change the colours
- Do not change the typography
- Do not change the badge
- Do not change the edition plate
- Do not crop the artwork
- Do not blur the artwork
- Do not stretch, warp, bend, squash, distort, or regenerate the frame or artwork
- Do not distort proportions
- Do not make the frame look pasted on
- Do not cover important artwork details with hands
- Do not add fake logos, fake text overlays, or watermarks
- Do not add clutter
- Do not make it CGI, cartoon, glossy, or fake"""


VIDEO_MASTER_RULES = """Create a premium ultra-realistic 6-8 second image-to-video ad from this exact still image.

Keep the framed Sports Cave artwork 100% unchanged.
Do not alter the artwork, text, badge, frame, colours, proportions, or layout.
Do not warp, redraw, crop, blur, or regenerate the artwork or frame.
Do not distort the frame.
Do not change the room.
Do not add text overlays.
Do not add logos.
Do not add extra people.
Do not make it cartoon, glossy, or CGI.
The artwork must remain razor sharp and stable throughout."""


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
    return f"""Act as the premium creative director for Sports Cave.

I have uploaded a black framed Sports Cave product mockup.

Product handle: {product_handle}
Product title: {product_title}
Sport category: {sport_category}
Creative notes: {creative_notes}

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
    product_handle = sanitize_handle(product_handle, "product-handle")
    product_title = str(product_title or "").strip() or "Untitled Sports Cave product"
    sport_category = str(sport_category or "").strip() or "sport"
    creative_notes = str(creative_notes or "").strip() or "No extra creative notes supplied."
    prompt = f"""{IMAGE_MASTER_RULES}

Product handle: {product_handle}
Product title: {product_title}
Sport category: {sport_category}
Creative notes: {creative_notes}
Scene: {scene["name"]}
Scene slug: {scene["slug"]}

Task:
{scene["image_direction"]}

Composition:
- Premium Shopify-grade Sports Cave product photography
- Use the original full-resolution Image A and Image B uploads, not screenshots or compressed previews
- Realistic room perspective and believable frame scale
- Black frame should feel physically present in the room
- Natural shadows behind the frame and around any hands
- Subtle glass reflection only, never covering key artwork detail
- High-resolution 1:1 square output for Meta feed testing
- Clean, premium, masculine collector-room mood

Quality control:
Reject and regenerate if text, badge, edition plate, artwork colour, or frame shape changes.
Reject and regenerate if the frame looks pasted on, warped, too glossy, blurry, or fake.
Do not accept low-resolution, cluttered, logo-heavy, or distorted backgrounds."""
    return append_sports_cave_prompt_blocks(prompt, include_human=bool(scene.get("has_person")))


def build_video_prompt(scene: dict, product_handle: str, product_title: str, sport_category: str, version: str = "v01", status: str = "final") -> str:
    product_handle = sanitize_handle(product_handle, "product-handle")
    product_title = str(product_title or "").strip() or "Untitled Sports Cave product"
    sport_category = str(sport_category or "").strip() or "sport"
    prompt = f"""{VIDEO_MASTER_RULES}

Product handle: {product_handle}
Product title: {product_title}
Sport category: {sport_category}
Video scene: {scene["video_name"]}
Video scene slug: {scene["slug"]}
Version: {sanitize_version(version)}
Status: {sanitize_status(status)}

Movement:
{scene["video_direction"]}

Camera and realism:
- Keep motion subtle, premium, and natural
- Preserve the still-image composition and room
- Keep the artwork razor sharp and stable
- Soft realistic glass reflection is okay only if it does not obscure details
- Natural shadows and realistic depth

Output: 9:16 vertical, 1080p, 6-8 seconds, photorealistic, smooth natural motion, Meta Reels/Stories ready."""
    return append_sports_cave_prompt_blocks(
        prompt,
        include_human=bool(scene.get("has_person")),
        include_video=True,
    )


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
        type=list(accepted_types),
        key=f"{key}_uploader",
        help="Upload, drag and drop, or paste an image below.",
    )
    if uploaded_file is not None:
        st.session_state[state_key] = image_asset_from_uploaded_file(uploaded_file, source="upload")

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


def render_page() -> None:
    _inject_styles()
    _ensure_wizard_flags()
    state = _state()
    files = state["files"]
    _sync_wizard_completion_from_assets(state)

    st.markdown(
        """
        <div class="smrs-header">
          <h1>Social Media Reels Studio</h1>
          <p>Build premium Sports Cave room mockups, video prompts, and one clean export pack.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    reset_cols = st.columns([1, 3])
    if reset_cols[0].button("Start New Reel Pack", key="smrs_start_new_pack", use_container_width=True):
        _reset_reels_studio_session_state()
        st.rerun()

    flags = _wizard_flags()
    unlocks = wizard_unlocks(flags)
    raw_handle = st.session_state.get("smrs_product_handle", "")
    product_handle = sanitize_handle(raw_handle)
    product_title = st.session_state.get("smrs_product_title", "")
    sport_category = st.session_state.get("smrs_sport_category", "")
    creative_notes = st.session_state.get("smrs_creative_notes", "")

    if product_handle:
        _sync_scene_filenames(state, product_handle)

    step1_complete = has_valid_image_asset(files.get("product_mockup"))
    with st.container(border=True):
        _step_header("1. Upload Product Mockup", step1_complete)
        st.caption("Upload the black framed product mockup, then generate the reel workflow.")

        if not step1_complete:
            product_asset = reels_image_input(
                "Upload the black framed product mockup",
                key="smrs_product_mockup",
                help_text="Upload, drag and drop, or paste an image below.",
                asset_type="product-mockup",
                product_handle=product_handle,
            )
            if has_valid_image_asset(product_asset):
                details = derive_product_details_from_asset(product_asset)
                _store_source_image_asset(state, product_asset, "product_mockup", "product-mockup-original", "product_mockup")
                if not st.session_state.get("smrs_product_handle"):
                    st.session_state["smrs_product_title"] = details["product_title"]
                    st.session_state["smrs_product_handle"] = details["product_handle"]
                    st.session_state["smrs_sport_category"] = details["sport_category"]
                    st.session_state.setdefault("smrs_creative_notes", "")
                    if not details["sport_category"] or details["product_handle"] == "pasted-product-mockup":
                        st.session_state["smrs_force_edit_details"] = True
                st.session_state["reels_product_generated"] = True
                _sync_wizard_completion_from_assets(state)
                render_full_resolution_image_tools(product_asset, "Product mockup ready", "step1_product_pending")
                st.rerun()
            if st.button(
                "Generate",
                key="smrs_generate_product",
                type="primary",
                use_container_width=True,
                disabled=not has_valid_image_asset(product_asset),
            ):
                details = derive_product_details_from_asset(product_asset)
                _store_source_image_asset(state, product_asset, "product_mockup", "product-mockup-original", "product_mockup")
                st.session_state["smrs_product_title"] = details["product_title"]
                st.session_state["smrs_product_handle"] = details["product_handle"]
                st.session_state["smrs_sport_category"] = details["sport_category"]
                st.session_state.setdefault("smrs_creative_notes", "")
                if not details["sport_category"] or details["product_handle"] == "pasted-product-mockup":
                    st.session_state["smrs_force_edit_details"] = True
                st.session_state["reels_step_1_complete"] = True
                st.session_state["reels_product_generated"] = True
                st.session_state["reels_step_2_complete"] = False
                st.session_state["reels_background_generated"] = False
                st.session_state["reels_step_3_complete"] = False
                st.session_state["reels_image_prompts_generated"] = False
                st.session_state["reels_step_4_complete"] = False
                st.session_state["reels_video_prompts_generated"] = False
                _sync_wizard_completion_from_assets(state)
                st.rerun()
        else:
            render_full_resolution_image_tools(files.get("product_mockup"), "Product Mockup", "step1_product")
            _summary_card(product_title, product_handle, sport_category)
            if not sport_category:
                st.warning("Sport could not be detected. Open Edit detected details and select a sport category.")
            with st.expander("Edit detected details", expanded=bool(st.session_state.get("smrs_force_edit_details"))):
                product_title = st.text_input("Product title", key="smrs_product_title")
                raw_handle = st.text_input("Shopify product handle", key="smrs_product_handle")
                product_handle = sanitize_handle(raw_handle)
                if raw_handle and raw_handle != product_handle:
                    st.caption(f"Sanitized handle used for filenames: {product_handle}")
                sport_category = _sport_selectbox(st.session_state.get("smrs_sport_category", ""))
                st.session_state["smrs_sport_category"] = sport_category
                creative_notes = st.text_area("Creative notes", key="smrs_creative_notes", height=90)

    flags = _wizard_flags()
    unlocks = wizard_unlocks(flags)
    product_handle = sanitize_handle(st.session_state.get("smrs_product_handle", ""))
    product_title = st.session_state.get("smrs_product_title", "")
    sport_category = st.session_state.get("smrs_sport_category", "")
    creative_notes = st.session_state.get("smrs_creative_notes", "")
    if product_handle:
        _sync_scene_filenames(state, product_handle)

    if step1_complete:
        _render_progress(state, product_handle)
        _render_warning_block()

    if not unlocks["step_2"]:
        _locked_step("2. Find / Upload Background", "Complete Step 1 first to unlock this section.")
        return

    background_prompt = build_background_finder_prompt(product_handle, product_title, sport_category, creative_notes)
    step2_complete = has_valid_image_asset(files.get("selected_background"))
    with st.container(border=True):
        _step_header("2. Find / Upload Background", step2_complete)
        st.caption("Use ChatGPT to choose the best background, then upload the selected room here.")
        st.markdown(
            "A) Copy the background finder prompt into ChatGPT with the product mockup uploaded.\n\n"
            "B) Choose the best room/background from ChatGPT.\n\n"
            "C) Upload the selected background/reference room here.\n\n"
            "D) Click Generate."
        )
        _copy_button(background_prompt, "background-finder", "Copy Background Finder Prompt", large=True)
        st.text_area(
            "Background finder prompt",
            value=background_prompt,
            height=520,
            key=_prompt_preview_key("smrs_background_prompt_preview", "background", background_prompt),
            disabled=True,
        )
        background_asset = reels_image_input(
            "Upload selected background/reference room",
            key="smrs_background",
            help_text="Use ChatGPT to choose the best background, then upload, drag/drop, or paste the selected room here.",
            asset_type="background",
            product_handle=product_handle,
        )
        if has_valid_image_asset(background_asset):
            _store_source_image_asset(state, background_asset, "selected_background", "selected-background-original", "selected_background")
            _sync_wizard_completion_from_assets(state)
            render_full_resolution_image_tools(background_asset, "Selected background ready", "step2_background_pending")
            if not step2_complete:
                st.rerun()
        if st.button(
            "Generate",
            key="smrs_generate_background",
            type="primary",
            use_container_width=True,
            disabled=not has_valid_image_asset(background_asset) and not has_valid_image_asset(files.get("selected_background")),
        ):
            if background_asset is not None:
                _store_source_image_asset(state, background_asset, "selected_background", "selected-background-original", "selected_background")
            st.session_state["reels_step_2_complete"] = True
            st.session_state["reels_background_generated"] = True
            st.session_state["reels_image_prompts_generated"] = True
            st.session_state["reels_step_3_complete"] = False
            st.session_state["reels_video_prompts_generated"] = False
            st.session_state["reels_step_4_complete"] = False
            _sync_wizard_completion_from_assets(state)
            st.rerun()
        render_full_resolution_image_tools(files.get("selected_background"), "Selected Background", "step2_background")

    flags = _wizard_flags()
    unlocks = wizard_unlocks(flags)
    if not unlocks["step_3"]:
        _locked_step("3. Create Image Mockups", "Complete Step 2 first to unlock this section.")
        return

    image_prompts = build_image_prompts(product_handle, product_title, sport_category, creative_notes)
    step3_complete = has_any_valid_image_asset(files.get("image_mockups"))
    with st.container(border=True):
        _step_header("3. Create Image Mockups", step3_complete)
        st.caption("Upload Image A and Image B to ChatGPT, then paste a prompt below.")
        st.info(
            "Upload BOTH reference files into ChatGPT:\n\n"
            "Image A = product mockup\n\n"
            "Image B = selected background/reference room\n\n"
            "Then paste one of the prompts below."
        )
        _render_reference_pair(state)

        columns = st.columns(2)
        for index, scene in enumerate(SCENES):
            with columns[index % 2]:
                with st.container(border=True):
                    st.markdown(f'<div class="smrs-card-title">{html.escape(scene["name"])}</div>', unsafe_allow_html=True)
                    st.caption(f"Scene slug: {scene['slug']}")
                    prompt_text = image_prompts[scene["slug"]]
                    _copy_button(prompt_text, f"image-{scene['slug']}", "Copy Prompt")
                    st.text_area(
                        "Generated prompt",
                        value=prompt_text,
                        height=360,
                        key=_prompt_preview_key("smrs_image_prompt", scene["slug"], prompt_text),
                        disabled=True,
                    )
                    mockup_asset = reels_image_input(
                        "Upload final generated mockup image",
                        key=f"smrs_mockup_{scene['slug']}",
                        help_text="Upload, drag and drop, or paste the generated mockup image.",
                        asset_type="mockup",
                        accepted_types=("png", "jpg", "jpeg", "webp"),
                        product_handle=product_handle,
                        scene_slug=scene["slug"],
                    )
                    if has_valid_image_asset(mockup_asset):
                        _store_image_mockup_asset(state, mockup_asset, product_handle, scene["slug"])
                        _sync_wizard_completion_from_assets(state)
                        if not step3_complete:
                            st.rerun()
                    render_full_resolution_image_tools(
                        files["image_mockups"].get(scene["slug"]),
                        f"{scene['name']} Mockup",
                        f"step3_{scene['slug']}",
                    )

    flags = _wizard_flags()
    unlocks = wizard_unlocks(flags)
    if not unlocks["step_4"]:
        _locked_step("4. Create Image-To-Video Reels", "Complete Step 3 first to unlock this section.")
        return

    with st.container(border=True):
        step4_complete = bool(flags["reels_step_4_complete"] and files.get("videos"))
        _step_header("4. Create Image-To-Video Reels", step4_complete)
        st.caption("Upload the generated mockup into your AI video tool, then paste the matching prompt.")
        st.info("Upload the generated mockup image into your AI video editor. Then paste the matching prompt below.")

        uploaded_scenes = [scene for scene in SCENES if files["image_mockups"].get(scene["slug"])]
        video_columns = st.columns(2)
        for index, scene in enumerate(uploaded_scenes):
            slug = scene["slug"]
            with video_columns[index % 2]:
                with st.container(border=True):
                    st.markdown(f'<div class="smrs-card-title">{html.escape(scene["video_name"])}</div>', unsafe_allow_html=True)
                    st.caption(f"Video scene slug: {slug}")
                    form_cols = st.columns([1, 1])
                    status = form_cols[0].selectbox(
                        "Status",
                        STATUS_OPTIONS,
                        index=STATUS_OPTIONS.index((files["videos"].get(slug) or {}).get("status", "final"))
                        if (files["videos"].get(slug) or {}).get("status", "final") in STATUS_OPTIONS
                        else STATUS_OPTIONS.index("final"),
                        key=f"smrs_video_status_{slug}",
                    )
                    version = form_cols[1].text_input(
                        "Version",
                        value=(files["videos"].get(slug) or {}).get("version", "v01"),
                        key=f"smrs_video_version_{slug}",
                    )
                    _store_video_upload(state, None, product_handle, slug, version, status)
                    current_video_prompt = build_video_prompt(scene, product_handle, product_title, sport_category, version, status)
                    _copy_button(current_video_prompt, f"video-{slug}", "Copy Video Prompt")
                    st.text_area(
                        "Generated image-to-video prompt",
                        value=current_video_prompt,
                        height=340,
                        key=_prompt_preview_key("smrs_video_prompt", slug, current_video_prompt),
                        disabled=True,
                    )
                    uploaded_video = st.file_uploader(
                        "Upload the final MP4 here",
                        type=VIDEO_UPLOAD_TYPES,
                        key=f"smrs_video_upload_{slug}",
                    )
                    if uploaded_video is not None:
                        record = _store_video_upload(state, uploaded_video, product_handle, slug, version, status)
                        st.session_state["reels_step_4_complete"] = True
                        if record and record.get("version") != sanitize_version(version):
                            st.info(f"Filename already existed, so this upload was saved as {record['version']}.")
                    _render_video_preview(files["videos"].get(slug))

    flags = _wizard_flags()
    unlocks = wizard_unlocks(flags)
    if not unlocks["step_5"]:
        _locked_step("5. Export Content Pack", "Complete Step 4 first to unlock this section.")
        return

    video_meta = {
        scene["slug"]: {
            "version": st.session_state.get(f"smrs_video_version_{scene['slug']}", (files["videos"].get(scene["slug"]) or {}).get("version", "v01")),
            "status": st.session_state.get(f"smrs_video_status_{scene['slug']}", (files["videos"].get(scene["slug"]) or {}).get("status", "final")),
        }
        for scene in SCENES
    }
    video_prompts = build_video_prompts(product_handle, product_title, sport_category, video_meta)
    with st.container(border=True):
        _step_header("5. Export Content Pack", True)
        st.caption("Export all files, prompts, videos, and instructions into one VA-ready ZIP.")

        if st.button("Create Reels ZIP", key="smrs_create_zip", type="primary", use_container_width=True):
            zip_path = build_social_media_reels_zip(
                _run_dir(state),
                product_handle,
                product_title,
                sport_category,
                state,
                background_prompt,
                image_prompts,
                video_prompts,
                PACK_VERSION,
            )
            state["zip_path"] = str(zip_path)
            st.success("ZIP created.")

        zip_path = Path(state.get("zip_path") or "")
        if zip_path.exists():
            with zip_path.open("rb") as file_handle:
                st.download_button(
                    "Download Content Pack ZIP",
                    data=file_handle,
                    file_name=zip_path.name,
                    mime="application/zip",
                    key=f"smrs_download_zip_{zip_path.name}",
                    use_container_width=True,
                )
            st.caption(f"Saved locally: {zip_path}")
