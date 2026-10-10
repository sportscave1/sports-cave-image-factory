from sports_categories import sport_family
from pathlib import Path
from PIL import Image, ImageOps, ImageFile, UnidentifiedImageError
from contextlib import closing, suppress
import hashlib
import json
import logging
import os
import zipfile
import re
import shutil
import tempfile
import warnings
import threading
from datetime import datetime
from textwrap import dedent

import prompt_store

from sports_cave_prompt_blocks import append_sports_cave_prompt_blocks, prompt_includes_human_scene

try:
    import psutil
except ImportError:
    psutil = None

ImageFile.LOAD_TRUNCATED_IMAGES = True

RENDER_LIGHTWEIGHT_MODE = True
MAX_UPLOAD_MB = 20
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_MB * 1024 * 1024
MAX_LIFESTYLE_UPLOAD_MB = 15
MAX_LIFESTYLE_UPLOAD_SIZE_BYTES = MAX_LIFESTYLE_UPLOAD_MB * 1024 * 1024
MAX_LIFESTYLE_SOURCE_EDGE = 3000
MAX_SOURCE_PIXELS = 25_000_000
MAX_WORKING_EDGE = 2000
MAX_PREVIEW_EDGE = 900
MAX_STORED_RUNS = 3
MAX_EXPORT_EDGE = 1600
WEBP_EXPORT_QUALITY = 82
EXPORT_WEBP_QUALITY = WEBP_EXPORT_QUALITY
EXPORT_WEBP_METHOD = 4
EXPORT_JPG_QUALITY = 92
PREVIEW_WEBP_QUALITY = 70
PREVIEW_WEBP_METHOD = 4
TEMP_RUN_MAX_AGE_SECONDS = 6 * 60 * 60
TEMP_ROOT_ENV = "SPORTS_CAVE_TEMP_DIR"
MEMORY_LIMIT_MESSAGE = (
    "Not enough memory to complete image processing. Retry when memory is available."
)
PREPARE_ARTWORK_MEMORY_LIMIT_MESSAGE = (
    "Not enough memory to prepare the uploaded artwork. Retry when memory is available "
    "or reduce the image's pixel dimensions."
)
LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE = (
    "This uploaded image is too large. Please upload a JPG, PNG or WebP under 15 MB."
)
LIFESTYLE_UPLOAD_INVALID_MESSAGE = (
    "Cannot read the uploaded lifestyle image. Please upload a valid JPG, PNG, or WEBP file."
)
LIFESTYLE_UPLOAD_MEMORY_MESSAGE = (
    "Memory limit reached while processing the lifestyle image. "
    "Clear and reselect the image to retry when memory is available."
)
LIFESTYLE_MEMORY_RESERVE_BYTES = 16 * 1024 * 1024
_lifestyle_processing_lock = threading.Lock()
IMAGE_DIMENSIONS_MESSAGE = "Image dimensions exceed the supported limit of 25 million pixels. Reduce the pixel dimensions."
MEMORY_TELEMETRY_MESSAGE = "Cannot determine the container's available memory safely. Retry after memory monitoring is restored."


def _cgroup_memory_headroom(proc_root=Path("/proc/self")):
    """Read this process's mounted v1/v2 limits, including constrained parents.

    Host available RAM alone is not a container budget. Resolve mount roots
    rather than assuming Render exposes a particular /sys/fs/cgroup layout.
    """
    try:
        memberships = [line.split(":", 2) for line in (proc_root / "cgroup").read_text().splitlines()]
        mounts = (proc_root / "mountinfo").read_text().splitlines()
    except OSError:
        return None
    headrooms = []
    for line in mounts:
        before, separator, after = line.partition(" - ")
        fields, fs = before.split(), after.split()
        if not separator or len(fields) < 5 or len(fs) < 3:
            continue
        if fs[0] == "cgroup2":
            members = [path for _, controllers, path in memberships if not controllers]
            limit_name, usage_name = "memory.max", "memory.current"
        elif fs[0] == "cgroup" and "memory" in fs[2].split(","):
            members = [path for _, controllers, path in memberships if "memory" in controllers.split(",")]
            limit_name, usage_name = "memory.limit_in_bytes", "memory.usage_in_bytes"
        else:
            continue
        unescape = lambda value: re.sub(r"\\([0-7]{3})", lambda match: chr(int(match[1], 8)), value)
        root, mount = Path(unescape(fields[3])), Path(unescape(fields[4]))
        for member in members:
            try:
                relative = Path(member).relative_to(root)
            except ValueError:
                # A cgroup namespace can present membership as '/' while the
                # mount root still names the host-side group.
                relative = Path(".")
            node = mount / relative
            while node.is_relative_to(mount):
                try:
                    raw_limit = (node / limit_name).read_text().strip()
                    if raw_limit != "max":
                        limit = int(raw_limit)
                        # v1 uses a near-LONG_MAX sentinel for no limit.
                        if 0 < limit < (1 << 60):
                            try:
                                used = int((node / usage_name).read_text().strip())
                            except OSError as error:
                                # A known container limit must never fall back
                                # to host RAM just because usage is unreadable.
                                raise RuntimeError(MEMORY_TELEMETRY_MESSAGE) from error
                            headrooms.append(max(0, limit - used))
                except FileNotFoundError:
                    pass
                except (OSError, ValueError) as error:
                    raise RuntimeError(MEMORY_TELEMETRY_MESSAGE) from error
                if node == mount:
                    break
                node = node.parent
    return min(headrooms) if headrooms else None


def lifestyle_available_memory_bytes():
    available = []
    if psutil is not None:
        try:
            available.append(max(0, int(psutil.virtual_memory().available)))
        except (OSError, AttributeError):
            pass
    container_available = _cgroup_memory_headroom()
    if container_available is not None:
        available.append(container_available)
    return min(available) if available else None


def validate_lifestyle_processing_memory(width, height):
    return validate_processing_memory(width, height, LIFESTYLE_UPLOAD_MEMORY_MESSAGE)


def validate_image_dimensions(width, height):
    if width <= 0 or height <= 0 or width * height > MAX_SOURCE_PIXELS:
        raise ValueError(IMAGE_DIMENSIONS_MESSAGE)


def validate_processing_memory(width, height, message=PREPARE_ARTWORK_MEMORY_LIMIT_MESSAGE):
    pixels = width * height
    validate_image_dimensions(width, height)
    # Up to four 4-byte pixel buffers for decode/orientation/RGB/resampling,
    # two bounded export buffers, plus codec workspace and a separate reserve.
    export_edge = min(MAX_EXPORT_EDGE, width, height)
    required = pixels * 16 + export_edge * export_edge * 8 + 16 * 1024 * 1024
    available = lifestyle_available_memory_bytes()
    logging.info("MOCKUPS_MEMORY dimensions=%sx%s estimated_bytes=%s reserve_bytes=%s available_bytes=%s rss_mb=%s",
                 width, height, required, LIFESTYLE_MEMORY_RESERVE_BYTES, available, get_memory_usage_mb())
    if available is not None and available < required + LIFESTYLE_MEMORY_RESERVE_BYTES:
        raise MemoryLimitExceededError(message)
    return required


class MemoryLimitExceededError(RuntimeError):
    pass


def get_memory_usage_mb():
    if psutil is None:
        return None

    process = psutil.Process(os.getpid())
    return process.memory_info().rss / 1024 / 1024


def log_memory(stage):
    memory_usage = get_memory_usage_mb()
    if memory_usage is None:
        print(f"MEMORY MB: unavailable | {stage}")
        return None

    print(f"MEMORY MB: {memory_usage:.1f} | {stage}")
    return memory_usage


def ensure_memory_available(stage, error_message=MEMORY_LIMIT_MESSAGE):
    # Compatibility for stage markers: RSS is telemetry, not an allocation budget.
    # Image allocations are checked using dimensions and runtime headroom.
    return log_memory(stage)


def close_image(image):
    if image is None:
        return

    try:
        image.close()
    except Exception:
        pass


class BorrowedImageStream:
    """Let Pillow close its image without closing Streamlit's retryable upload."""
    def __init__(self, stream):
        self.stream = stream

    def read(self, *args):
        return self.stream.read(*args)

    def seek(self, *args):
        return self.stream.seek(*args)

    def tell(self):
        return self.stream.tell()

    def close(self):
        pass


def save_image_atomic(image, path, **options):
    """Only publish a preview once its encoder has completed successfully."""
    path = Path(path)
    with tempfile.TemporaryDirectory(dir=path.parent, prefix="preview-stage-") as staging:
        staged = Path(staging) / path.name
        image.save(staged, **options)
        os.replace(staged, path)


def collect_garbage(stage, error_message=MEMORY_LIMIT_MESSAGE):
    ensure_memory_available(stage, error_message=error_message)


def app_temp_root():
    configured = str(os.getenv(TEMP_ROOT_ENV, "") or "").strip()
    if configured:
        root = Path(configured)
    else:
        root = Path(tempfile.gettempdir()) / "sports-cave-image-factory"
    root.mkdir(parents=True, exist_ok=True)
    return root


def create_temp_run_parent():
    root = app_temp_root() / "mockup-runs"
    root.mkdir(parents=True, exist_ok=True)
    return root


def is_path_within_directory(path, directory):
    try:
        resolved_path = Path(path).resolve()
        resolved_directory = Path(directory).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved_path == resolved_directory or resolved_directory in resolved_path.parents


def cleanup_stale_temp_runs(temp_root=None, *, max_age_seconds=TEMP_RUN_MAX_AGE_SECONDS, max_delete=20):
    root = Path(temp_root) if temp_root else create_temp_run_parent()
    if not root.exists():
        return []
    if not is_path_within_directory(root, app_temp_root()):
        raise ValueError("Refusing to clean a directory outside the app-owned temp root.")

    cutoff = datetime.now().timestamp() - max(60, int(max_age_seconds or TEMP_RUN_MAX_AGE_SECONDS))
    deleted = []
    for child in sorted(root.iterdir(), key=lambda path: path.stat().st_mtime if path.exists() else 0):
        if len(deleted) >= max(1, int(max_delete or 1)):
            break
        if not child.is_dir() or not child.name.startswith("mockup-run-"):
            continue
        try:
            if child.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(child)
            deleted.append(child)
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return deleted


def validate_lifestyle_upload_size(image_file):
    file_size = getattr(image_file, "size", None)
    if file_size is not None and file_size > MAX_LIFESTYLE_UPLOAD_SIZE_BYTES:
        raise ValueError(LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE)

    if file_size is not None and file_size <= 0:
        raise ValueError(LIFESTYLE_UPLOAD_INVALID_MESSAGE)


def get_uploaded_image_suffix(image_file):
    suffix = Path(getattr(image_file, "name", "")).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix

    return ".jpg"


def copy_uploaded_image_to_temp(image_file, temp_dir):
    validate_lifestyle_upload_size(image_file)
    temp_path = Path(temp_dir) / f"uploaded-lifestyle{get_uploaded_image_suffix(image_file)}"

    if hasattr(image_file, "seek"):
        image_file.seek(0)

    try:
        with temp_path.open("wb") as destination:
            shutil.copyfileobj(image_file, destination, length=1024 * 1024)

        # This is the unchanged source file, before any decoding or conversion.
        if temp_path.stat().st_size > MAX_LIFESTYLE_UPLOAD_SIZE_BYTES:
            raise ValueError(LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE)
        if temp_path.stat().st_size == 0:
            raise ValueError(LIFESTYLE_UPLOAD_INVALID_MESSAGE)
    finally:
        if hasattr(image_file, "seek"):
            image_file.seek(0)

    return temp_path


def resize_lifestyle_source_if_needed(image):
    longest_side = max(image.size)
    if longest_side <= MAX_LIFESTYLE_SOURCE_EDGE:
        return False

    image.thumbnail(
        (MAX_LIFESTYLE_SOURCE_EDGE, MAX_LIFESTYLE_SOURCE_EDGE),
        Image.LANCZOS,
    )
    return True


def log_image_details(stage, image_format, width, height, file_size_bytes):
    file_size_mb = file_size_bytes / 1024 / 1024 if file_size_bytes else 0
    print(
        f"[image_factory] {stage}: format={image_format or 'unknown'} "
        f"size={width}x{height} pixels={width * height} file_mb={file_size_mb:.2f}"
    )


def load_artwork_image(image_path):
    try:
        with Image.open(image_path) as image:
            validate_processing_memory(*image.size)
            ImageOps.exif_transpose(image, in_place=True)
            return image.convert("RGB")
    except UnidentifiedImageError as error:
        raise RuntimeError(
            f"Cannot open artwork file {image_path}. Please upload a valid JPG, PNG, or WEBP image."
        ) from error


# -----------------------------------
# TEMPLATE FINDER
# -----------------------------------

def find_file(preferred_name, fallback_patterns, folder):
    preferred = folder / preferred_name

    if preferred.exists():
        return preferred

    for pattern in fallback_patterns:
        matches = list(folder.glob(pattern))
        if matches:
            return matches[0]

    raise FileNotFoundError(
        f"Could not find {preferred_name}. Checked folder: {folder}"
    )


# -----------------------------------
# PLACEMENT RULES
# -----------------------------------

MASTER_FRAMED_BOX = (84, 204, 824, 583)

UNFRAMED_ART_BOX = (84, 210, 824, 580)

SIZE_GUIDE_BOXES = {
    "x_large": (633, 147, 655, 462),
    "large":   (101, 248, 426, 300),
    "medium":  (115, 812, 289, 204),
    "small":   (567, 863, 179, 126),
}

LIFESTYLE_REFERENCE_FILE_NAME = "00-upload-this-black-framed-reference.webp"
SHOPIFY_UPLOADS_FOLDER_NAME = "shopify-uploads"
SOCIALS_FOLDER_NAME = "socials"
PROMPTS_FOLDER_NAME = "chatgpt-prompts"
WEBP_CACHE_FOLDER_NAME = "_webp-cache"
JPG_CACHE_FOLDER_NAME = "_jpg-cache"
PREVIEW_FOLDER_NAME = "previews"
ASSET_CATEGORY_CORE = "core_images"
ASSET_CATEGORY_SOCIAL = "social_mockups"
ASSET_CATEGORY_PRODUCT = "product_images"
ZIP_GROUP_ALIASES = {
    "core": ASSET_CATEGORY_CORE,
    "core_images": ASSET_CATEGORY_CORE,
    "generated": ASSET_CATEGORY_CORE,
    "social": ASSET_CATEGORY_SOCIAL,
    "social_mockups": ASSET_CATEGORY_SOCIAL,
    "lifestyle": ASSET_CATEGORY_SOCIAL,
    "product_page": ASSET_CATEGORY_PRODUCT,
    "product_images": ASSET_CATEGORY_PRODUCT,
    "product": ASSET_CATEGORY_PRODUCT,
    "reels": ASSET_CATEGORY_SOCIAL,
}

LIFESTYLE_IMAGE_VARIANTS = {
    "01-man-cave-prompt.txt": "man-cave-lifestyle",
    "02-office-prompt.txt": "office-lifestyle",
    "03-living-room-prompt.txt": "living-room-lifestyle",
    "04-close-up-wall-prompt.txt": "close-up-wall-lifestyle",
    "05-limited-edition-detail-prompt.txt": "limited-edition-detail-lifestyle",
    "06-instant-experience-cover-prompt.txt": "instant-experience-cover-lifestyle",
    "07-home-sports-bar-prompt.txt": "home-sports-bar-lifestyle",
    "08-collector-display-room-prompt.txt": "collector-display-room-lifestyle",
    "09-luxury-entry-wall-prompt.txt": "luxury-entry-wall-lifestyle",
    "10-private-club-lounge-prompt.txt": "private-club-lounge-lifestyle",
    "11-wall-upgrade-moment-prompt.txt": "wall-upgrade-moment-lifestyle",
    "12-fireplace-feature-wall-prompt.txt": "fireplace-feature-wall-lifestyle",
    "13-premium-bedroom-prompt.txt": "premium-bedroom-lifestyle",
    "14-man-cave-pool-table-prompt.txt": "man-cave-pool-table-lifestyle",
    "15-premium-tool-shed-workshop-prompt.txt": "premium-tool-shed-workshop-lifestyle",
    "16-man-cave-with-pool-table-prompt.txt": "man-cave-with-pool-table-lifestyle",
    "17-architectural-loft-prompt.txt": "architectural-loft-statement-wall-lifestyle",
    "16-man-cave-reel-prompt.txt": "16-man-cave-reel",
    "17-living-room-reel-prompt.txt": "17-living-room-reel",
    "18-office-reel-prompt.txt": "18-office-reel",
    "19-home-sports-bar-reel-prompt.txt": "19-home-sports-bar-reel",
    "20-collector-display-room-reel-prompt.txt": "20-collector-display-room-reel",
}

CLOSE_UP_WALL_PROMPT_FILENAME = "04-close-up-wall-prompt.txt"

PRODUCT_PAGE_PROMPT_FILENAMES = {
    "01-man-cave-prompt.txt",
    "02-office-prompt.txt",
    "03-living-room-prompt.txt",
}

# Canonical product gallery contract.  The five generated images keep their
# historical identities and the three product-page room uploads sit between the
# featured Black image and Size Guide, matching the established Shopify order.
PRODUCT_IMAGE_SLOT_SPECS = (
    {
        "slot_id": "black-frame",
        "asset_key": "black",
        "image_type": "black_frame",
        "display_label": "Black Framed",
        "sort_position": 1,
        "zip_group": ASSET_CATEGORY_CORE,
        "filename_suffix": "black-framed-{sport}-wall-art",
        "legacy_keys": ("black-framed", "black_framed", "black frame"),
        "shopify_alt_text_source": "Black framed product image",
    },
    {
        "slot_id": "man-cave",
        "asset_key": "lifestyle::01-man-cave-prompt.txt",
        "prompt_filename": "01-man-cave-prompt.txt",
        "image_type": "man_cave",
        "display_label": "Man Cave",
        "sort_position": 2,
        "zip_group": ASSET_CATEGORY_PRODUCT,
        "filename_suffix": "black-framed-{sport}-man-cave-lifestyle",
        "legacy_keys": ("man-cave", "man_cave", "man cave", "lifestyle::01", "01-man-cave"),
        "shopify_alt_text_source": "Man Cave lifestyle room",
    },
    {
        "slot_id": "office",
        "asset_key": "lifestyle::02-office-prompt.txt",
        "prompt_filename": "02-office-prompt.txt",
        "image_type": "office",
        "display_label": "Office",
        "sort_position": 3,
        "zip_group": ASSET_CATEGORY_PRODUCT,
        "filename_suffix": "black-framed-{sport}-office-lifestyle",
        "legacy_keys": ("office", "lifestyle::02", "02-office"),
        "shopify_alt_text_source": "Office lifestyle room",
    },
    {
        "slot_id": "living-room",
        "asset_key": "lifestyle::03-living-room-prompt.txt",
        "prompt_filename": "03-living-room-prompt.txt",
        "image_type": "living_room",
        "display_label": "Living Room",
        "sort_position": 4,
        "zip_group": ASSET_CATEGORY_PRODUCT,
        "filename_suffix": "black-framed-{sport}-living-room-lifestyle",
        "legacy_keys": ("living-room", "living_room", "living room", "lifestyle::03", "03-living-room"),
        "shopify_alt_text_source": "Living Room lifestyle room",
    },
    {
        "slot_id": "size-guide",
        "asset_key": "size-guide",
        "image_type": "size_guide",
        "display_label": "Size Guide",
        "sort_position": 5,
        "zip_group": ASSET_CATEGORY_CORE,
        "filename_suffix": "framed-{sport}-wall-art-sizing-guide",
        "legacy_keys": ("size_guide", "size guide", "sizing-guide"),
        "shopify_alt_text_source": "Framed wall art size guide",
    },
    {
        "slot_id": "oak-frame",
        "asset_key": "oak",
        "image_type": "oak_frame",
        "display_label": "Oak Framed",
        "sort_position": 6,
        "zip_group": ASSET_CATEGORY_CORE,
        "filename_suffix": "oak-framed-{sport}-wall-art",
        "legacy_keys": ("oak-framed", "oak_framed", "oak frame"),
        "shopify_alt_text_source": "Oak framed product image",
    },
    {
        "slot_id": "white-frame",
        "asset_key": "white",
        "image_type": "white_frame",
        "display_label": "White Framed",
        "sort_position": 7,
        "zip_group": ASSET_CATEGORY_CORE,
        "filename_suffix": "white-framed-{sport}-wall-art",
        "legacy_keys": ("white-framed", "white_framed", "white frame"),
        "shopify_alt_text_source": "White framed product image",
    },
    {
        "slot_id": "unframed",
        "asset_key": "unframed",
        "image_type": "unframed",
        "display_label": "Unframed",
        "sort_position": 8,
        "zip_group": ASSET_CATEGORY_CORE,
        "filename_suffix": "unframed-{sport}-wall-art",
        "legacy_keys": ("un-framed", "unframed print"),
        "shopify_alt_text_source": "Unframed product image",
    },
)
PRODUCT_IMAGE_REQUIRED_COUNT = len(PRODUCT_IMAGE_SLOT_SPECS)
PRODUCT_IMAGE_MANIFEST_FILENAME = "product-image-manifest.json"
REELS_PROMPT_FILENAMES = {
    "16-man-cave-reel-prompt.txt",
    "17-living-room-reel-prompt.txt",
    "18-office-reel-prompt.txt",
    "19-home-sports-bar-reel-prompt.txt",
    "20-collector-display-room-reel-prompt.txt",
}

from mockup_product_prompts import TEMPLATE as PRODUCT_PAGE_PROMPT_TEMPLATE

LIFESTYLE_PROMPT_SPECS = [
    ("01-man-cave-prompt.txt", "Man Cave", PRODUCT_PAGE_PROMPT_TEMPLATE),
    ("02-office-prompt.txt", "Office", PRODUCT_PAGE_PROMPT_TEMPLATE),
    ("03-living-room-prompt.txt", "Living Room", PRODUCT_PAGE_PROMPT_TEMPLATE),
]

# Ads uses this foundation independently of the retired Mockups social cards.
CLOSE_UP_WALL_PROMPT_FOUNDATION = """Using the uploaded artwork and frame as the exact reference, create a 1024 x 1024 ultra-realistic close-up lifestyle mockup. Use a different angle and different wall colour so it looks like a different house and camera angle to the previous generation.
The artwork and frame must remain exactly the same as the uploaded image.
Do not redesign the artwork.
Do not change the colours.
Do not change the layout.
Do not change the text.
Do not change the badge.
Do not crop the artwork.
Do not blur the artwork.
Do not stretch, warp, bend, squash, or distort the frame or artwork.
Create a close-up shot of the framed artwork mounted on a premium wall, as if it is hanging in someone's real home.
The frame should be the hero of the image.
No room decor.
No furniture.
No shelves.
No plants.
No lamps.
No extra wall art.
No people.
No logos.
No added text.
No clutter.
Use only the framed artwork on a premium textured wall.
The wall should feel realistic and high-end:
matte plaster, soft concrete, warm beige, off-white, charcoal, muted taupe, or clean gallery-style painted wall.
Use a wall colour that makes the black frame and artwork stand out.
Camera angle:
close-up view.
Slight natural angle from one side.
The angle should feel premium and realistic, like a professional product photo.
Do not over-angle it.
Do not create heavy perspective distortion.
The frame and artwork must keep correct landscape proportions.
Frame realism:
premium black timber frame.
Realistic depth.
Sharp corners.
Clean edges.
Subtle timber texture.
Believable thickness.
Natural shadow behind the frame.
Glazing realism:
show premium clear glass reflections on the existing transparent front surface, preserving verified source construction; never add a pane to known unglazed products.
The glazing must have soft, subtle yet visible room-based reflections and restrained premium highlights.
The glare must look real, controlled, and high-end.
Do not let the glare hide the artwork.
Do not add fake glow.
Lighting:
premium cinematic lighting.
Soft natural light from one side.
Controlled highlights.
Realistic shadow falloff behind and below the frame.
The frame should look physically mounted on the wall, not pasted on.
Composition:
square 1024 x 1024 canvas.
Close enough to show the frame quality, glass, shadows, and artwork detail.
Leave a small amount of premium wall space around the frame for realism.
The final image should feel clean, expensive, sharp, and believable.
Final result:
photorealistic close-up wall mockup of the exact supplied Sports Cave artwork and black frame, with real glass glare, premium shadows, realistic wall texture, and no distractions."""


def get_lifestyle_prompt_spec(prompt_filename):
    prompt_filename = Path(prompt_filename).name
    for filename, title, prompt_body in LIFESTYLE_PROMPT_SPECS:
        if filename == prompt_filename:
            return {"filename": filename, "title": title,
                    "prompt": get_lifestyle_prompt_text(filename, prompt_body, local_only=True)}
    return {}


def get_close_up_wall_prompt_foundation():
    return get_lifestyle_prompt_text(CLOSE_UP_WALL_PROMPT_FILENAME, CLOSE_UP_WALL_PROMPT_FOUNDATION, local_only=True).strip()


LEGACY_MOCKUPS_REEL_PROMPT_SPECS = [
    (
        "16-man-cave-reel-prompt.txt",
        "Man Cave Reel",
        dedent(
            """
            Using the uploaded Sports Cave artwork and black landscape frame as the exact reference, create a 1080 x 1920 vertical 9:16 ultra-realistic lifestyle mockup for Meta/Facebook/Instagram Reels.

            This image must feel like the artwork belongs in a serious fan’s premium man cave.

            Keep the exact same artwork and exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, signatures, crop, or internal composition.
            Do not blur, stretch, warp, bend, squash, or distort the artwork or frame.

            Place the framed artwork realistically mounted on the wall of a premium man cave / media room.

            The space should feel masculine, cinematic, collector-driven, clean, and expensive.
            Use a refined palette: charcoal walls, matte black details, warm timber, soft beige, leather textures, subtle concrete or plaster wall finish.

            Include only subtle realistic decor: a blurred leather chair edge, low media cabinet, soft TV glow, simple shelf, or warm floor lamp.
            Keep decor minimal and out of focus.
            The framed artwork must remain the hero.

            Do not add people.
            Do not add neon signs.
            Do not add random sports logos.
            Do not add beer branding.
            Do not add extra wall art.
            Do not add text overlays.
            Do not add watermarks.
            Do not add clutter.

            Frame realism: premium black timber frame, realistic depth, sharp corners, subtle timber texture, clean edges, believable wall mounting, natural shadows behind and below the frame.

            Glass realism: add realistic glass over the artwork with soft room reflections and subtle premium glare.
            The glare must feel natural and expensive but must not hide the artwork.

            Lighting: premium cinematic evening lighting, warm highlights, controlled shadows, soft ambient glow, realistic shadow falloff on the wall.

            Vertical Reels composition:
            1080 x 1920 vertical canvas.
            Keep the framed artwork in the central safe area.
            Do not place the artwork too low where Reels captions/buttons would cover it.
            The frame should take strong visual space, roughly 70–85% of the image width.
            Leave tasteful negative space above and below for mobile viewing.
            Use a slight natural camera angle, but preserve correct landscape proportions.

            Final result:
            a photorealistic premium man cave Reels mockup with the exact uploaded Sports Cave framed artwork, realistic glass, strong wall presence, cinematic lighting, and a feeling that this belongs in a real fan’s cave.
            """
        ).strip(),
    ),
    (
        "17-living-room-reel-prompt.txt",
        "Living Room Reel",
        dedent(
            """
            Using the uploaded Sports Cave artwork and black landscape frame as the exact reference, create a 1080 x 1920 vertical 9:16 ultra-realistic lifestyle mockup for Meta/Facebook/Instagram Reels.

            This image must show the artwork as a premium statement piece inside a refined modern living room.

            Keep the exact same artwork and exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, signatures, crop, or internal composition.
            Do not blur, stretch, warp, bend, squash, or distort the artwork or frame.

            Place the framed artwork mounted at realistic eye-level height on a premium living room wall.

            The room should feel clean, masculine, expensive, and believable.
            Use a warm neutral home interior: soft greige wall, matte plaster, warm beige, off-white, muted taupe, soft concrete, or warm grey.

            Include subtle decor only: part of a premium sofa, low side table, floor lamp edge, soft rug texture, or minimal foreground object.
            Keep everything understated.
            The artwork must be the clear hero.

            Do not add people.
            Do not add random sports logos.
            Do not add extra wall art.
            Do not add neon signs.
            Do not add text overlays.
            Do not add watermarks.
            Do not add clutter.

            Frame realism: premium black timber frame, realistic thickness, sharp corners, subtle texture, clean edges, believable wall mounting.

            Glass realism: add realistic glass over the artwork with soft natural reflections and subtle premium glare.
            The glare should feel real and controlled without covering important artwork detail.

            Lighting: soft natural daylight mixed with warm interior highlights.
            Premium cinematic shadows behind and below the frame.
            The artwork should look physically mounted, not pasted onto the wall.

            Vertical Reels composition:
            1080 x 1920 vertical canvas.
            Frame sits in the central safe area and remains fully visible.
            Do not crop the frame.
            Do not place the frame too low.
            Use the vertical room height to show scale, wall texture, and premium home atmosphere.
            The framed artwork should take roughly 65–80% of the image width.
            Use a fresh editorial camera angle with slight depth, but keep the landscape frame proportions accurate.

            Final result:
            a photorealistic premium living room Reels mockup with the exact uploaded Sports Cave framed artwork, realistic glass, warm natural light, believable scale, and a high-end home feel that makes buyers imagine it on their own wall.
            """
        ).strip(),
    ),
    (
        "18-office-reel-prompt.txt",
        "Office Reel",
        dedent(
            """
            Using the uploaded Sports Cave artwork and black landscape frame as the exact reference, create a 1080 x 1920 vertical 9:16 ultra-realistic lifestyle mockup for Meta/Facebook/Instagram Reels.

            This image must place the artwork in a premium home office or private study, where it feels like a daily reminder of greatness, discipline, rivalry, and identity.

            Keep the exact same artwork and exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, signatures, crop, or internal composition.
            Do not blur, stretch, warp, bend, squash, or distort the artwork or frame.

            Place the framed artwork mounted on the wall inside a clean premium office.

            The office should feel refined, masculine, focused, expensive, and realistic.
            Use a mature interior palette: matte olive-grey, charcoal, warm beige, off-white, soft plaster, concrete, walnut timber, black metal details.

            Include subtle office details only: desk edge, premium chair silhouette, bookshelf blur, laptop edge, warm desk lamp, or minimal side table.
            Keep the space clean and professional.
            The framed artwork must be the emotional hero.

            Do not add people.
            Do not add random sports logos.
            Do not add extra wall art.
            Do not add text overlays.
            Do not add watermarks.
            Do not add clutter.
            Do not make it look like a corporate stock office.

            Frame realism: premium black timber frame, real depth, sharp corners, subtle texture, realistic wall mounting, natural shadowing.

            Glass realism: add realistic glass over the artwork with soft window reflections and controlled premium glare.
            The reflections must not block the artwork.

            Lighting: premium cinematic office lighting.
            Soft daylight from one side.
            Warm desk or wall light accents.
            Clean shadows behind and below the frame.
            The scene should feel productive, calm, and collector-driven.

            Vertical Reels composition:
            1080 x 1920 vertical canvas.
            Keep the artwork in the central safe zone.
            Do not place the artwork too low.
            Show enough vertical wall and office context to make the room feel real.
            Frame should take roughly 65–80% of image width.
            Use a slight natural side angle with accurate landscape proportions.

            Final result:
            a photorealistic premium office Reels mockup using the exact uploaded Sports Cave framed artwork, realistic glass, premium shadows, refined office styling, and a clear feeling that this piece belongs where serious fans work and think.
            """
        ).strip(),
    ),
    (
        "19-home-sports-bar-reel-prompt.txt",
        "Home Sports Bar Reel",
        dedent(
            """
            Using the uploaded Sports Cave artwork and black landscape frame as the exact reference, create a 1080 x 1920 vertical 9:16 ultra-realistic lifestyle mockup for Meta/Facebook/Instagram Reels.

            This image must make the artwork feel like the centrepiece of a premium home sports bar where fans watch finals, rivalries, title fights, race days, derby nights, or big match moments.

            Keep the exact same artwork and exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, signatures, crop, or internal composition.
            Do not blur, stretch, warp, bend, squash, or distort the artwork or frame.

            Place the framed artwork mounted behind or near a premium home bar as the main statement piece.

            The room should feel cinematic, masculine, clean, expensive, and fan-owned.
            Use refined home bar details: dark stone benchtop, matte black cabinetry, warm timber shelving, subtle glassware, premium stools, soft bar lighting, faint out-of-focus TV glow.

            Keep all decor subtle and secondary.
            The artwork must dominate visual attention.

            Do not add people.
            Do not add neon signs.
            Do not add beer branding.
            Do not add recognisable team logos.
            Do not add random sports logos.
            Do not add extra wall art.
            Do not add text overlays.
            Do not add watermarks.
            Do not make it look like a commercial pub.

            Frame realism: premium black timber frame, realistic depth, sharp corners, subtle texture, believable wall mounting, clean shadows.

            Glass realism: add realistic glass over the artwork with warm bar-light reflections and subtle premium glare.
            The glare must feel believable and must not hide the artwork.

            Lighting: cinematic evening lighting.
            Warm practical lights.
            Soft highlights on glass and frame edges.
            Deep but clean shadows.
            Premium contrast without making the artwork too dark.

            Vertical Reels composition:
            1080 x 1920 vertical canvas.
            Keep the framed artwork fully visible in the central safe area.
            Do not place it too low.
            Use the vertical space to show the bar atmosphere above and below the frame.
            Frame should take roughly 60–75% of image width.
            Use a slight natural camera angle, but keep the landscape frame accurate and undistorted.

            Final result:
            a photorealistic premium home sports bar Reels mockup with the exact uploaded Sports Cave framed artwork, realistic glass, warm cinematic lighting, subtle bar atmosphere, and strong “that belongs in my space” collector appeal.
            """
        ).strip(),
    ),
    (
        "20-collector-display-room-reel-prompt.txt",
        "Collector Display Room Reel",
        dedent(
            """
            Using the uploaded Sports Cave artwork and black landscape frame as the exact reference, create a 1080 x 1920 vertical 9:16 ultra-realistic lifestyle mockup for Meta/Facebook/Instagram Reels.

            This image must make the artwork feel like a prized limited-edition collector piece inside a serious fan’s private display room.

            Keep the exact same artwork and exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, signatures, crop, or internal composition.
            Do not blur, stretch, warp, bend, squash, or distort the artwork or frame.

            Place the framed artwork inside a premium private collector display room.

            The space should feel exclusive, cinematic, masculine, controlled, and expensive.
            Use a refined display environment: dark matte walls, warm timber or black shelving, glass display cabinet, subtle memorabilia silhouettes, low display lighting, premium spotlights, clean negative space.

            Collector items must stay subtle, tasteful, and out of focus.
            They should add atmosphere without competing with the framed artwork.
            The framed artwork must feel like the prized piece in the room.

            Do not add people.
            Do not add recognisable team logos.
            Do not add random athlete photos.
            Do not add extra wall art.
            Do not add text overlays.
            Do not add watermarks.
            Do not make the room cluttered.
            Do not make it look like a retail shop.

            Frame realism: premium black timber frame, realistic depth, sharp corners, subtle texture, clean edges, believable wall mounting, natural shadows.

            Glass realism: add realistic glass over the artwork with soft reflections from collector-room lighting.
            The glare should feel subtle, premium, and natural.
            Do not let reflections obscure the artwork.

            Lighting: controlled collector-room spotlight on the artwork.
            Soft warm highlights.
            Deep clean shadows.
            Cinematic black, charcoal, warm timber and gold-accent atmosphere.
            The scene should communicate scarcity, ownership, pride, and collector value.

            Vertical Reels composition:
            1080 x 1920 vertical canvas.
            Keep the framed artwork in the central safe area.
            Do not place it too low.
            Use vertical space to show the collector-room mood without shrinking the artwork too much.
            Frame should take roughly 65–80% of image width.
            Use a slightly angled premium interior photography perspective, but keep frame proportions accurate and undistorted.

            Final result:
            a photorealistic premium collector display room Reels mockup with the exact uploaded Sports Cave framed artwork, realistic glass, controlled cinematic lighting, subtle memorabilia atmosphere, and strong limited-edition collector energy.
            """
        ).strip(),
    ),
]


# -----------------------------------
# HELPERS
# -----------------------------------

def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def fit_artwork_to_box(artwork, box_width, box_height):
    return ImageOps.fit(
        artwork,
        (box_width, box_height),
        method=Image.LANCZOS,
        centering=(0.5, 0.5),
    )


def resize_for_export(image, max_edge=MAX_EXPORT_EDGE):
    if max(image.size) <= max_edge:
        return image.copy()

    resized_image = image.copy()
    resized_image.thumbnail((max_edge, max_edge), Image.LANCZOS)
    return resized_image


def prepare_working_artwork(image_path, upload_dir):
    with _lifestyle_processing_lock:
        return _prepare_working_artwork(image_path, upload_dir)


def _prepare_working_artwork(image_path, upload_dir):
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_path = Path(image_path)
    working_path = upload_dir / "working-artwork.webp"
    working_image = None
    stage = "metadata"
    try:
        with tempfile.TemporaryDirectory(dir=upload_dir, prefix="prepare-") as staging:
            staged_path = Path(staging) / working_path.name
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image_path) as source:
                    size = image_path.stat().st_size
                    logging.info("MOCKUPS_ARTWORK stage=%s dimensions=%sx%s mode=%s upload_bytes=%s",
                                 stage, *source.size, source.mode, size)
                    if size > MAX_UPLOAD_SIZE_BYTES:
                        raise ValueError("Artwork exceeds the 20 MB upload file-size limit.")
                    if source.format not in {"JPEG", "PNG", "WEBP"}:
                        raise ValueError("Upload a valid JPG, PNG, or WebP image.")
                    validate_image_dimensions(*source.size)
                    if source.format == "JPEG":
                        source.draft("RGB", (MAX_WORKING_EDGE, MAX_WORKING_EDGE))
                    validate_processing_memory(*source.size)
                    stage = "decode/resize/orient"
                    source.thumbnail((MAX_WORKING_EDGE, MAX_WORKING_EDGE), Image.LANCZOS, reducing_gap=3.0)
                    ImageOps.exif_transpose(source, in_place=True)
                    working_image = source if source.mode in {"RGB", "RGBA"} else source.convert(
                        "RGBA" if "transparency" in source.info else "RGB")
                    stage = "working export"
                    working_image.save(staged_path, format="WEBP", quality=EXPORT_WEBP_QUALITY,
                                       method=EXPORT_WEBP_METHOD)
            stage = "commit"
            os.replace(staged_path, working_path)
    except (MemoryError, MemoryLimitExceededError) as error:
        logging.exception("MOCKUPS_ARTWORK failed stage=%s rss_mb=%s", stage, get_memory_usage_mb())
        raise MemoryLimitExceededError(PREPARE_ARTWORK_MEMORY_LIMIT_MESSAGE) from error
    except (Image.DecompressionBombWarning, Image.DecompressionBombError) as error:
        raise ValueError(IMAGE_DIMENSIONS_MESSAGE) from error
    except UnidentifiedImageError as error:
        raise ValueError("Upload a valid JPG, PNG, or WebP image.") from error
    finally:
        close_image(working_image)
    return working_path



def create_preview_file(source_image_path, preview_dir, preview_name):
    preview_dir = Path(preview_dir)
    preview_dir.mkdir(parents=True, exist_ok=True)
    preview_path = preview_dir / preview_name

    ensure_memory_available(f"Before preview creation: {preview_name}")
    preview_image = load_artwork_image(source_image_path)

    try:
        preview_image.thumbnail((MAX_PREVIEW_EDGE, MAX_PREVIEW_EDGE), Image.LANCZOS)
        preview_image.save(
            preview_path,
            format="WEBP",
            quality=PREVIEW_WEBP_QUALITY,
            method=PREVIEW_WEBP_METHOD,
        )
    finally:
        close_image(preview_image)
        del preview_image
        collect_garbage(f"After preview creation: {preview_name}")

    return preview_path


def cleanup_old_runs(output_dir, keep_latest=MAX_STORED_RUNS, active_run_dir=None):
    runs_dir = Path(output_dir) / "runs"
    if not runs_dir.exists():
        return []

    active_run_dir = Path(active_run_dir).resolve() if active_run_dir else None
    run_dirs = sorted(
        [path for path in runs_dir.iterdir() if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )

    kept_runs = 0
    deleted_runs = []

    for run_dir in run_dirs:
        resolved_run_dir = run_dir.resolve()
        if active_run_dir is not None and resolved_run_dir == active_run_dir:
            kept_runs += 1
            continue

        if kept_runs < keep_latest:
            kept_runs += 1
            continue

        shutil.rmtree(run_dir)
        deleted_runs.append(run_dir)

    return deleted_runs


def build_asset_record(
    key,
    label,
    review_path=None,
    preview_path=None,
    webp_path=None,
    jpg_path=None,
    include_in_zip=True,
    asset_group="generated",
    zip_group=ASSET_CATEGORY_CORE,
    prompt_filename=None,
    export_to_shopify=True,
    export_to_socials=True,
):
    return {
        "key": key,
        "label": label,
        "review_path": review_path,
        "preview_path": preview_path,
        "webp_path": webp_path,
        "jpg_path": jpg_path,
        "include_in_zip": include_in_zip,
        "asset_group": asset_group,
        "zip_group": zip_group,
        "prompt_filename": prompt_filename,
        "export_to_shopify": export_to_shopify,
        "export_to_socials": export_to_socials,
    }


class IncompleteProductImagePackageError(ValueError):
    def __init__(self, missing_labels):
        self.missing_labels = tuple(str(label) for label in missing_labels)
        super().__init__(
            "Product image package is incomplete. Missing: "
            + ", ".join(self.missing_labels)
        )


def _manifest_identity(value):
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def _manifest_path(asset, *keys):
    for key in keys:
        value = (asset or {}).get(key)
        if value:
            return str(value)
    return ""


def _manifest_local_file(path_value):
    if not path_value:
        return None
    path = Path(path_value)
    if path.exists() and path.is_file() and path.stat().st_size > 0:
        return path
    return None


def _product_slot_asset(spec, assets):
    canonical_key = str(spec["asset_key"])
    prompt_filename = str(spec.get("prompt_filename") or "")
    identity_candidates = {
        _manifest_identity(canonical_key),
        _manifest_identity(spec["slot_id"]),
        *(_manifest_identity(value) for value in spec.get("legacy_keys") or ()),
    }
    for asset in assets:
        if str(asset.get("key") or "") == canonical_key:
            return asset
    if prompt_filename:
        for asset in assets:
            if Path(str(asset.get("prompt_filename") or "")).name == prompt_filename:
                return asset
    for asset in assets:
        if _manifest_identity(asset.get("key")) in identity_candidates:
            return asset
    filename_suffix = _manifest_identity(spec.get("filename_suffix", "").replace("{sport}", ""))
    for asset in assets:
        for path_key in ("webp_path", "jpg_path", "webp_path_dropbox_path", "jpg_path_dropbox_path"):
            filename_identity = _manifest_identity(Path(str(asset.get(path_key) or "")).stem)
            if filename_identity and filename_suffix and filename_suffix in filename_identity:
                return asset
    return {}


def build_product_image_manifest(assets, *, product_slug="product", sport_slug="sports"):
    """Return the one ordered eight-slot product image contract.

    Local and Dropbox-backed assets use the same slot identities.  Source files
    may retain legacy names; downstream outputs receive deterministic names.
    """
    product_slug = slugify(product_slug) or "product"
    sport_slug = slugify(sport_slug) or "sports"
    normalized_assets = [dict(asset or {}) for asset in assets or ()]
    entries = []
    output_names = set()
    for spec in PRODUCT_IMAGE_SLOT_SPECS:
        asset = _product_slot_asset(spec, normalized_assets)
        local_webp = _manifest_local_file(asset.get("webp_path"))
        local_jpg = _manifest_local_file(asset.get("jpg_path"))
        local_path = local_webp or local_jpg
        dropbox_path = _manifest_path(asset, "webp_path_dropbox_path", "jpg_path_dropbox_path")
        suffix = local_path.suffix.casefold() if local_path else Path(dropbox_path).suffix.casefold()
        if suffix not in {".webp", ".jpg", ".jpeg", ".png"}:
            suffix = ".webp"
        output_filename = (
            f"{product_slug}-"
            f"{str(spec['filename_suffix']).format(sport=sport_slug)}{suffix}"
        )
        filename_key = output_filename.casefold()
        if filename_key in output_names:
            raise ValueError(f"Duplicate product image output filename: {output_filename}")
        output_names.add(filename_key)
        included = bool(asset.get("include_in_zip", True)) if asset else True
        ready = bool(local_path or dropbox_path) and included
        entries.append(
            {
                "slot_id": spec["slot_id"],
                "asset_key": spec["asset_key"],
                "image_type": spec["image_type"],
                "display_label": spec["display_label"],
                "output_filename": output_filename,
                "sort_position": int(spec["sort_position"]),
                "uploaded_image_reference": str(local_path or dropbox_path or ""),
                "local_path": str(local_path) if local_path else "",
                "dropbox_path": dropbox_path,
                "inclusion_status": "included" if ready else ("excluded" if asset and not included else "missing"),
                "included": included,
                "ready": ready,
                "required": True,
                "zip_group": spec["zip_group"],
                "shopify_alt_text_source": spec["shopify_alt_text_source"],
                "prompt_filename": spec.get("prompt_filename") or "",
            }
        )
    return entries


def product_image_readiness(manifest):
    entries = sorted((dict(entry) for entry in manifest or ()), key=lambda entry: entry["sort_position"])
    missing = [entry["display_label"] for entry in entries if not entry.get("ready")]
    ready_count = len(entries) - len(missing)
    return {
        "ready_count": ready_count,
        "required_count": PRODUCT_IMAGE_REQUIRED_COUNT,
        "complete": ready_count == PRODUCT_IMAGE_REQUIRED_COUNT and len(entries) == PRODUCT_IMAGE_REQUIRED_COUNT,
        "missing_labels": missing,
    }


def require_complete_product_image_manifest(manifest):
    readiness = product_image_readiness(manifest)
    if not readiness["complete"]:
        raise IncompleteProductImagePackageError(readiness["missing_labels"])
    return sorted((dict(entry) for entry in manifest), key=lambda entry: entry["sort_position"])


def build_shopify_draft_image_payload(manifest, *, allow_incomplete=False):
    ordered = sorted((dict(entry) for entry in manifest or ()), key=lambda entry: entry["sort_position"])
    if not allow_incomplete:
        ordered = require_complete_product_image_manifest(ordered)
    return [
        {
            "slot_id": entry["slot_id"],
            "position": entry["sort_position"],
            "filename": entry["output_filename"],
            "source": entry["uploaded_image_reference"],
            "alt_text_source": entry["shopify_alt_text_source"],
        }
        for entry in ordered
        if entry.get("ready")
    ]


def merge_shopify_draft_images(draft_payload, manifest, *, allow_incomplete=False):
    """Replace only draft image data; all non-image Shopify fields are preserved."""
    merged = dict(draft_payload or {})
    merged["images"] = build_shopify_draft_image_payload(
        manifest,
        allow_incomplete=allow_incomplete,
    )
    return merged


def product_image_manifest_json(manifest):
    allowed = (
        "slot_id", "asset_key", "image_type", "display_label", "output_filename",
        "sort_position", "uploaded_image_reference", "inclusion_status", "included",
        "ready", "required", "zip_group", "shopify_alt_text_source", "prompt_filename",
    )
    return [
        {key: entry.get(key) for key in allowed}
        for entry in sorted(manifest or (), key=lambda item: item["sort_position"])
    ]


def order_assets_by_product_manifest(assets, manifest):
    """Put the eight canonical product assets first and attach slot metadata."""
    source_assets = [dict(asset or {}) for asset in assets or ()]
    assets_by_key = {str(asset.get("key") or ""): asset for asset in source_assets}
    ordered = []
    consumed_keys = set()
    for entry in sorted(manifest or (), key=lambda item: item["sort_position"]):
        asset = assets_by_key.get(str(entry.get("asset_key") or ""))
        if not asset:
            spec = next(
                (item for item in PRODUCT_IMAGE_SLOT_SPECS if item["slot_id"] == entry.get("slot_id")),
                None,
            )
            asset = _product_slot_asset(spec, source_assets) if spec else {}
        if not asset:
            continue
        asset = dict(asset)
        asset["product_slot_id"] = entry["slot_id"]
        asset["product_sort_position"] = int(entry["sort_position"])
        asset["product_output_filename"] = entry["output_filename"]
        asset["product_image_type"] = entry["image_type"]
        ordered.append(asset)
        consumed_keys.add(str(asset.get("key") or ""))
    ordered.extend(
        sorted(
            (
                asset for asset in source_assets
                if str(asset.get("key") or "") not in consumed_keys
            ),
            key=lambda item: item.get("label", item.get("key", "")).lower(),
        )
    )
    return ordered


def is_product_page_prompt_filename(prompt_filename):
    return Path(prompt_filename).name in PRODUCT_PAGE_PROMPT_FILENAMES


def should_export_asset_to_shopify(asset):
    return bool(asset.get("export_to_shopify")) and bool(asset.get("webp_path"))


def should_export_asset_to_socials(asset):
    return bool(asset.get("export_to_socials")) and bool(asset.get("jpg_path"))


def reset_directory_contents(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    for child in directory.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def create_shopify_uploads_html(
    run_dir,
    shopify_uploads_dir,
    product_name,
    sport_category,
    product_image_manifest=None,
):
    shopify_uploads_dir = Path(shopify_uploads_dir)
    ordered_image_files = []
    for entry in sorted(product_image_manifest or (), key=lambda item: item["sort_position"]):
        image_path = shopify_uploads_dir / str(entry.get("output_filename") or "")
        if entry.get("ready") and image_path.is_file():
            ordered_image_files.append((image_path, entry.get("display_label") or image_path.name))
    if not product_image_manifest:
        ordered_image_files = [
            (image_path, image_path.name)
            for image_path in sorted(shopify_uploads_dir.glob("*.webp"))
        ]
    index_path = shopify_uploads_dir / "index.html"

    html_lines = [
        "<!DOCTYPE html>",
        "<html lang=\"en\">",
        "<head>",
        "  <meta charset=\"UTF-8\">",
        f"  <title>Shopify Uploads - {product_name}</title>",
        "  <style>",
        "    body { font-family: Arial, sans-serif; background: #f7f4ee; color: #1a1a1a; padding: 24px; }",
        "    .image-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; }",
        "    .image-card { border: 1px solid #ddd; border-radius: 12px; padding: 12px; background: #fff; }",
        "    .image-card img { width: 100%; height: auto; border-radius: 8px; }",
        "    .image-card p { margin: 8px 0 0; font-size: 0.92rem; color: #333; }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>Shopify Uploads for {product_name}</h1>",
        f"  <p><strong>Sports category:</strong> {sport_category}</p>",
        "  <p>Upload these images and paste the prompt text from the Product Uploads page into ChatGPT. Use this page to copy all image filenames and make sure the new Shopify product gets the correct visuals.</p>",
        "  <div class=\"image-grid\">",
    ]

    if ordered_image_files:
        for image_file, display_label in ordered_image_files:
            html_lines.extend([
                "    <div class=\"image-card\">",
                f"      <img src=\"{image_file.name}\" alt=\"{display_label}\">",
                f"      <p>{display_label} &mdash; {image_file.name}</p>",
                "    </div>",
            ])
    else:
        html_lines.append("    <p>No Shopify upload images were found yet.</p>")

    html_lines.extend([
        "  </div>",
        "  <p style=\"margin-top:24px;font-size:0.95rem;color:#555;\">When using ChatGPT, attach these image files and copy the product prompt from the Product Uploads page. For existing products, use the Update Existing Product prompt to replace the old images with these new ones.</p>",
        "</body>",
        "</html>",
    ])

    index_path.write_text("\n".join(html_lines), encoding="utf-8")
    return index_path


def rebuild_export_folders(
    run_dir,
    assets,
    product_name="",
    sport_category="",
    *,
    product_slug="product",
    sport_slug="sports",
    product_image_manifest=None,
):
    run_dir = Path(run_dir)
    shopify_uploads_dir = run_dir / SHOPIFY_UPLOADS_FOLDER_NAME
    socials_dir = run_dir / SOCIALS_FOLDER_NAME
    shopify_uploads_dir.mkdir(parents=True, exist_ok=True)
    socials_dir.mkdir(parents=True, exist_ok=True)
    manifest = product_image_manifest or build_product_image_manifest(
        assets,
        product_slug=product_slug,
        sport_slug=sport_slug,
    )
    product_manifest_path = shopify_uploads_dir / PRODUCT_IMAGE_MANIFEST_FILENAME

    log_memory("Before export folder rebuild")
    # Product files are stable per slot. Rebuilding replaces only a slot's own
    # destination and leaves unrelated/supporting files in an existing folder
    # untouched.
    previous_images = []
    if product_manifest_path.is_file():
        try:
            previous_images = json.loads(
                product_manifest_path.read_text(encoding="utf-8")
            ).get("images") or []
        except (OSError, ValueError, TypeError, AttributeError):
            previous_images = []
    current_by_slot = {entry["slot_id"]: entry for entry in manifest}
    for previous in previous_images:
        current = current_by_slot.get(previous.get("slot_id")) or {}
        previous_name = str(previous.get("output_filename") or "")
        should_remove = previous_name and (
            not current.get("ready")
            or previous_name.casefold() != str(current.get("output_filename") or "").casefold()
        )
        if should_remove and Path(previous_name).name == previous_name:
            previous_path = shopify_uploads_dir / previous_name
            if previous_path.is_file():
                previous_path.unlink()

    for entry in manifest:
        source_path = _manifest_local_file(entry.get("local_path"))
        if not entry.get("ready") or not source_path:
            continue
        destination = shopify_uploads_dir / str(entry["output_filename"])
        if source_path.resolve() != destination.resolve():
            shutil.copy2(source_path, destination)

    # Social exports retain their established filenames and are likewise
    # idempotent: a retry replaces the matching file only.
    for asset in sorted(assets, key=lambda item: item.get("label", item.get("key", "")).lower()):
        if not asset.get("include_in_zip", True):
            continue
        jpg_path = asset.get("jpg_path")
        if should_export_asset_to_socials(asset) and jpg_path and Path(jpg_path).exists():
            shutil.copy2(jpg_path, socials_dir / Path(jpg_path).name)

    product_manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "readiness": product_image_readiness(manifest),
                "images": product_image_manifest_json(manifest),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    create_shopify_uploads_html(
        run_dir,
        shopify_uploads_dir,
        product_name,
        sport_category,
        manifest,
    )
    log_memory("After export folder rebuild")

    return {
        "shopify_uploads_dir": shopify_uploads_dir,
        "shopify_uploads_html_path": shopify_uploads_dir / "index.html",
        "socials_dir": socials_dir,
        "product_image_manifest": manifest,
        "product_image_readiness": product_image_readiness(manifest),
        "product_image_manifest_path": product_manifest_path,
    }


def save_review_and_assets(image, review_dir, webp_dir, jpg_dir, review_name, webp_name, jpg_name):
    review_path = review_dir / review_name
    webp_path = webp_dir / webp_name
    jpg_path = jpg_dir / jpg_name

    export_image = resize_for_export(image)
    try:
        export_image.save(review_path, format="PNG")

        export_image.save(
            webp_path,
            format="WEBP",
            quality=EXPORT_WEBP_QUALITY,
            method=EXPORT_WEBP_METHOD,
        )

        export_image.save(
            jpg_path,
            format="JPEG",
            quality=EXPORT_JPG_QUALITY,
            optimize=True,
        )
    finally:
        close_image(export_image)
        del export_image

    return review_path, webp_path, jpg_path


# -----------------------------------
# GENERATORS
# -----------------------------------

def generate_framed_product_image(
    template_path,
    artwork_path,
    box,
    review_dir,
    webp_dir,
    jpg_dir,
    review_name,
    webp_name,
    jpg_name,
):
    template = None
    artwork = None
    fitted_artwork = None

    try:
        template = load_artwork_image(template_path)
        artwork = load_artwork_image(artwork_path)

        x, y, w, h = box
        fitted_artwork = fit_artwork_to_box(artwork, w, h)
        template.paste(fitted_artwork, (x, y))

        return save_review_and_assets(
            template,
            review_dir,
            webp_dir,
            jpg_dir,
            review_name,
            webp_name,
            jpg_name,
        )
    finally:
        close_image(fitted_artwork)
        close_image(artwork)
        close_image(template)
        del fitted_artwork, artwork, template


def generate_unframed_product_image(
    template_path,
    artwork_path,
    art_box,
    review_dir,
    webp_dir,
    jpg_dir,
    review_name,
    webp_name,
    jpg_name,
):
    template = None
    artwork = None
    fitted_artwork = None

    try:
        template = load_artwork_image(template_path)
        artwork = load_artwork_image(artwork_path)

        x, y, w, h = art_box
        fitted_artwork = fit_artwork_to_box(artwork, w, h)
        template.paste(fitted_artwork, (x, y))

        return save_review_and_assets(
            template,
            review_dir,
            webp_dir,
            jpg_dir,
            review_name,
            webp_name,
            jpg_name,
        )
    finally:
        close_image(fitted_artwork)
        close_image(artwork)
        close_image(template)
        del fitted_artwork, artwork, template


def generate_size_guide(template_path, artwork_path, review_dir, webp_dir, jpg_dir, webp_name, jpg_name):
    template = None
    artwork = None

    try:
        template = load_artwork_image(template_path)
        artwork = load_artwork_image(artwork_path)

        for _, box in SIZE_GUIDE_BOXES.items():
            x, y, w, h = box
            fitted_artwork = fit_artwork_to_box(artwork, w, h)
            try:
                template.paste(fitted_artwork, (x, y))
            finally:
                close_image(fitted_artwork)
                del fitted_artwork

        return save_review_and_assets(
            template,
            review_dir,
            webp_dir,
            jpg_dir,
            "size-guide-output.png",
            webp_name,
            jpg_name,
        )
    finally:
        close_image(artwork)
        close_image(template)
        del artwork, template


def create_shopify_pack_zip(
    zip_dir,
    product_slug,
    shopify_uploads_dir,
    product_image_manifest=None,
):
    zip_path = zip_dir / f"{product_slug}-shopify-pack-webp.zip"

    ensure_memory_available("Before zip creation: Shopify pack")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        shopify_uploads_dir = Path(shopify_uploads_dir)
        if product_image_manifest is not None:
            upload_files = [
                shopify_uploads_dir / entry["output_filename"]
                for entry in sorted(product_image_manifest, key=lambda item: item["sort_position"])
                if entry.get("ready")
            ]
            upload_files.extend(
                path for path in (
                    shopify_uploads_dir / PRODUCT_IMAGE_MANIFEST_FILENAME,
                    shopify_uploads_dir / "index.html",
                )
                if path.is_file()
            )
        else:
            upload_files = sorted(shopify_uploads_dir.glob("*"))
        for upload_file in upload_files:
            if upload_file.is_file():
                zipf.write(upload_file, arcname=upload_file.name)

    ensure_memory_available("After zip creation: Shopify pack")

    return zip_path


def create_download_bundle_zip(
    zip_dir,
    product_slug,
    shopify_uploads_dir,
    jpg_dir,
    product_image_manifest=None,
):
    zip_path = zip_dir / f"{product_slug}-download-bundle.zip"

    ensure_memory_available("Before zip creation: Download bundle")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        if product_image_manifest is not None:
            upload_files = [
                Path(shopify_uploads_dir) / entry["output_filename"]
                for entry in sorted(product_image_manifest, key=lambda item: item["sort_position"])
                if entry.get("ready")
            ]
        else:
            upload_files = sorted(Path(shopify_uploads_dir).glob("*.webp"))
        for upload_file in upload_files:
            if upload_file.is_file():
                zipf.write(upload_file, arcname=f"{SHOPIFY_UPLOADS_FOLDER_NAME}/{upload_file.name}")

        for jpg_file in sorted(Path(jpg_dir).glob("*.jpg")):
            if jpg_file.is_file():
                zipf.write(jpg_file, arcname=f"jpg/{jpg_file.name}")

    ensure_memory_available("After zip creation: Download bundle")
    return zip_path


def create_social_media_pack_zip(zip_dir, product_slug, jpg_dir):
    zip_path = zip_dir / f"{product_slug}-social-media-pack-jpg.zip"

    ensure_memory_available("Before zip creation: Social media pack")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for jpg_file in sorted(jpg_dir.glob("*.jpg")):
            zipf.write(jpg_file, arcname=jpg_file.name)

    ensure_memory_available("After zip creation: Social media pack")
    return zip_path


def create_prompt_pack_zip(zip_dir, product_slug, prompt_dir):
    zip_path = zip_dir / f"{product_slug}-chatgpt-lifestyle-prompts.zip"

    ensure_memory_available("Before zip creation: Prompt pack")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for prompt_file in sorted(Path(prompt_dir).glob("*")):
            if prompt_file.is_file():
                zipf.write(prompt_file, arcname=prompt_file.name)

    ensure_memory_available("After zip creation: Prompt pack")
    return zip_path


def prompt_key_from_prompt_filename(prompt_filename):
    prompt_key = Path(prompt_filename).name
    if prompt_key.endswith("-prompt.txt"):
        prompt_key = prompt_key[: -len("-prompt.txt")]
    return prompt_key


def is_reels_prompt_filename(prompt_filename):
    return Path(prompt_filename).name in REELS_PROMPT_FILENAMES


PRODUCT_TITLE_PLACEHOLDER = "[PRODUCT TITLE]"
SPORT_PLACEHOLDER = "[SPORT]"
ARTWORK_REFERENCE_PLACEHOLDER = "[ARTWORK REFERENCE]"
LIFESTYLE_REFERENCE_PROMPT_TEXT = (
    "Upload the black framed WebP from this run into ChatGPT before using this prompt."
)
ROOM_STYLE_GUIDANCE_MARKER = "SPORTS CAVE ROOM STYLE GUIDANCE"
ROOM_STYLE_GUIDANCE_PROMPT_FILENAMES = set(PRODUCT_PAGE_PROMPT_FILENAMES)


def build_room_style_guidance(product_name, sport_category):
    product_value = str(product_name or "").strip() or PRODUCT_TITLE_PLACEHOLDER
    sport_value = str(sport_category or "").strip() or SPORT_PLACEHOLDER
    sport_text = (sport_family(sport_value) or sport_value).lower()
    product_text = product_value.lower()

    sport_profiles = [
        (
            ("motorsport", "formula", "f1", "racing", "race"),
            "sleek graphite, charcoal, black metal, controlled industrial refinement, warm timber restraint, and precise architectural lighting",
        ),
        (
            ("cricket",),
            "warm timber, textured plaster, earthy masculine tones, restrained heritage character, and calm study-or-lounge lighting",
        ),
        (
            ("afl", "australian rules"),
            "grounded contemporary Australian styling, natural timber, charcoal, muted neutrals, matte plaster, and relaxed premium warmth",
        ),
        (
            ("basketball", "nba"),
            "urban sophistication, deeper neutrals, clean contemporary forms, moody apartment lighting, and refined media-room materiality",
        ),
        (
            ("baseball",),
            "understated American lounge character, leather and timber influence, muted navy, charcoal, cream, and classic masculine balance",
        ),
        (
            ("soccer", "football"),
            "refined European-inspired modern styling, elegant darker neutrals, clean architectural lines, and quiet lounge sophistication",
        ),
        (
            ("golf",),
            "calm stone, oak, taupe, soft green undertones, restrained luxury, and a composed premium study or lounge mood",
        ),
        (
            ("tennis",),
            "lighter refined neutrals, elegant contemporary styling, soft natural light, subtle plaster texture, and understated luxury",
        ),
        (
            ("combat", "boxing", "ufc", "mma", "fight"),
            "darker minimal styling, strong architectural light, matte finishes, clean powerful lines, and no gym cliches",
        ),
        (
            ("nfl",),
            "substantial masculine lounge character, deeper neutrals, tailored leather or woven upholstery, timber weight, and controlled media-room lighting",
        ),
        (
            ("nrl", "rugby"),
            "grounded masculine Australian lounge styling, warm timber, charcoal, muted stone, durable premium textures, and relaxed architectural lighting",
        ),
        (
            ("hockey",),
            "cooler charcoal, slate, timber, black metal restraint, crisp architectural detail, and controlled cinematic lighting",
        ),
    ]

    sport_direction = (
        "a refined masculine palette, real architectural materials, premium wall texture, believable furniture tone, and lighting suited to the selected sport"
    )
    for keywords, direction in sport_profiles:
        if any(keyword in sport_text for keyword in keywords):
            sport_direction = direction
            break

    heritage_keywords = ("legend", "legacy", "classic", "heritage", "iconic", "greatest", "immortal", "champion")
    modern_keywords = ("bold", "intense", "modern", "dynasty", "rivalry", "statement", "attack", "unstoppable")
    nostalgic_keywords = ("remember", "farewell", "last dance", "history", "vintage", "throwback", "miracle")
    if any(keyword in product_text for keyword in heritage_keywords):
        product_direction = "Because the product title feels legendary or classic, lean slightly warmer, more timeless, and more established."
    elif any(keyword in product_text for keyword in modern_keywords):
        product_direction = "Because the product title feels bold or modern, lean slightly darker, cleaner, more architectural, and more controlled in the lighting."
    elif any(keyword in product_text for keyword in nostalgic_keywords):
        product_direction = "Because the product title feels nostalgic or history-driven, lean slightly warmer, more textured, and more emotionally lived-in."
    else:
        product_direction = "Let the product title subtly influence whether the room feels more timeless, modern, nostalgic, intense, calm, or iconic."

    return dedent(
        f"""
        {ROOM_STYLE_GUIDANCE_MARKER}:
        Place the artwork in a real premium lived-in interior suited to a discerning 30-50 year old {sport_value} fan and collector of "{product_value}".
        Use {sport_direction}.
        Create the sport-specific feeling through colour, materiality, mood, lighting, architecture, wall finish, and furniture tone rather than literal sports objects.
        {product_direction}
        Keep the room believable, masculine, clean, collector-worthy, subtly imperfect, and premium, with realistic room proportions, natural wall shadows, real material texture, and no fake showroom or generic AI-room appearance.
        Do not add sports balls, bats, helmets, jerseys, trophies, figurines, toy cars, novelty signs, fake memorabilia, team-coloured clutter, or obvious themed decorations.
        """
    ).strip()


def is_room_style_guidance_prompt(prompt_filename):
    return Path(prompt_filename).name in ROOM_STYLE_GUIDANCE_PROMPT_FILENAMES


def get_lifestyle_prompt_text(prompt_filename, default_text, *, local_only=False):
    prompt_filename = Path(prompt_filename).name
    prompt_id = f"lifestyle::{prompt_key_from_prompt_filename(prompt_filename)}"
    legacy_prompt_id = f"lifestyle::{prompt_filename}"
    prompt_loader = prompt_store.get_cached_prompt if local_only else prompt_store.get_prompt
    prompt_text = prompt_loader(prompt_id, "")
    if prompt_text.strip():
        return prompt_text
    return prompt_loader(legacy_prompt_id, default_text)


def get_prompt_group(prompt_filename):
    if is_product_page_prompt_filename(prompt_filename):
        return ASSET_CATEGORY_PRODUCT
    return ASSET_CATEGORY_SOCIAL


def get_asset_zip_group(asset):
    zip_group = str((asset or {}).get("zip_group") or "").strip()
    if zip_group:
        return ZIP_GROUP_ALIASES.get(zip_group, zip_group)

    prompt_filename = (asset or {}).get("prompt_filename")
    if prompt_filename:
        return get_prompt_group(prompt_filename)

    if (asset or {}).get("asset_group") == "lifestyle":
        return ASSET_CATEGORY_SOCIAL

    return ASSET_CATEGORY_CORE


def get_asset_zip_folder(file_path):
    file_path = Path(file_path)
    file_name = file_path.name

    for prompt_filename, variant_slug in LIFESTYLE_IMAGE_VARIANTS.items():
        if variant_slug in file_name:
            return "jpg"

    return "WEBP"


def build_lifestyle_prompt_items(
    product_name,
    sport_category,
    *,
    labels_by_filename=None,
    local_only=False,
    artwork_reference_available=True,
    product_metadata=None,
):
    labels_by_filename = labels_by_filename or {}
    prompt_items = []
    product_prompt_value = str(product_name or "").strip() or PRODUCT_TITLE_PLACEHOLDER
    sport_prompt_value = str(sport_category or "").strip() or SPORT_PLACEHOLDER
    reference_prompt_value = (
        LIFESTYLE_REFERENCE_PROMPT_TEXT
        if artwork_reference_available
        else ARTWORK_REFERENCE_PLACEHOLDER
    )
    room_style_guidance = build_room_style_guidance(product_prompt_value, sport_prompt_value)

    used_camera_angles = set()
    for filename, title, prompt_body in LIFESTYLE_PROMPT_SPECS:
        prompt_body = get_lifestyle_prompt_text(
            filename,
            prompt_body,
            local_only=local_only,
        )
        from mockup_product_prompts import build as build_product_scene
        prompt_body = build_product_scene(filename, prompt_body, avoid_angles=used_camera_angles)
        selected_angle = re.search(r'^Selected camera angle: (.+)$', prompt_body, flags=re.MULTILINE)
        if selected_angle:
            used_camera_angles.add(selected_angle.group(1))
        if (
            is_room_style_guidance_prompt(filename)
            and ROOM_STYLE_GUIDANCE_MARKER not in prompt_body
        ):
            prompt_body = f"{prompt_body}\n\n{room_style_guidance}"
        if is_reels_prompt_filename(filename):
            prompt_text = prompt_body.strip()
        else:
            prompt_text = dedent(
                f"""
                Product name: {product_prompt_value}
                Sport category: {sport_prompt_value}
                Reference image: {reference_prompt_value}

                {prompt_body}
                """
            ).strip()
        prompt_text = append_sports_cave_prompt_blocks(
            prompt_text,
            include_human=prompt_includes_human_scene(prompt_text),
            include_video=is_reels_prompt_filename(filename),
            physical_product=product_metadata,
        )
        prompt_items.append(
            {
                "key": prompt_key_from_prompt_filename(filename),
                "filename": filename,
                "label": labels_by_filename.get(filename, title),
                "prompt": prompt_text,
            }
        )

    return prompt_items


def generate_lifestyle_prompt_pack(
    product_name,
    sport_category,
    product_slug,
    run_dir,
    black_framed_webp_path,
    prompt_items=None,
):
    prompt_dir = run_dir / PROMPTS_FOLDER_NAME
    prompt_dir.mkdir(parents=True, exist_ok=True)

    reference_image_path = prompt_dir / LIFESTYLE_REFERENCE_FILE_NAME
    shutil.copy2(black_framed_webp_path, reference_image_path)

    prompt_paths = []
    final_prompt_items = (
        [dict(item) for item in prompt_items]
        if prompt_items is not None
        else build_lifestyle_prompt_items(product_name, sport_category)
    )

    for prompt_item in final_prompt_items:
        filename = Path(prompt_item["filename"]).name
        prompt_text = str(prompt_item["prompt"])
        prompt_path = prompt_dir / filename
        prompt_path.write_text(prompt_text + "\n", encoding="utf-8")
        prompt_paths.append(prompt_path)

    return prompt_dir, reference_image_path, prompt_paths, None


def unique_archive_name(archive_name, used_names, asset_key=""):
    archive_name = str(archive_name).replace("\\", "/")
    if archive_name not in used_names:
        used_names.add(archive_name)
        return archive_name

    archive_path = Path(archive_name)
    folder = archive_path.parent.as_posix()
    stem = archive_path.stem
    suffix = archive_path.suffix
    safe_key = slugify(asset_key or stem) or "asset"
    index = 2
    while True:
        candidate_name = f"{stem}-{safe_key}-{index}{suffix}"
        candidate = f"{folder}/{candidate_name}" if folder and folder != "." else candidate_name
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate
        index += 1


def normalize_zip_groups(zip_groups):
    if zip_groups is None:
        return None
    return {
        ZIP_GROUP_ALIASES.get(str(group).strip(), str(group).strip())
        for group in zip_groups
    }


def file_content_sha1(file_path):
    digest = hashlib.sha1()
    with Path(file_path).open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_asset_zip_manifest(assets, zip_groups=None, *, include_content_hash=True):
    selected_groups = normalize_zip_groups(zip_groups)
    used_names = set()
    entries = []

    for asset in sorted(
        assets or [],
        key=lambda item: (
            int(item.get("product_sort_position") or 10_000),
            item.get("label", item.get("key", "")).lower(),
        ),
    ):
        if not asset.get("include_in_zip", True):
            continue
        asset_group = get_asset_zip_group(asset)
        if selected_groups is not None and asset_group not in selected_groups:
            continue

        archive_paths = [("webp_path", "WEBP"), ("jpg_path", "jpg")]
        if asset_group == ASSET_CATEGORY_SOCIAL:
            archive_paths = [("jpg_path", "jpg")]

        for path_key, archive_folder in archive_paths:
            file_path = asset.get(path_key)
            if not file_path:
                continue
            file_path = Path(file_path)
            if not file_path.exists() or file_path.stat().st_size <= 0:
                continue
            archive_filename = file_path.name
            product_output_filename = str(asset.get("product_output_filename") or "")
            if product_output_filename:
                archive_filename = str(
                    Path(product_output_filename).with_suffix(file_path.suffix.casefold())
                )
            archive_name = unique_archive_name(
                f"{archive_folder}/{archive_filename}",
                used_names,
                asset.get("key"),
            )
            stat = file_path.stat()
            entries.append(
                {
                    "asset_key": asset.get("key"),
                    "asset_label": asset.get("label"),
                    "product_slot_id": asset.get("product_slot_id"),
                    "product_sort_position": asset.get("product_sort_position"),
                    "category": asset_group,
                    "path": file_path,
                    "filename": file_path.name,
                    "archive_name": archive_name,
                    "byte_length": stat.st_size,
                    "content_sha1": file_content_sha1(file_path) if include_content_hash else None,
                }
            )

    return entries


def create_complete_pack_zip(
    zip_dir,
    product_slug,
    webp_dir=None,
    jpg_dir=None,
    prompt_dir=None,
    assets=None,
    zip_groups=None,
    zip_filename=None,
):
    complete_zip_path = zip_dir / (zip_filename or f"{product_slug}-complete-package.zip")
    selected_groups = normalize_zip_groups(zip_groups)

    ensure_memory_available("Before zip creation: Complete pack")
    used_names = set()
    written_count = 0
    with zipfile.ZipFile(complete_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        if assets is not None:
            manifest_entries = build_asset_zip_manifest(
                assets,
                selected_groups,
                include_content_hash=False,
            )
            for entry in manifest_entries:
                zipf.write(entry["path"], arcname=entry["archive_name"])
                used_names.add(entry["archive_name"])
                written_count += 1
            logging.info(
                "MOCKUPS_ZIP wrote assets=%s groups=%s files=%s names=%s",
                len(assets or []),
                sorted(selected_groups) if selected_groups is not None else "all",
                written_count,
                [
                    {
                        "category": entry["category"],
                        "archive_name": entry["archive_name"],
                        "byte_length": entry["byte_length"],
                    }
                    for entry in manifest_entries
                ],
            )
        else:
            if webp_dir is not None:
                for webp_file in sorted(Path(webp_dir).glob("*.webp")):
                    zipf.write(webp_file, arcname=unique_archive_name(f"WEBP/{webp_file.name}", used_names))
                    written_count += 1

            if jpg_dir is not None:
                for jpg_file in sorted(Path(jpg_dir).glob("*.jpg")):
                    zipf.write(jpg_file, arcname=unique_archive_name(f"jpg/{jpg_file.name}", used_names))
                    written_count += 1

        if prompt_dir is not None:
            for prompt_file in sorted(Path(prompt_dir).glob("*")):
                if prompt_file.is_file():
                    zipf.write(
                        prompt_file,
                        arcname=unique_archive_name(f"{PROMPTS_FOLDER_NAME}/{prompt_file.name}", used_names),
                    )
                    written_count += 1

    if written_count != len(used_names):
        raise RuntimeError("ZIP validation failed: duplicate archive names were detected.")
    ensure_memory_available("After zip creation: Complete pack")
    return complete_zip_path


def save_lifestyle_mockup(run_dir, product_slug, sport_slug, prompt_filename, image_file):
    with _lifestyle_processing_lock:
        run_dir = Path(run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        try:
            with tempfile.TemporaryDirectory(dir=run_dir, prefix="lifestyle-stage-") as staging:
                staged = _save_lifestyle_mockup(staging, product_slug, sport_slug, prompt_filename, image_file)
                result, committed, backups = {}, [], {}
                try:
                    for key, value in staged.items():
                        if value is None:
                            result[key] = None
                            continue
                        value = Path(value)
                        target = run_dir / value.relative_to(staging)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if target.exists():
                            backup = Path(staging) / (key + ".backup")
                            shutil.copy2(target, backup)
                            backups[target] = backup
                        os.replace(value, target)
                        committed.append(target)
                        result[key] = target
                except Exception:
                    for target in reversed(committed):
                        if target in backups:
                            os.replace(backups[target], target)
                        else:
                            target.unlink(missing_ok=True)
                    raise
                return result
        except (MemoryError, MemoryLimitExceededError) as error:
            logging.exception("MOCKUPS_LIFESTYLE allocation/budget failure rss_mb=%s", get_memory_usage_mb())
            raise MemoryLimitExceededError(LIFESTYLE_UPLOAD_MEMORY_MESSAGE) from error
        finally:
            if hasattr(image_file, "seek"):
                image_file.seek(0)



def _save_lifestyle_mockup(run_dir, product_slug, sport_slug, prompt_filename, image_file):
    run_dir = Path(run_dir)
    webp_dir = run_dir / WEBP_CACHE_FOLDER_NAME
    jpg_dir = run_dir / JPG_CACHE_FOLDER_NAME
    preview_dir = run_dir / PREVIEW_FOLDER_NAME
    webp_dir.mkdir(parents=True, exist_ok=True)
    jpg_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    variant_slug = LIFESTYLE_IMAGE_VARIANTS[prompt_filename]
    should_save_webp = is_product_page_prompt_filename(prompt_filename)
    webp_output_path = webp_dir / f"{product_slug}-black-framed-{sport_slug}-{variant_slug}.webp"
    jpg_output_path = jpg_dir / f"{product_slug}-black-framed-{sport_slug}-{variant_slug}.jpg"
    preview_output_path = preview_dir / f"{product_slug}-black-framed-{sport_slug}-{variant_slug}-preview.webp"

    image_export = None
    working_image = None
    rgb_image = None
    try:
        with tempfile.TemporaryDirectory(prefix="sports-cave-lifestyle-") as temp_dir:
            temp_source_path = copy_uploaded_image_to_temp(image_file, temp_dir)

            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    # Conversion releases the decoded source early; Pillow 10.4's
                    # file-context __exit__ cannot close that source a second time.
                    with closing(Image.open(temp_source_path)) as source_image:
                        if source_image.format not in {"JPEG", "PNG", "WEBP"}:
                            raise ValueError(LIFESTYLE_UPLOAD_INVALID_MESSAGE)
                        logging.info("MOCKUPS_LIFESTYLE stage=decode dimensions=%sx%s mode=%s upload_bytes=%s",
                                     *source_image.size, source_image.mode, temp_source_path.stat().st_size)
                        validate_lifestyle_processing_memory(*source_image.size)
                        ImageOps.exif_transpose(source_image, in_place=True)
                        working_image = source_image
                        resize_lifestyle_source_if_needed(working_image)

                        if working_image.mode != "RGB":
                            rgb_image = working_image.convert("RGB")
                            close_image(working_image)
                            working_image = None
                        else:
                            rgb_image = working_image
                            working_image = None

                        export_edge = max(1, min(MAX_EXPORT_EDGE, rgb_image.width, rgb_image.height))
                        image_export = ImageOps.fit(
                            rgb_image,
                            (export_edge, export_edge),
                            method=Image.LANCZOS,
                        )
            finally:
                close_image(rgb_image)
                close_image(working_image)
                del rgb_image, working_image
    except ValueError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ValueError(IMAGE_DIMENSIONS_MESSAGE) from error
    except UnidentifiedImageError as error:
        raise RuntimeError(LIFESTYLE_UPLOAD_INVALID_MESSAGE) from error
    except (MemoryError, MemoryLimitExceededError) as error:
        # Process RSS / decoder allocation failures are not source-file sizes.
        close_image(image_export)
        raise MemoryLimitExceededError(LIFESTYLE_UPLOAD_MEMORY_MESSAGE) from error
    finally:
        if hasattr(image_file, "seek"):
            image_file.seek(0)

    try:
        if should_save_webp:
            image_export.save(
                webp_output_path,
                format="WEBP",
                quality=EXPORT_WEBP_QUALITY,
                method=EXPORT_WEBP_METHOD,
            )
        else:
            with suppress(FileNotFoundError, PermissionError):
                webp_output_path.unlink()

        image_export.save(
            jpg_output_path,
            format="JPEG",
            quality=EXPORT_JPG_QUALITY,
            optimize=True,
        )

        preview_image = image_export.copy()
        try:
            preview_image.thumbnail((MAX_PREVIEW_EDGE, MAX_PREVIEW_EDGE), Image.LANCZOS)
            preview_image.save(
                preview_output_path,
                format="WEBP",
                quality=PREVIEW_WEBP_QUALITY,
                method=PREVIEW_WEBP_METHOD,
            )
        finally:
            close_image(preview_image)
            del preview_image
    finally:
        close_image(image_export)
        del image_export

    return {
        "webp_path": webp_output_path if should_save_webp else None,
        "jpg_path": jpg_output_path,
        "preview_path": preview_output_path,
    }


# -----------------------------------
# MAIN BACKEND FUNCTION
# -----------------------------------

def generate_product_images(
    product_name,
    sport_category,
    artwork_file_path,
    base_dir=None,
    status_callback=None,
    final_prompt_items=None,
    output_root=None,
    asset_completed_callback=None,
):
    def report(message, progress=None):
        if callable(status_callback):
            try:
                status_callback(message, progress)
            except Exception:
                pass

        if message:
            print(f"[image_factory] {message}")
    if base_dir is None:
        base_dir = Path(__file__).resolve().parent
    else:
        base_dir = Path(base_dir)

    templates_dir = base_dir / "templates"
    output_dir = Path(output_root) if output_root is not None else base_dir / "output"

    product_slug = slugify(product_name) or "sports-cave-product"
    sport_slug = slugify(sport_category) or "sports"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    run_prefix = "mockup-run-" if output_root is not None else ""
    run_dir = output_dir / f"{run_prefix}{product_slug}-{timestamp}"
    if output_root is None:
        run_dir = output_dir / "runs" / f"{product_slug}-{timestamp}"

    review_dir = run_dir / "review"
    preview_dir = run_dir / PREVIEW_FOLDER_NAME
    webp_dir = run_dir / WEBP_CACHE_FOLDER_NAME
    jpg_dir = run_dir / JPG_CACHE_FOLDER_NAME
    zip_dir = run_dir / "zip"
    upload_dir = run_dir / "uploaded"

    review_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)
    webp_dir.mkdir(parents=True, exist_ok=True)
    jpg_dir.mkdir(parents=True, exist_ok=True)
    zip_dir.mkdir(parents=True, exist_ok=True)
    upload_dir.mkdir(parents=True, exist_ok=True)

    black_template = find_file(
        "black-frame-template.jpg",
        ["black-framed*.jpg", "*black*.jpg"],
        templates_dir
    )

    oak_template = find_file(
        "oak-frame-template.jpg",
        ["oak-framed*.jpg", "*oak*.jpg"],
        templates_dir
    )

    white_template = find_file(
        "white-frame-template.jpg",
        ["white-framed*.jpg", "*white*.jpg"],
        templates_dir
    )

    unframed_template = find_file(
        "unframed-template.jpg",
        ["unframed*.jpg", "*unframed*.jpg"],
        templates_dir
    )

    size_guide_template = find_file(
        "size-guide-template.jpg",
        ["*sizing-guide*.jpg", "*size-guide*.jpg"],
        templates_dir
    )

    artwork_file_path = Path(artwork_file_path)
    saved_artwork_path = upload_dir / "artwork-original"
    saved_artwork_path = saved_artwork_path.with_suffix(artwork_file_path.suffix)

    shutil.copy2(artwork_file_path, saved_artwork_path)
    report("Preparing lightweight working image...", 15)
    working_artwork_path = prepare_working_artwork(saved_artwork_path, upload_dir)

    review_paths = []
    webp_paths = []
    jpg_paths = []
    generated_assets = {}
    assets = []

    jobs = [
        {
            "key": "black",
            "label": "Black Framed",
            "status": "Generating black frame...",
            "progress": 30,
            "type": "framed",
            "template": black_template,
            "review_name": "black-framed-output.png",
            "webp_name": f"{product_slug}-black-framed-{sport_slug}-wall-art.webp",
            "jpg_name": f"{product_slug}-black-framed-{sport_slug}-wall-art.jpg",
        },
        {
            "key": "oak",
            "label": "Oak Framed",
            "status": "Generating oak frame...",
            "progress": 42,
            "type": "framed",
            "template": oak_template,
            "review_name": "oak-framed-output.png",
            "webp_name": f"{product_slug}-oak-framed-{sport_slug}-wall-art.webp",
            "jpg_name": f"{product_slug}-oak-framed-{sport_slug}-wall-art.jpg",
        },
        {
            "key": "white",
            "label": "White Framed",
            "status": "Generating white frame...",
            "progress": 54,
            "type": "framed",
            "template": white_template,
            "review_name": "white-framed-output.png",
            "webp_name": f"{product_slug}-white-framed-{sport_slug}-wall-art.webp",
            "jpg_name": f"{product_slug}-white-framed-{sport_slug}-wall-art.jpg",
        },
        {
            "key": "unframed",
            "label": "Unframed",
            "status": "Generating unframed...",
            "progress": 66,
            "type": "unframed",
            "template": unframed_template,
            "review_name": "unframed-output.png",
            "webp_name": f"{product_slug}-unframed-{sport_slug}-wall-art.webp",
            "jpg_name": f"{product_slug}-unframed-{sport_slug}-wall-art.jpg",
        },
        {
            "key": "size-guide",
            "label": "Size Guide",
            "status": "Generating size guide...",
            "progress": 78,
            "type": "size_guide",
            "template": size_guide_template,
            "review_name": "size-guide-output.png",
            "webp_name": f"{product_slug}-framed-{sport_slug}-wall-art-sizing-guide.webp",
            "jpg_name": f"{product_slug}-framed-{sport_slug}-wall-art-sizing-guide.jpg",
        },
    ]

    for job in jobs:
        report(job["status"], job["progress"])
        ensure_memory_available(f"Before mockup generation: {job['label']}")

        if job["type"] == "framed":
            review_path, webp_path, jpg_path = generate_framed_product_image(
                job["template"],
                working_artwork_path,
                MASTER_FRAMED_BOX,
                review_dir,
                webp_dir,
                jpg_dir,
                job["review_name"],
                job["webp_name"],
                job["jpg_name"],
            )

        elif job["type"] == "size_guide":
            review_path, webp_path, jpg_path = generate_size_guide(
                job["template"],
                working_artwork_path,
                review_dir,
                webp_dir,
                jpg_dir,
                job["webp_name"],
                job["jpg_name"],
            )

        elif job["type"] == "unframed":
            review_path, webp_path, jpg_path = generate_unframed_product_image(
                job["template"],
                working_artwork_path,
                UNFRAMED_ART_BOX,
                review_dir,
                webp_dir,
                jpg_dir,
                job["review_name"],
                job["webp_name"],
                job["jpg_name"],
            )

        asset_record = build_asset_record(
            key=job["key"],
            label=job["label"],
            review_path=review_path,
            preview_path=None,
            webp_path=webp_path,
            jpg_path=jpg_path,
        )
        preview_path = create_preview_file(
            review_path,
            preview_dir,
            f"{Path(review_path).stem}-preview.webp",
        )
        asset_record["preview_path"] = preview_path

        if callable(asset_completed_callback):
            callback_updates = asset_completed_callback(
                dict(asset_record),
                dict(job),
                run_dir=run_dir,
            )
            if callback_updates:
                asset_record.update(callback_updates)

        review_paths.append(asset_record.get("review_path"))
        webp_paths.append(asset_record.get("webp_path"))
        jpg_paths.append(asset_record.get("jpg_path"))
        generated_assets[job["key"]] = {
            "review_path": asset_record.get("review_path"),
            "preview_path": asset_record.get("preview_path"),
            "webp_path": asset_record.get("webp_path"),
            "jpg_path": asset_record.get("jpg_path"),
            "asset_record": asset_record,
        }
        assets.append(asset_record)

        collect_garbage(f"After mockup generation: {job['label']}")

    black_framed_webp_path = generated_assets["black"]["webp_path"]
    black_framed_jpg_path = generated_assets["black"]["jpg_path"]
    prompt_dir = None
    prompt_paths = []
    prompt_zip_path = None
    lifestyle_pack_error = None

    ensure_memory_available("Completion")

    return {
        "product_name": product_name,
        "sport_category": sport_category,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "product_slug": product_slug,
        "sport_slug": sport_slug,
        "run_dir": run_dir,
        "review_dir": review_dir,
        "preview_dir": preview_dir,
        "webp_dir": webp_dir,
        "jpg_dir": jpg_dir,
        "zip_dir": zip_dir,
        "zip_path": None,
        "social_zip_path": None,
        "complete_zip_path": None,
        "shopify_uploads_dir": None,
        "shopify_uploads_html_path": None,
        "socials_dir": None,
        "review_paths": review_paths,
        "webp_paths": webp_paths,
        "jpg_paths": jpg_paths,
        "black_framed_webp_path": black_framed_webp_path,
        "black_framed_jpg_path": black_framed_jpg_path,
        "prompt_dir": prompt_dir,
        "prompt_paths": prompt_paths,
        "prompt_zip_path": prompt_zip_path,
        "final_prompt_items": [dict(item) for item in (final_prompt_items or [])],
        "assets": assets,
        "lifestyle_mockup_paths": {},
        "lifestyle_pack_error": lifestyle_pack_error,
    }
