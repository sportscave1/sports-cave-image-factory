from pathlib import Path
from PIL import Image, ImageOps, ImageFile, UnidentifiedImageError
import gc
import os
import zipfile
import re
import shutil
import tempfile
import warnings
from datetime import datetime
from textwrap import dedent

import prompt_store

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
MEMORY_LIMIT_MB = 430
MEMORY_LIMIT_MESSAGE = (
    "Memory limit reached before completion. Try a smaller uploaded image or upgrade the Render instance."
)
PREPARE_ARTWORK_MEMORY_LIMIT_MESSAGE = (
    "Memory limit reached while preparing the uploaded artwork. "
    "Try exporting the artwork as JPG/WebP under 20MB, or upgrade Render to a higher-memory instance."
)
LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE = (
    "This uploaded image is too large. Please upload a JPG, PNG or WebP under 15 MB."
)
LIFESTYLE_UPLOAD_INVALID_MESSAGE = (
    "Cannot read the uploaded lifestyle image. Please upload a valid JPG, PNG, or WEBP file."
)


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
    memory_usage = log_memory(stage)
    if memory_usage is not None and memory_usage >= MEMORY_LIMIT_MB:
        raise MemoryLimitExceededError(error_message)

    return memory_usage


def close_image(image):
    if image is None:
        return

    try:
        image.close()
    except Exception:
        pass


def collect_garbage(stage, error_message=MEMORY_LIMIT_MESSAGE):
    gc.collect()
    ensure_memory_available(stage, error_message=error_message)


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

    with temp_path.open("wb") as destination:
        shutil.copyfileobj(image_file, destination, length=1024 * 1024)

    if temp_path.stat().st_size > MAX_LIFESTYLE_UPLOAD_SIZE_BYTES:
        raise ValueError(LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE)

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
            image.load()
            return ImageOps.exif_transpose(image).convert("RGB")
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
    "10-premium-unboxing-prompt.txt": "premium-unboxing-lifestyle",
    "11-wall-upgrade-moment-prompt.txt": "wall-upgrade-moment-lifestyle",
    "12-fireplace-feature-wall-prompt.txt": "fireplace-feature-wall-lifestyle",
    "13-premium-bedroom-prompt.txt": "premium-bedroom-lifestyle",
    "14-home-gym-prompt.txt": "home-gym-lifestyle",
    "15-premium-gift-reveal-prompt.txt": "premium-gift-reveal-lifestyle",
    "16-man-cave-reel-prompt.txt": "16-man-cave-reel",
    "17-living-room-reel-prompt.txt": "17-living-room-reel",
    "18-office-reel-prompt.txt": "18-office-reel",
    "19-home-sports-bar-reel-prompt.txt": "19-home-sports-bar-reel",
    "20-collector-display-room-reel-prompt.txt": "20-collector-display-room-reel",
}

PRODUCT_PAGE_PROMPT_FILENAMES = {
    "01-man-cave-prompt.txt",
    "02-office-prompt.txt",
    "03-living-room-prompt.txt",
}
REELS_PROMPT_FILENAMES = {
    "16-man-cave-reel-prompt.txt",
    "17-living-room-reel-prompt.txt",
    "18-office-reel-prompt.txt",
    "19-home-sports-bar-reel-prompt.txt",
    "20-collector-display-room-reel-prompt.txt",
}

LIFESTYLE_PROMPT_SPECS = [
    (
        "01-man-cave-prompt.txt",
        "Man Cave",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic lifestyle mockup using the uploaded image as the exact reference for the framed artwork.
            The artwork and frame must remain exactly the same as the uploaded image.
            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.

            Place the exact uploaded Sports Cave landscape frame realistically inside a premium man cave interior.

            The space must feel masculine, minimal, premium, and collector-driven.
            Use a clean man cave setting with subtle realism only.
            Keep the background restrained and believable.

            Use a neutral premium palette:
            black, charcoal, warm timber, off-white, soft beige, concrete, plaster, or matte painted walls.

            The frame must look physically real:
            premium black timber frame, realistic depth, sharp corners, subtle texture, and believable wall shadows.

            Add realistic glass over the frame.
            The glass should have soft natural reflections and subtle premium glare from the room lighting.
            The glare must feel believable and must not cover or ruin the artwork.

            Use premium cinematic lighting:
            soft natural light, controlled highlights, and realistic shadow falloff behind and below the frame.

            The frame should feel mounted on a real wall, not pasted on.

            Composition:
            square 1024 x 1024 canvas.
            The framed artwork is the hero.
            Place it at realistic eye-level height.
            Show believable scale.
            A slight natural viewing angle is allowed, but the frame and artwork must keep correct landscape proportions and must not look perspective-distorted.

            Background styling:
            minimal premium man cave only.
            You may include subtle realistic decor such as a blurred leather chair, a simple shelf, or a soft foreground object, but keep it minimal.
            Do not add clutter.
            Do not add neon signs.
            Do not add random sports logos.
            Do not add extra wall art.
            Do not add people.
            Do not add text overlays.
            Do not add watermarks.

            Final result:
            photorealistic premium man cave mockup with the exact uploaded design and frame, realistic glass, premium shadows, and believable lighting.
            """
        ).strip(),
    ),
    (
        "02-office-prompt.txt",
        "Office",
        dedent(
            """
            Using the design and frame from the last image created, create another 1024 x 1024 ultra-realistic lifestyle mockup.

            Keep the exact same artwork and the exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, crop, or composition inside the frame.
            Do not blur, stretch, warp, or distort the artwork or frame.

            This version must place the framed artwork in a premium office setting.

            The office should feel like a different house or location from the previous image.
            Use a different wall colour from the last image so it feels like a new environment.
            Also use a different viewing angle so it feels like a fresh perspective.

            The frame must remain physically realistic:
            premium black timber frame, real depth, sharp corners, subtle texture, and realistic wall mounting.

            Add realistic glass over the artwork with soft premium reflections and subtle glare.
            The glare should feel natural and believable, without blocking the artwork too much.

            Use premium cinematic lighting with realistic highlights and shadows.
            The lighting and shadows should feel different from the previous image while still looking premium and natural.

            Room style:
            minimal premium office.
            Clean, refined, masculine, and realistic.
            Use a neutral palette with a different wall tone than the last scene.
            You may use off-white, warm grey, beige, matte olive-grey, charcoal, concrete, or soft plaster tones.

            Keep the background minimal and realistic.
            You may include subtle office details only if they help realism, such as a desk edge, chair, bookshelf, or side table.
            Do not clutter the space.
            Do not add random sports logos.
            Do not add extra artwork.
            Do not add text overlays.
            Do not add watermarks.

            Composition:
            square 1024 x 1024 canvas.
            The framed artwork is the hero.
            Show believable scale and realistic eye-level placement.
            Use a different angle from the previous image, but preserve the correct landscape proportions of the frame and artwork.

            Final result:
            photorealistic premium office mockup using the same exact design and frame as the previous image, with a different wall colour, different angle, and different premium lighting so it feels like a different house and a different view.
            """
        ).strip(),
    ),
    (
        "03-living-room-prompt.txt",
        "Living Room",
        dedent(
            """
            Using the design and frame from the last image created, create another 1024 x 1024 ultra-realistic lifestyle mockup. Use a different angle and different wall colour so it looks like a different house and camera angle to the previous generation.
            Keep the exact same artwork and the exact same black landscape frame.
            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, crop, or composition inside the frame.
            Do not blur, stretch, warp, or distort the artwork or frame.

            This version must place the framed artwork in a premium living room setting.

            The living room should feel like a different house or location from the previous images.
            Use a different wall colour again so it feels like a fresh new space.
            Also use a different angle so this mockup feels like a new premium view.

            The frame must look physically real:
            premium black timber frame, realistic depth, sharp corners, subtle texture, and believable mounting on the wall.

            Add realistic glass over the artwork.
            The glass should have soft natural reflections and subtle premium glare from the room lighting.
            The glare must feel realistic and controlled without hiding the artwork.

            Use premium cinematic lighting:
            soft natural light, controlled highlights, and realistic shadows behind and below the frame.
            The scene should feel bright enough to look premium, but still warm and realistic.

            Room style:
            minimal premium living room.
            Clean, restrained, masculine, collector-driven, and believable.
            Use a refined neutral palette with a different wall colour from the office and man cave versions.
            You may use warm beige, light greige, soft concrete, off-white, muted taupe, or matte painted plaster walls.

            Keep the background minimal.
            You may include subtle realistic decor such as part of a sofa, side table, floor lamp, or soft foreground object, but keep everything understated.
            Do not add clutter.
            Do not add neon signs.
            Do not add random sports logos.
            Do not add extra wall art.
            Do not add people.
            Do not add text overlays.
            Do not add watermarks.

            Composition:
            square 1024 x 1024 canvas.
            The framed artwork is the hero.
            Show believable scale.
            Place it at realistic eye-level height.
            Use a different angle from the previous versions, while preserving the correct landscape proportions of the frame and artwork.

            Final result:
            photorealistic premium living room mockup using the same exact design and frame as the previous image, with real glass, premium shadows, different wall colour, and a fresh angle so it feels like a different house and a different premium scene.
            """
        ).strip(),
    ),
    (
        "04-close-up-wall-prompt.txt",
        "Close-Up Premium Wall Shot",
        dedent(
            """
            Using the uploaded artwork and frame as the exact reference, create a 1024 x 1024 ultra-realistic close-up lifestyle mockup. Use a different angle and different wall colour so it looks like a different house and camera angle to the previous generation.
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
            Glass realism:
            add realistic glass over the artwork.
            The glass should show soft natural reflections and subtle premium glare.
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
            photorealistic close-up wall mockup of the exact supplied Sports Cave artwork and black frame, with real glass glare, premium shadows, realistic wall texture, and no distractions.
            """
        ).strip(),
    ),
    (
        "05-limited-edition-detail-prompt.txt",
        "Limited Edition Magnifying Glass Detail Shot",
        dedent(
            """
            Using the uploaded artwork and frame as the exact reference, create a 1024 x 1024 ultra-realistic limited edition detail mockup.
            The artwork and frame must remain exactly the same as the uploaded image.
            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.
            This image must highlight the limited edition detail on the uploaded Sports Cave design.
            Use a realistic magnifying glass placed over or near the limited edition badge, edition plate, edition number, collector badge, certificate-style detail, or numbered edition area visible in the uploaded artwork.
            The magnifying glass must feel physically real:
            clear glass lens, premium metal rim, realistic handle, natural reflections, soft shadows, and believable distortion only inside the lens.
            The magnified area should clearly show the limited edition text, edition number, numbered plate, or collector detail.
            The magnification must look realistic and premium.
            Do not make the magnified area cartoonish.
            Do not over-enlarge the text.
            Do not distort the artwork outside the magnifying glass.
            Do not create fake text.
            Do not change the edition number.
            Do not add new badges.
            Do not add new logos.
            Do not add extra text overlays.
            Do not add watermarks.
            If the uploaded artwork has the limited edition detail near the bottom centre, place the magnifying glass naturally over that area.
            If the uploaded artwork has the limited edition detail in another location, place the magnifying glass over the correct visible limited edition detail.
            If the uploaded artwork includes both a collector badge and a numbered edition plate, prioritise the numbered edition plate.
            The frame must remain physically realistic:
            premium black timber frame, real depth, sharp corners, subtle timber texture, and believable wall mounting.
            Add realistic glass over the frame.
            The artwork glass and magnifying glass should both have believable reflections, but the reflections must not hide the limited edition detail.
            Use premium cinematic lighting:
            soft natural light from one side, controlled highlights, realistic shadows, and subtle premium glare.
            The scene must feel like a professional product detail photo for a premium collector release.
            Composition:
            square 1024 x 1024 canvas.
            The framed artwork should still be clearly visible, but the limited edition detail must become the hero.
            The magnifying glass should sit naturally in the foreground, angled slightly, with realistic depth and shadow.
            Keep the frame and artwork proportions correct.
            Use a clean premium wall background:
            matte plaster, warm beige, soft concrete, charcoal, muted taupe, off-white, or gallery-style painted wall.
            No room decor.
            No furniture.
            No people.
            No random props except the magnifying glass.
            No clutter.
            No neon signs.
            No extra wall art.
            No random sports logos.
            No added text.
            Final result:
            photorealistic premium close-up mockup of the exact uploaded Sports Cave framed artwork, with a realistic magnifying glass highlighting the limited edition detail, real glass reflections, premium shadows, and a collector-driven product photography feel.
            """
        ).strip(),
    ),
    (
        "06-instant-experience-cover-prompt.txt",
        "Instant Experience Cover Banner",
        dedent(
            """
            Using the uploaded Sports Cave product image as the exact reference, create a 1024 x 1024 ultra-realistic Instant Experience cover image for a Meta ad.
            This image will be used as the top cover of an Instant Experience ad, with the product catalogue automatically appearing underneath, so the image must instantly create desire, scarcity and premium collector value.
            The uploaded framed artwork must remain exactly the same.
            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text inside the artwork.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.
            Do not create fake signatures, fake logos, fake edition numbers, or fake artwork details.
            Do not change the frame colour unless the uploaded reference already shows that frame colour.
            Create a premium square advertising cover that combines:
            A realistic lifestyle-style framed artwork hero shot at the top.
            A luxury black and gold scarcity CTA panel at the bottom.
            The framed artwork should take up the top 60-68% of the canvas.
            Place the exact uploaded Sports Cave framed artwork on a premium wall, as if it is hanging in a real home, office, man cave, collector room, or gallery-style space.
            The room should feel:
            premium, masculine, minimal, cinematic, collector-driven, realistic and high-end.
            Use a refined neutral background:
            warm beige, soft concrete, charcoal, off-white, muted taupe, plaster wall, gallery wall, or warm grey.
            The frame must look physically real:
            premium black timber frame, realistic depth, sharp corners, subtle timber texture, clean edges, correct landscape proportions, and believable wall mounting.
            Add realistic glass over the framed artwork.
            The glass must show:
            soft natural reflections, subtle premium glare, realistic highlight streaks, and believable room reflections.
            The glare must feel expensive and real, but it must not cover or ruin the artwork.
            Use premium cinematic lighting:
            soft natural light from one side, controlled warm highlights, realistic shadows behind and below the frame, and subtle shadow falloff on the wall.
            The artwork must look mounted on the wall, not pasted on.
            Use a slight natural viewing angle if needed, but do not over-angle the frame.
            The frame and artwork must keep correct proportions and must not look warped or distorted.
            Bottom CTA panel:
            Add a premium black textured banner panel across the bottom 32-40% of the image.
            The panel should feel luxury and collector-grade:
            deep black, subtle dark texture, soft gold highlights, faint vignette, refined metallic glow, and clean spacing.
            Add a subtle gold light flare or glow line between the framed artwork section and the CTA panel, similar to a premium collector campaign.
            Text overlay on the bottom panel must be clean, centred, readable on mobile, and limited to three lines only.
            Use this exact text:
            LIMITED TO 100 WORLDWIDE
            Once it sells out, it's gone.
            Claim Your Edition
            Text styling:
            The first line should be large, premium, uppercase, serif-style, white or soft metallic gold.
            The second line should be smaller, clean, white or warm ivory.
            The third line should feel like a premium CTA, gold, slightly smaller than the main headline, and highly readable.
            Do not add too much text.
            Do not add paragraphs.
            Do not add extra product information.
            Do not add prices.
            Do not add discount messaging.
            Do not add "shop now" buttons.
            Do not add fake UI elements.
            Do not add random logos.
            Do not add people.
            Do not add clutter.
            Do not add extra wall art.
            Do not add social media icons.
            Do not add watermarks.
            Composition:
            square 1024 x 1024 canvas.
            The framed artwork is the hero.
            The bottom scarcity message must feel like part of a premium ad campaign, not a cheap banner.
            Leave enough breathing room so the text is readable on mobile.
            The final image should look like a luxury limited-edition collector release, designed to make fans tap into the Instant Experience catalogue below.
            Final result:
            a photorealistic premium Sports Cave Instant Experience cover image featuring the exact uploaded framed artwork, realistic wall mounting, real glass reflections, premium glare, believable shadows, luxury black and gold bottom CTA panel, and strong limited-edition scarcity messaging.
            """
        ).strip(),
    ),
    (
        "07-home-sports-bar-prompt.txt",
        "Premium Home Sports Bar",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad carousel mockup using the uploaded image as the exact reference for the framed artwork.
            This image is for a paid Meta ad carousel, not a standard product page image. It must instantly create desire, ownership, and premium collector value.
            The artwork and frame must remain exactly the same as the uploaded image.
            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text inside the artwork.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.
            Place the exact uploaded Sports Cave landscape frame realistically inside a premium home sports bar setting.
            The room must feel like the kind of place a serious fan would watch finals, rivalries, title fights, race days, or derby nights.
            The space should feel premium, masculine, cinematic, and collector-driven - not cheap, cluttered, or gimmicky.
            Use a refined home bar environment:
            dark stone benchtop, matte black cabinetry, warm timber shelving, subtle glassware, soft bar lighting, premium stools, and a faint out-of-focus TV glow in the background.
            Do not use neon signs.
            Do not use random sports logos.
            Do not use beer branding.
            Do not use team branding.
            Do not add extra wall art.
            Do not add people.
            Do not add text overlays.
            Do not add watermarks.
            The framed artwork must be the hero of the image.
            It should be mounted behind or near the bar as the main statement piece.
            Show believable scale, as if the customer can imagine it in their own home bar or fan space.
            The frame must look physically real:
            premium black timber frame, realistic depth, sharp corners, subtle texture, and believable wall mounting.
            Add realistic glass over the frame.
            The glass must show soft premium reflections and subtle natural glare from the bar lighting.
            The glare must feel believable and must not hide or ruin the artwork.
            Lighting:
            cinematic evening lighting.
            Warm practical lights.
            Controlled highlights.
            Soft shadows behind and below the frame.
            Subtle reflections on the glass.
            Premium contrast without making the artwork too dark.
            Composition:
            square 1024 x 1024 canvas.
            The framed artwork should take up strong visual space, roughly 45-60% of the image.
            Use a slight natural angle to make the scene feel real, but preserve the correct landscape proportions.
            The image must stop the scroll and make the viewer think: "That belongs in my space."
            Final result:
            a photorealistic premium home sports bar ad mockup with the exact uploaded Sports Cave framed artwork, realistic glass, premium shadows, cinematic lighting, and strong collector appeal.
            """
        ).strip(),
    ),
    (
        "08-collector-display-room-prompt.txt",
        "Collector Display Room",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad carousel mockup using the uploaded image as the exact reference for the framed artwork.
            This image is for a high-converting Meta ad carousel. It must feel like a premium collector piece being displayed in a serious fan's private collection.
            The artwork and frame must remain exactly the same as the uploaded image.
            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text inside the artwork.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.
            Place the exact uploaded Sports Cave landscape frame inside a premium collector display room.
            The space should feel like a private sports collector's room, not a messy bedroom or generic man cave.
            Use a refined display environment:
            dark matte walls, warm timber or black shelving, a glass display cabinet, subtle memorabilia silhouettes, premium lighting strips, and carefully placed collector items.
            The collector items must stay subtle and out of focus.
            They should add atmosphere without competing with the framed artwork.
            Do not add recognisable team logos.
            Do not add random athlete photos.
            Do not add extra wall art.
            Do not add people.
            Do not add text overlays.
            Do not add watermarks.
            Do not make the room cluttered.
            Do not make it look like a retail shop.
            The framed artwork must be the clear hero.
            It should feel like the prized piece in the collection.
            Position it above or beside the display cabinet, with enough breathing room around it to feel premium.
            The frame must look physically real:
            premium black timber frame, realistic depth, sharp corners, subtle texture, and believable wall shadows.
            Add realistic glass over the artwork.
            The glass should show soft reflections from the display lighting.
            The glare should feel premium, subtle, and natural.
            Do not let reflections obscure the artwork.
            Lighting:
            collector-room lighting.
            Controlled spotlight effect on the framed artwork.
            Soft warm highlights.
            Deep but clean shadows.
            A cinematic black, gold, charcoal, and warm timber palette.
            Composition:
            square 1024 x 1024 canvas.
            The framed artwork must dominate the visual hierarchy.
            Use a slightly angled camera perspective from one side, like a premium interior photography shot.
            Keep the frame proportions accurate and undistorted.
            The image should communicate:
            limited edition,
            collector value,
            ownership,
            scarcity,
            and pride.
            Final result:
            a photorealistic premium collector display room ad mockup with the exact uploaded Sports Cave framed artwork, realistic glass, controlled cinematic lighting, subtle memorabilia atmosphere, and strong limited-edition collector energy.
            """
        ).strip(),
    ),
    (
        "09-luxury-entry-wall-prompt.txt",
        "Luxury Entry Statement Wall",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad carousel mockup using the uploaded image as the exact reference for the framed artwork.
            This image is for a paid Meta ad carousel. It must show the artwork as a premium statement piece inside a stylish home, designed to make viewers imagine owning it immediately.
            The artwork and frame must remain exactly the same as the uploaded image.
            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text inside the artwork.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.
            Place the exact uploaded Sports Cave landscape frame on a premium luxury entryway or hallway statement wall.
            This must feel different from a living room, office, man cave, or close-up wall shot.
            The space should feel refined, clean, architectural, and expensive.
            Use a luxury hallway or entry space with:
            matte plaster wall,
            stone or timber floor,
            soft wall lighting,
            a slim console table,
            subtle sculptural decor,
            and controlled negative space.
            The artwork should feel like the first thing someone sees when they walk into the home.
            Do not add clutter.
            Do not add people.
            Do not add random sports logos.
            Do not add extra wall art.
            Do not add text overlays.
            Do not add watermarks.
            Do not make the space look like a hotel lobby.
            Do not make the room too bright or sterile.
            The frame must look physically real:
            premium black timber frame, realistic depth, sharp corners, subtle texture, and believable wall mounting.
            Add realistic glass over the artwork.
            The glass should show soft architectural reflections and controlled premium glare.
            The glare must feel realistic and must not hide the artwork.
            Lighting:
            premium architectural lighting.
            Soft warm wall lights or ceiling spotlights.
            Natural shadow falloff behind and below the frame.
            Subtle highlights on the glass and frame edges.
            The scene should feel cinematic, minimal, and collector-driven.
            Composition:
            square 1024 x 1024 canvas.
            The framed artwork should be the hero.
            Show enough of the hallway or entryway to make the viewer feel the scale and premium placement.
            Use a clean editorial camera angle, slightly off-centre, with strong depth and realism.
            Preserve the correct landscape proportions of the artwork and frame.
            The image should communicate:
            this is not just decoration,
            this is a statement piece,
            this belongs in a home owned by a real fan.
            Final result:
            a photorealistic premium luxury entry statement wall ad mockup with the exact uploaded Sports Cave framed artwork, realistic glass, premium shadows, architectural lighting, and strong scroll-stopping collector appeal.
            """
        ).strip(),
    ),
]

LIFESTYLE_PROMPT_SPECS.extend([
    (
        "10-premium-unboxing-prompt.txt",
        "Premium Unboxing / Collector Arrival",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad mockup using the uploaded Sports Cave image as the exact reference for the framed artwork.

            This image is for a paid Meta ad and must feel like the customer has just received a premium collector piece.

            The artwork and frame must remain exactly the same as the uploaded image.

            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop the artwork.
            Do not blur the artwork.
            Do not stretch, warp, bend, squash, or distort the frame or artwork.

            Place the exact framed artwork in a premium unboxing scene.

            The frame should be resting carefully on a luxury timber, stone, or matte black surface, partly lifted from premium protective packaging.

            Use tasteful packaging details:

            black shipping box or kraft protective box
            soft tissue paper
            subtle black/gold wrapping detail
            clean protective corners
            a blank premium thank-you card with no readable text

            The scene should feel expensive, real, and gift-worthy.

            Do not add fake logos.
            Do not add fake edition numbers.
            Do not add fake certificates.
            Do not add extra readable text.
            Do not add people or faces.
            Do not make it look cheap or messy.

            The frame must look physically real with depth, sharp corners, timber texture, realistic glass reflections, and believable shadows.

            Lighting should feel like premium product photography: soft natural light, gentle highlights on the glass, realistic shadow falloff, and clean contrast.

            Final result:
            A premium collector unboxing ad image that makes the product feel valuable, gift-worthy, and exciting to receive.
            """
        ).strip(),
    ),
    (
        "11-wall-upgrade-moment-prompt.txt",
        "The Wall Upgrade Moment",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad mockup using the uploaded Sports Cave image as the exact reference for the framed artwork.

            This image should capture the moment the customer has just upgraded their wall with the artwork.

            The artwork and frame must remain exactly the same as the uploaded image.

            Do not redesign the artwork.
            Do not change the colours, layout, text, badge, crop, or internal composition.
            Do not blur, stretch, warp, bend, squash, or distort the frame or artwork.

            Place the exact framed artwork mounted on a clean premium wall, with subtle styling that suggests it has just been installed.

            Include tasteful installation details only:

            a small spirit level on a nearby console or floor
            soft packaging material below
            a clean wall hook or hanging guide nearby
            subtle shadow from the frame
            no mess, no clutter

            The image should feel like:
            "This is the moment the room changed."

            The setting should be minimal, modern, and premium. Use matte plaster, warm grey, beige, soft concrete, charcoal, or off-white walls.

            The framed artwork must be the hero and should feel freshly installed, perfectly level, and premium.

            Do not add people.
            Do not add hands.
            Do not add text overlays.
            Do not add extra wall art.
            Do not add random sports logos.
            Do not add watermarks.

            Add realistic glass reflections, premium glare, frame depth, and natural shadows.

            Final result:
            A high-converting "room upgrade" ad creative that makes the viewer imagine putting the piece on their own wall today.
            """
        ).strip(),
    ),
    (
        "12-fireplace-feature-wall-prompt.txt",
        "Luxury Fireplace Feature Wall",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad mockup using the uploaded image as the exact reference for the framed Sports Cave artwork.

            This image is for a premium Meta ad and must make the artwork feel like the hero piece of an expensive feature wall.

            The artwork and frame must remain exactly the same as the uploaded image.

            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop, blur, stretch, warp, bend, squash, or distort the frame or artwork.

            Place the exact framed artwork above or beside a premium modern fireplace feature wall.

            The space should feel architectural, warm, masculine, and expensive.

            Use details like:

            stone fireplace surround
            matte plaster wall
            warm ambient lighting
            low modern furniture edge
            subtle timber or concrete textures
            clean negative space

            The fireplace should support the product, not overpower it. The artwork must remain the main focal point.

            Do not add people.
            Do not add extra wall art.
            Do not add random sports logos.
            Do not add text overlays.
            Do not add watermarks.
            Do not make it look like a hotel lobby.

            The frame must look physically mounted, with real depth, natural wall shadows, premium glass reflections, and subtle glare.

            Lighting should feel cinematic and warm, like an expensive evening interior shoot.

            Final result:
            A premium fireplace feature-wall ad image that makes the artwork feel like a serious statement piece for a high-end home.
            """
        ).strip(),
    ),
    (
        "13-premium-bedroom-prompt.txt",
        "Premium Bedroom / Private Retreat",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad mockup using the uploaded image as the exact reference for the framed artwork.

            This image is for a paid Meta ad and should show the artwork in a more personal, emotional setting - a private room where the customer sees it every day.

            The artwork and frame must remain exactly the same as the uploaded image.

            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop, blur, stretch, warp, bend, squash, or distort the frame or artwork.

            Place the exact framed Sports Cave artwork inside a premium bedroom or private retreat.

            The room should feel refined, masculine, calm, and expensive - not messy, childish, or overly decorated.

            Use:

            premium bed linen
            soft wall lighting
            matte plaster or warm neutral wall
            timber bedside table
            subtle luxury decor
            controlled negative space

            The artwork should feel like a personal reminder of greatness, memory, identity, or obsession.

            Do not add people.
            Do not add extra wall art.
            Do not add random sports logos.
            Do not add text overlays.
            Do not add watermarks.
            Do not make it look like a hotel room catalogue image.

            The frame must look physically real with premium black timber depth, sharp corners, realistic wall shadows, and natural glass glare.

            Final result:
            A premium bedroom lifestyle ad that makes the artwork feel personal, emotional, and worth owning.
            """
        ).strip(),
    ),
    (
        "14-home-gym-prompt.txt",
        "Home Gym / Motivation Wall",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad mockup using the uploaded image as the exact reference for the framed Sports Cave artwork.

            This image is for a high-attention Meta ad. It should connect the artwork with motivation, discipline, greatness, and daily identity.

            The artwork and frame must remain exactly the same as the uploaded image.

            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop, blur, stretch, warp, bend, squash, or distort the frame or artwork.

            Place the exact framed artwork on the wall of a premium private home gym or training space.

            The room should feel high-end, clean, masculine, and aspirational.

            Use subtle gym details only:

            matte black dumbbells
            clean rubber flooring
            timber or concrete wall texture
            soft mirror reflection
            premium bench or training equipment edge
            controlled lighting

            The gym should not look commercial, cheap, sweaty, or cluttered. It should feel like a private luxury training room.

            Do not add people.
            Do not add brand logos.
            Do not add motivational text overlays.
            Do not add extra posters.
            Do not add watermarks.

            The framed artwork must be the hero. It should feel like the piece that sets the tone for the room.

            Add realistic glass reflections, premium glare, frame depth, and believable wall shadows.

            Final result:
            A scroll-stopping home gym ad creative that links the artwork with motivation, winning, discipline, and greatness.
            """
        ).strip(),
    ),
    (
        "15-premium-gift-reveal-prompt.txt",
        "Premium Gift Reveal Scene",
        dedent(
            """
            Create a 1024 x 1024 ultra-realistic Meta ad mockup using the uploaded Sports Cave image as the exact reference for the framed artwork.

            This image is for a paid Meta ad and must position the product as the perfect premium gift for a serious fan.

            The artwork and frame must remain exactly the same as the uploaded image.

            Do not redesign the artwork.
            Do not change the colours.
            Do not change the layout.
            Do not change the text.
            Do not change the badge.
            Do not crop, blur, stretch, warp, bend, squash, or distort the frame or artwork.

            Create a premium gift reveal scene.

            The framed artwork should be leaning safely against a luxury wall or resting on a premium surface, surrounded by tasteful gift details.

            Use:

            black or gold wrapping paper
            premium ribbon
            clean gift box
            blank gift card with no readable text
            soft warm lighting
            luxury home setting

            The mood should feel emotional, premium, and personal - like someone has just received a meaningful collector piece.

            Do not add people.
            Do not add fake text.
            Do not add fake logos.
            Do not add fake edition certificates.
            Do not add random sports branding.
            Do not add watermarks.
            Do not make it look like Christmas unless specifically requested.

            The artwork must stay sharp, readable, and unchanged. The frame must show real depth, premium glass reflections, subtle glare, and believable shadows.

            Final result:
            A premium gift-focused Meta ad image that makes the product feel meaningful, valuable, and easy to buy for someone who loves the sport.
            """
        ).strip(),
    ),
])

LIFESTYLE_PROMPT_SPECS.extend([
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
])


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
    upload_dir = Path(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    image_path = Path(image_path)
    working_path = upload_dir / "working-artwork.webp"

    ensure_memory_available(
        "Before source image open",
        error_message=PREPARE_ARTWORK_MEMORY_LIMIT_MESSAGE,
    )

    source_image = None
    working_image = None

    try:
        source_image = Image.open(image_path)
        source_format = (source_image.format or image_path.suffix.lstrip(".") or "unknown").upper()
        source_width, source_height = source_image.size
        file_size_bytes = image_path.stat().st_size if image_path.exists() else 0

        log_image_details(
            "Source upload metadata",
            source_format,
            source_width,
            source_height,
            file_size_bytes,
        )
        log_memory("After reading source metadata")

        if source_format in {"JPEG", "JPG"}:
            source_image.draft("RGB", (MAX_WORKING_EDGE, MAX_WORKING_EDGE))

        if max(source_image.size) > MAX_WORKING_EDGE or (source_image.width * source_image.height) > MAX_SOURCE_PIXELS:
            source_image.thumbnail(
                (MAX_WORKING_EDGE, MAX_WORKING_EDGE),
                Image.LANCZOS,
                reducing_gap=3.0,
            )
            log_memory("After source downscale before transpose")

        working_image = ImageOps.exif_transpose(source_image)

        if max(working_image.size) > MAX_WORKING_EDGE or (working_image.width * working_image.height) > MAX_SOURCE_PIXELS:
            working_image.thumbnail(
                (MAX_WORKING_EDGE, MAX_WORKING_EDGE),
                Image.LANCZOS,
                reducing_gap=3.0,
            )

        if working_image.mode != "RGB":
            rgb_image = working_image.convert("RGB")
            close_image(working_image)
            working_image = rgb_image

        working_image.save(
            working_path,
            format="WEBP",
            quality=EXPORT_WEBP_QUALITY,
            method=EXPORT_WEBP_METHOD,
        )
        log_memory("After downscaled working image saved")
    except UnidentifiedImageError as error:
        raise RuntimeError(
            f"Cannot open artwork file {image_path}. Please upload a valid JPG, PNG, or WEBP image."
        ) from error
    finally:
        close_image(working_image)
        close_image(source_image)
        del working_image, source_image
        gc.collect()
        log_memory("After closing source image")

    collect_garbage(
        "After preparing lightweight working image",
        error_message=PREPARE_ARTWORK_MEMORY_LIMIT_MESSAGE,
    )

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
    zip_group="core",
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


def is_product_page_prompt_filename(prompt_filename):
    return prompt_filename in PRODUCT_PAGE_PROMPT_FILENAMES


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


def create_shopify_uploads_html(run_dir, shopify_uploads_dir, product_name, sport_category):
    shopify_uploads_dir = Path(shopify_uploads_dir)
    image_files = sorted(shopify_uploads_dir.glob("*.webp"))
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

    if image_files:
        for image_file in image_files:
            html_lines.extend([
                "    <div class=\"image-card\">",
                f"      <img src=\"{image_file.name}\" alt=\"{image_file.name}\">",
                f"      <p>{image_file.name}</p>",
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


def rebuild_export_folders(run_dir, assets, product_name="", sport_category=""):
    run_dir = Path(run_dir)
    shopify_uploads_dir = run_dir / SHOPIFY_UPLOADS_FOLDER_NAME
    socials_dir = run_dir / SOCIALS_FOLDER_NAME

    log_memory("Before export folder rebuild")
    reset_directory_contents(shopify_uploads_dir)
    reset_directory_contents(socials_dir)

    for asset in sorted(assets, key=lambda item: item.get("label", item.get("key", "")).lower()):
        if not asset.get("include_in_zip", True):
            continue

        webp_path = asset.get("webp_path")
        jpg_path = asset.get("jpg_path")

        if should_export_asset_to_shopify(asset) and webp_path and Path(webp_path).exists():
            shutil.copy2(webp_path, shopify_uploads_dir / Path(webp_path).name)

        if should_export_asset_to_socials(asset) and jpg_path and Path(jpg_path).exists():
            shutil.copy2(jpg_path, socials_dir / Path(jpg_path).name)

    create_shopify_uploads_html(run_dir, shopify_uploads_dir, product_name, sport_category)
    log_memory("After export folder rebuild")

    return {
        "shopify_uploads_dir": shopify_uploads_dir,
        "shopify_uploads_html_path": shopify_uploads_dir / "index.html",
        "socials_dir": socials_dir,
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
        gc.collect()

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
        gc.collect()


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
        gc.collect()


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
        gc.collect()


def create_shopify_pack_zip(zip_dir, product_slug, shopify_uploads_dir):
    zip_path = zip_dir / f"{product_slug}-shopify-pack-webp.zip"

    ensure_memory_available("Before zip creation: Shopify pack")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for upload_file in sorted(Path(shopify_uploads_dir).glob("*")):
            if upload_file.is_file():
                zipf.write(upload_file, arcname=upload_file.name)

    ensure_memory_available("After zip creation: Shopify pack")

    return zip_path


def create_download_bundle_zip(zip_dir, product_slug, shopify_uploads_dir, jpg_dir):
    zip_path = zip_dir / f"{product_slug}-download-bundle.zip"

    ensure_memory_available("Before zip creation: Download bundle")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for upload_file in sorted(Path(shopify_uploads_dir).glob("*.webp")):
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


def get_lifestyle_prompt_text(prompt_filename, default_text):
    prompt_filename = Path(prompt_filename).name
    prompt_id = f"lifestyle::{prompt_key_from_prompt_filename(prompt_filename)}"
    legacy_prompt_id = f"lifestyle::{prompt_filename}"
    prompt_text = prompt_store.get_prompt(prompt_id, "")
    if prompt_text.strip():
        return prompt_text
    return prompt_store.get_prompt(legacy_prompt_id, default_text)


def get_prompt_group(prompt_filename):
    prompt_filename = Path(prompt_filename).name
    if prompt_filename in PRODUCT_PAGE_PROMPT_FILENAMES:
        return "product_page"
    if prompt_filename in REELS_PROMPT_FILENAMES:
        return "reels"

    return "social"


def get_asset_zip_group(asset):
    zip_group = str((asset or {}).get("zip_group") or "").strip()
    if zip_group:
        return zip_group

    prompt_filename = (asset or {}).get("prompt_filename")
    if prompt_filename:
        return get_prompt_group(prompt_filename)

    if (asset or {}).get("asset_group") == "lifestyle":
        return "social"

    return "core"


def get_asset_zip_folder(file_path):
    file_path = Path(file_path)
    file_name = file_path.name

    for prompt_filename, variant_slug in LIFESTYLE_IMAGE_VARIANTS.items():
        if variant_slug in file_name:
            if get_prompt_group(prompt_filename) == "product_page":
                return "WEBP"

            return "jpg"

    return "WEBP"


def generate_lifestyle_prompt_pack(product_name, sport_category, product_slug, run_dir, black_framed_webp_path):
    prompt_dir = run_dir / PROMPTS_FOLDER_NAME
    prompt_dir.mkdir(parents=True, exist_ok=True)

    reference_image_path = prompt_dir / LIFESTYLE_REFERENCE_FILE_NAME
    shutil.copy2(black_framed_webp_path, reference_image_path)

    prompt_paths = []

    for filename, _, prompt_body in LIFESTYLE_PROMPT_SPECS:
        prompt_path = prompt_dir / filename
        prompt_body = get_lifestyle_prompt_text(filename, prompt_body)
        if is_reels_prompt_filename(filename):
            prompt_text = prompt_body.strip()
        else:
            prompt_text = dedent(
                f"""
                Product name: {product_name}
                Sport category: {sport_category}
                Reference image: Upload the black framed WebP from this run into ChatGPT before using this prompt.

                {prompt_body}
                """
            ).strip()
        prompt_path.write_text(prompt_text + "\n", encoding="utf-8")
        prompt_paths.append(prompt_path)

    return prompt_dir, reference_image_path, prompt_paths, None


def create_complete_pack_zip(zip_dir, product_slug, webp_dir=None, jpg_dir=None, prompt_dir=None, assets=None, zip_groups=None):
    complete_zip_path = zip_dir / f"{product_slug}-complete-package.zip"
    selected_groups = set(zip_groups or []) if zip_groups is not None else None

    ensure_memory_available("Before zip creation: Complete pack")
    with zipfile.ZipFile(complete_zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        if assets is not None:
            for asset in sorted(assets, key=lambda item: item.get("label", item.get("key", "")).lower()):
                if not asset.get("include_in_zip", True):
                    continue
                if selected_groups is not None and get_asset_zip_group(asset) not in selected_groups:
                    continue

                webp_path = asset.get("webp_path")
                jpg_path = asset.get("jpg_path")

                if webp_path and Path(webp_path).exists():
                    webp_path = Path(webp_path)
                    zipf.write(webp_path, arcname=f"WEBP/{webp_path.name}")

                if jpg_path and Path(jpg_path).exists():
                    jpg_path = Path(jpg_path)
                    zipf.write(jpg_path, arcname=f"jpg/{jpg_path.name}")
        else:
            if webp_dir is not None:
                for webp_file in sorted(Path(webp_dir).glob("*.webp")):
                    zipf.write(webp_file, arcname=f"WEBP/{webp_file.name}")

            if jpg_dir is not None:
                for jpg_file in sorted(Path(jpg_dir).glob("*.jpg")):
                    zipf.write(jpg_file, arcname=f"jpg/{jpg_file.name}")

        if prompt_dir is not None:
            for prompt_file in sorted(Path(prompt_dir).glob("*")):
                if prompt_file.is_file():
                    zipf.write(prompt_file, arcname=f"{PROMPTS_FOLDER_NAME}/{prompt_file.name}")

    ensure_memory_available("After zip creation: Complete pack")
    return complete_zip_path


def save_lifestyle_mockup(run_dir, product_slug, sport_slug, prompt_filename, image_file):
    run_dir = Path(run_dir)
    webp_dir = run_dir / WEBP_CACHE_FOLDER_NAME
    jpg_dir = run_dir / JPG_CACHE_FOLDER_NAME
    preview_dir = run_dir / PREVIEW_FOLDER_NAME
    webp_dir.mkdir(parents=True, exist_ok=True)
    jpg_dir.mkdir(parents=True, exist_ok=True)
    preview_dir.mkdir(parents=True, exist_ok=True)

    variant_slug = LIFESTYLE_IMAGE_VARIANTS[prompt_filename]
    webp_output_path = webp_dir / f"{product_slug}-black-framed-{sport_slug}-{variant_slug}.webp"
    jpg_output_path = jpg_dir / f"{product_slug}-black-framed-{sport_slug}-{variant_slug}.jpg"
    preview_output_path = preview_dir / f"{product_slug}-black-framed-{sport_slug}-{variant_slug}-preview.webp"

    image_export = None
    working_image = None
    rgb_image = None
    try:
        with tempfile.TemporaryDirectory(prefix="sports-cave-lifestyle-") as temp_dir:
            temp_source_path = copy_uploaded_image_to_temp(image_file, temp_dir)

            ensure_memory_available(f"Before source image open: {prompt_filename}")
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("error", Image.DecompressionBombWarning)
                    with Image.open(temp_source_path) as source_image:
                        working_image = ImageOps.exif_transpose(source_image)
                        if resize_lifestyle_source_if_needed(working_image):
                            collect_garbage(f"After lifestyle source resize: {prompt_filename}")

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
                collect_garbage(f"After source image open: {prompt_filename}")
    except ValueError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as error:
        raise RuntimeError(LIFESTYLE_UPLOAD_INVALID_MESSAGE) from error
    except (MemoryError, MemoryLimitExceededError) as error:
        raise RuntimeError(LIFESTYLE_UPLOAD_TOO_LARGE_MESSAGE) from error
    finally:
        if hasattr(image_file, "seek"):
            image_file.seek(0)

    try:
        image_export.save(
            webp_output_path,
            format="WEBP",
            quality=EXPORT_WEBP_QUALITY,
            method=EXPORT_WEBP_METHOD,
        )
        collect_garbage(f"After lifestyle WEBP save: {prompt_filename}")

        image_export.save(
            jpg_output_path,
            format="JPEG",
            quality=EXPORT_JPG_QUALITY,
            optimize=True,
        )
        collect_garbage(f"After lifestyle JPG save: {prompt_filename}")

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
        collect_garbage(f"After saving lifestyle mockup: {prompt_filename}")

    return {
        "webp_path": webp_output_path,
        "jpg_path": jpg_output_path,
        "preview_path": preview_output_path,
    }


# -----------------------------------
# MAIN BACKEND FUNCTION
# -----------------------------------

def generate_product_images(product_name, sport_category, artwork_file_path, base_dir=None, status_callback=None):
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
    output_dir = base_dir / "output"

    product_slug = slugify(product_name) or "sports-cave-product"
    sport_slug = slugify(sport_category) or "sports"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
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

        review_paths.append(review_path)
        webp_paths.append(webp_path)
        jpg_paths.append(jpg_path)
        asset_record = build_asset_record(
            key=job["key"],
            label=job["label"],
            review_path=review_path,
            preview_path=None,
            webp_path=webp_path,
            jpg_path=jpg_path,
        )
        generated_assets[job["key"]] = {
            "review_path": review_path,
            "preview_path": None,
            "webp_path": webp_path,
            "jpg_path": jpg_path,
            "asset_record": asset_record,
        }
        assets.append(asset_record)

        collect_garbage(f"After mockup generation: {job['label']}")

    report("Creating lightweight previews...", 88)
    for job in jobs:
        review_path = generated_assets[job["key"]]["review_path"]
        preview_path = create_preview_file(
            review_path,
            preview_dir,
            f"{Path(review_path).stem}-preview.webp",
        )
        generated_assets[job["key"]]["preview_path"] = preview_path
        generated_assets[job["key"]]["asset_record"]["preview_path"] = preview_path

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
        "assets": assets,
        "lifestyle_mockup_paths": {},
        "lifestyle_pack_error": lifestyle_pack_error,
    }
