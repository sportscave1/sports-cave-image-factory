from pathlib import Path
from PIL import Image
import zipfile
import re

# -----------------------------------
# PATHS
# -----------------------------------

BASE_DIR = Path(__file__).resolve().parent

TEMPLATES_DIR = BASE_DIR / "templates"
INPUT_DIR = BASE_DIR / "input"

OUTPUT_DIR = BASE_DIR / "output"
REVIEW_DIR = OUTPUT_DIR / "review"
WEBP_DIR = OUTPUT_DIR / "webp"
ZIP_DIR = OUTPUT_DIR / "zip"

REVIEW_DIR.mkdir(parents=True, exist_ok=True)
WEBP_DIR.mkdir(parents=True, exist_ok=True)
ZIP_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------------
# CLEAN OLD OUTPUTS
# -----------------------------------

def clean_folder(folder, patterns):
    for pattern in patterns:
        for file in folder.glob(pattern):
            try:
                file.unlink()
            except PermissionError:
                print(f"Could not delete {file}. Close it if it is open and run again.")


clean_folder(REVIEW_DIR, ["*.png", "*.jpg", "*.jpeg", "*.webp"])
clean_folder(WEBP_DIR, ["*.webp"])
clean_folder(ZIP_DIR, ["*.zip"])

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


BLACK_TEMPLATE = find_file(
    "black-frame-template.jpg",
    ["black-framed*.jpg", "*black*.jpg"],
    TEMPLATES_DIR
)

OAK_TEMPLATE = find_file(
    "oak-frame-template.jpg",
    ["oak-framed*.jpg", "*oak*.jpg"],
    TEMPLATES_DIR
)

WHITE_TEMPLATE = find_file(
    "white-frame-template.jpg",
    ["white-framed*.jpg", "*white*.jpg"],
    TEMPLATES_DIR
)

UNFRAMED_TEMPLATE = find_file(
    "unframed-template.jpg",
    ["unframed*.jpg", "*unframed*.jpg"],
    TEMPLATES_DIR
)

SIZE_GUIDE_TEMPLATE = find_file(
    "size-guide-template.jpg",
    ["*sizing-guide*.jpg", "*size-guide*.jpg"],
    TEMPLATES_DIR
)

ARTWORK_FILE = find_file(
    "artwork.jpg",
    ["*.jpg", "*.jpeg", "*.png"],
    INPUT_DIR
)

# -----------------------------------
# PLACEMENT RULES
# -----------------------------------

# FRAMED PRODUCT MOCKUPS
# Current shared framed box for black / oak / white.
# If you later measure black frame exactly, we can swap this out.
MASTER_FRAMED_BOX = (84, 204, 824, 583)

FRAMED_BOXES = {
    "black": {
        "template": BLACK_TEMPLATE,
        "box": MASTER_FRAMED_BOX,
        "review_name": "black-framed-output.png",
    },
    "oak": {
        "template": OAK_TEMPLATE,
        "box": MASTER_FRAMED_BOX,
        "review_name": "oak-framed-output.png",
    },
    "white": {
        "template": WHITE_TEMPLATE,
        "box": MASTER_FRAMED_BOX,
        "review_name": "white-framed-output.png",
    },
}

# UNFRAMED
# Leave unchanged — user approved this.
UNFRAMED_ART_BOX = (84, 210, 824, 580)

# SIZE GUIDE
# Exact measured values supplied from Photoshop:
# XL = first 2 screenshots
# L  = next 2 screenshots
# M  = next 2 screenshots
# S  = last 2 screenshots

SIZE_GUIDE_BOXES = {
    "x_large": (633, 147, 655, 462),
    "large":   (101, 248, 426, 300),
    "medium":  (115, 812, 289, 204),
    "small":   (567, 863, 179, 126),
}

# -----------------------------------
# HELPERS
# -----------------------------------

def slugify(text):
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def fit_artwork_to_box(artwork, box_width, box_height):
    """
    Resize artwork to fully cover the target box while preserving aspect ratio.
    If needed, crop evenly from the centre so no blank edges appear.
    """
    artwork = artwork.convert("RGB")

    art_ratio = artwork.width / artwork.height
    box_ratio = box_width / box_height

    if art_ratio > box_ratio:
        new_height = box_height
        new_width = int(new_height * art_ratio)
    else:
        new_width = box_width
        new_height = int(new_width / art_ratio)

    resized = artwork.resize((new_width, new_height), Image.LANCZOS)

    left = (new_width - box_width) // 2
    top = (new_height - box_height) // 2
    right = left + box_width
    bottom = top + box_height

    return resized.crop((left, top, right, bottom))


def resize_to_1024(image):
    return image.resize((1024, 1024), Image.LANCZOS)


def save_review_and_webp(image, review_name, webp_name):
    review_path = REVIEW_DIR / review_name
    webp_path = WEBP_DIR / webp_name

    image_1024 = resize_to_1024(image)

    image_1024.save(review_path, format="PNG")

    image_1024.save(
        webp_path,
        format="WEBP",
        quality=82,
        method=6
    )

    print(f"Saved review: {review_path}")
    print(f"Saved WebP:   {webp_path}")

    return webp_path


# -----------------------------------
# GENERATORS
# -----------------------------------

def generate_framed_product_image(template_path, artwork, box, review_name, webp_name):
    """
    For black / oak / white framed mockups.
    """
    template = Image.open(template_path).convert("RGB")

    x, y, w, h = box
    fitted_artwork = fit_artwork_to_box(artwork, w, h)

    template.paste(fitted_artwork, (x, y))

    return save_review_and_webp(template, review_name, webp_name)


def generate_unframed_product_image(template_path, artwork, art_box, review_name, webp_name):
    """
    For unframed:
    Do not add white.
    The template already has the poster paper.
    """
    template = Image.open(template_path).convert("RGB")

    x, y, w, h = art_box
    fitted_artwork = fit_artwork_to_box(artwork, w, h)

    template.paste(fitted_artwork, (x, y))

    return save_review_and_webp(template, review_name, webp_name)


def generate_size_guide(artwork, webp_name):
    """
    Size guide uses its own exact measured coordinates.
    """
    template = Image.open(SIZE_GUIDE_TEMPLATE).convert("RGB")

    for _, box in SIZE_GUIDE_BOXES.items():
        x, y, w, h = box
        fitted_artwork = fit_artwork_to_box(artwork, w, h)
        template.paste(fitted_artwork, (x, y))

    return save_review_and_webp(
        template,
        "size-guide-output.png",
        webp_name
    )


def create_zip(product_slug):
    zip_path = ZIP_DIR / f"{product_slug}-shopify-images.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for webp_file in sorted(WEBP_DIR.glob("*.webp")):
            zipf.write(webp_file, arcname=webp_file.name)

    print(f"\nZIP created: {zip_path}")
    return zip_path


# -----------------------------------
# MAIN
# -----------------------------------

def main():
    print("\nSports Cave Image Factory — Size Guide Measured Revision")
    print("--------------------------------------------------------\n")

    product_name = input("Product name, example greg-murphy-lap-of-the-gods: ").strip()
    sport_category = input("Sport category, example motorsport, soccer, basketball: ").strip()

    if not product_name:
        product_name = "sports-cave-product"

    if not sport_category:
        sport_category = "sports"

    product_slug = slugify(product_name)
    sport_slug = slugify(sport_category)

    artwork = Image.open(ARTWORK_FILE).convert("RGB")

    generate_framed_product_image(
        FRAMED_BOXES["black"]["template"],
        artwork,
        FRAMED_BOXES["black"]["box"],
        FRAMED_BOXES["black"]["review_name"],
        f"{product_slug}-black-framed-{sport_slug}-wall-art.webp"
    )

    generate_size_guide(
        artwork,
        f"{product_slug}-framed-{sport_slug}-wall-art-sizing-guide.webp"
    )

    generate_framed_product_image(
        FRAMED_BOXES["oak"]["template"],
        artwork,
        FRAMED_BOXES["oak"]["box"],
        FRAMED_BOXES["oak"]["review_name"],
        f"{product_slug}-oak-framed-{sport_slug}-wall-art.webp"
    )

    generate_framed_product_image(
        FRAMED_BOXES["white"]["template"],
        artwork,
        FRAMED_BOXES["white"]["box"],
        FRAMED_BOXES["white"]["review_name"],
        f"{product_slug}-white-framed-{sport_slug}-wall-art.webp"
    )

    generate_unframed_product_image(
        UNFRAMED_TEMPLATE,
        artwork,
        UNFRAMED_ART_BOX,
        "unframed-output.png",
        f"{product_slug}-unframed-{sport_slug}-wall-art.webp"
    )

    create_zip(product_slug)

    print("\nDone.")
    print("Check these folders:")
    print(f"Review PNGs: {REVIEW_DIR}")
    print(f"WebP files:  {WEBP_DIR}")
    print(f"ZIP folder:  {ZIP_DIR}")


if __name__ == "__main__":
    main()