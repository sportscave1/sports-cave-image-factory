from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import re
import warnings
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError


META_IMAGE_EDGE = 1080
INSTANT_EXPERIENCE_IMAGE_EDGE = 1024
META_IMAGE_QUALITY = 91
META_IMAGE_MAX_UPLOAD_BYTES = 20 * 1024 * 1024
META_IMAGE_MAX_SOURCE_PIXELS = 25_000_000
META_IMAGE_ACCEPTED_FORMATS = {"JPEG", "PNG", "WEBP"}
DEFAULT_ACCOUNT_TIMEZONE = "Australia/Sydney"
MAX_FILENAME_LENGTH = 220


class AdsImageValidationError(ValueError):
    pass


def campaign_image_slots(campaign_type):
    if campaign_type == "Carousel":
        return tuple(
            {
                "id": f"carousel-{index:02d}",
                "label": f"Carousel {index}",
                "position": index,
            }
            for index in range(1, 6)
        )
    if campaign_type == "Instant Experience":
        return (
            {
                "id": "instant-experience-01",
                "label": "Nostalgia / Moment Cover",
                "position": 1,
                "required": True,
            },
            {
                "id": "instant-experience-02",
                "label": "Identity / Ownership Cover",
                "position": 2,
                "required": True,
            },
            {
                "id": "instant-experience-03",
                "label": "Collector / Scarcity Cover",
                "position": 3,
                "required": True,
            },
        )
    return ()


def source_image_signature(data):
    return hashlib.sha256(bytes(data or b"")).hexdigest()


def _flatten_transparency(image):
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        background.alpha_composite(rgba)
        return background.convert("RGB")
    return image


def _convert_to_srgb(image):
    source_profile_bytes = image.info.get("icc_profile")
    srgb_profile = ImageCms.createProfile("sRGB")
    if source_profile_bytes:
        try:
            source_profile = ImageCms.ImageCmsProfile(io.BytesIO(source_profile_bytes))
            converted = ImageCms.profileToProfile(
                image,
                source_profile,
                srgb_profile,
                outputMode="RGB",
            )
            return converted
        except (ImageCms.PyCMSError, OSError, TypeError, ValueError):
            pass
    flattened = _flatten_transparency(image)
    return flattened if flattened.mode == "RGB" else flattened.convert("RGB")


def srgb_profile_bytes():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def optimize_meta_image(
    data,
    *,
    original_name="",
    output_edge=META_IMAGE_EDGE,
    output_format="JPEG",
):
    output_edge = int(output_edge or META_IMAGE_EDGE)
    if output_edge <= 0:
        raise AdsImageValidationError("The requested output size is invalid.")
    clean_output_format = str(output_format or "JPEG").upper()
    if clean_output_format not in {"JPEG", "PNG"}:
        raise AdsImageValidationError("The requested output format is invalid.")
    source_bytes = bytes(data or b"")
    if not source_bytes:
        raise AdsImageValidationError("This image is empty. Upload a valid JPEG, PNG or WebP image.")
    if len(source_bytes) > META_IMAGE_MAX_UPLOAD_BYTES:
        raise AdsImageValidationError("This image is too large. Upload a JPEG, PNG or WebP under 20 MB.")

    source = None
    oriented = None
    converted = None
    resized = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            source = Image.open(io.BytesIO(source_bytes))
            source_format = str(source.format or "").upper()
            if source_format not in META_IMAGE_ACCEPTED_FORMATS:
                raise AdsImageValidationError("Unsupported image type. Upload a JPEG, PNG or WebP image.")
            width, height = source.size
            if width <= 0 or height <= 0 or width * height > META_IMAGE_MAX_SOURCE_PIXELS:
                raise AdsImageValidationError("This image is too large to process safely.")
            source.verify()

            source.close()
            source = Image.open(io.BytesIO(source_bytes))
            source_format = str(source.format or "").upper()
            oriented = ImageOps.exif_transpose(source)
            oriented.load()

        if oriented.width != oriented.height:
            raise AdsImageValidationError(
                f"{original_name or 'This image'} is {oriented.width} x {oriented.height}. "
                "Upload a square image; Sports Cave OS will not crop the artwork automatically."
            )

        converted = _convert_to_srgb(oriented)
        resized = converted.resize(
            (output_edge, output_edge),
            Image.Resampling.LANCZOS,
        )
        output = io.BytesIO()
        if clean_output_format == "PNG":
            resized.save(
                output,
                format="PNG",
                optimize=False,
                compress_level=6,
                icc_profile=srgb_profile_bytes(),
            )
        else:
            resized.save(
                output,
                format="JPEG",
                quality=META_IMAGE_QUALITY,
                optimize=True,
                progressive=True,
                subsampling=0,
                icc_profile=srgb_profile_bytes(),
            )
        output_bytes = output.getvalue()
        with Image.open(io.BytesIO(output_bytes)) as check:
            check.load()
            if check.format != clean_output_format or check.mode != "RGB" or check.size != (
                output_edge,
                output_edge,
            ):
                raise AdsImageValidationError("The Meta-ready image could not be verified.")
        return {
            "source_hash": source_image_signature(source_bytes),
            "original_name": str(original_name or "image"),
            "source_format": source_format,
            "source_width": oriented.width,
            "source_height": oriented.height,
            "output_format": clean_output_format,
            "output_mode": "RGB",
            "output_width": output_edge,
            "output_height": output_edge,
            "output_size": len(output_bytes),
            "data": output_bytes,
        }
    except AdsImageValidationError:
        raise
    except (
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        OSError,
        SyntaxError,
        ValueError,
    ) as error:
        raise AdsImageValidationError(
            "This file is corrupt or is not a supported JPEG, PNG or WebP image."
        ) from error
    finally:
        for image in (resized, converted, oriented, source):
            if image is not None:
                try:
                    image.close()
                except Exception:
                    pass


def sanitize_product_filename(value, *, max_length=140):
    clean = "".join("_" if ord(char) < 32 else char for char in str(value or ""))
    clean = re.sub(r'[<>:"/\\|?*]', "_", clean)
    clean = re.sub(r"\s+", " ", clean).strip(" .")
    clean = re.sub(r"_+", "_", clean)
    if clean in {"", ".", ".."}:
        clean = "Sports Cave Product"
    return clean[: max(1, int(max_length))].rstrip(" .")


def account_iso_date(timezone_name="", *, now=None):
    clean_timezone = str(timezone_name or "").strip() or DEFAULT_ACCOUNT_TIMEZONE
    try:
        local_timezone = ZoneInfo(clean_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        local_timezone = ZoneInfo(DEFAULT_ACCOUNT_TIMEZONE)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(local_timezone).date().isoformat()


def build_meta_image_filename(product_name, campaign_type, *, position=1, iso_date):
    if campaign_type == "Carousel":
        suffix = f" - Carousel {int(position):02d} - {iso_date}.jpg"
    elif campaign_type == "Instant Experience":
        suffix = f" - Instant Experience {int(position):02d} - {iso_date}.jpg"
    else:
        raise ValueError("This campaign type does not support generated-image export.")
    product_limit = max(1, MAX_FILENAME_LENGTH - len(suffix))
    product = sanitize_product_filename(product_name, max_length=product_limit)
    return f"{product}{suffix}"
