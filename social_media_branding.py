import hashlib
import io
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageCms, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parent
LOGO_ASSET_PATH = ROOT / "assets" / "sports-cave-logo-landscape-gold-transparent.webp"
FONT_BOLD_PATH = ROOT / "assets" / "fonts" / "Montserrat-Bold.ttf"
FONT_MEDIUM_PATH = ROOT / "assets" / "fonts" / "Montserrat-Medium.ttf"

LOGO_ASSET_RELATIVE_PATH = "assets/sports-cave-logo-landscape-gold-transparent.webp"
LOGO_SOURCE_URL = (
    "https://www.sportscaveshop.com/cdn/shop/files/"
    "sports-cave-logo-landscape-gold-transparent-optimised_1.webp"
    "?v=1779715351&width=1000"
)
LOGO_SHA256 = "957e409f6358dcee53ab1336c05439e07147ca9cb0da7756cd1e2ac329ae727e"
FONT_BOLD_SHA256 = "bc6e854971cea46b463be6f9eef4d9cd52f51cfc1fc0dd90c9d3e6483dc0ec61"
FONT_MEDIUM_SHA256 = "dae47428bb041f9716604e0e07b5b0c8585b3bdd8183362f75c69fe7bb3cfaf4"

BRAND_COLOURS = {
    "near_black": "#0B0B0D",
    "charcoal": "#1E1E23",
    "gold": "#D4A54C",
    "off_white": "#F5F2EA",
}
BRAND_FONT_FAMILY = "Montserrat"
LOGO_VARIANT = "Verified website gold transparent wordmark"
IMAGE_EXTENSIONS = frozenset({"jpg", "jpeg", "png", "webp", "gif"})
VIDEO_EXTENSIONS = frozenset({"mp4", "mov", "m4v", "webm"})

FORMAT_PROFILES = {
    "Story sequence": {
        "width": 1080,
        "height": 1920,
        "safe_zone": {"left": 72, "right": 72, "top": 220, "bottom": 320},
        "logo_width_fraction": 0.10,
    },
    "Launch sequence": {
        "width": 1080,
        "height": 1920,
        "safe_zone": {"left": 72, "right": 72, "top": 220, "bottom": 320},
        "logo_width_fraction": 0.10,
    },
    "Reel": {
        "width": 1080,
        "height": 1920,
        "safe_zone": {"left": 72, "right": 72, "top": 220, "bottom": 320},
        "logo_width_fraction": 0.09,
    },
    "Feed carousel": {
        "width": 1080,
        "height": 1350,
        "safe_zone": {"left": 64, "right": 64, "top": 72, "bottom": 96},
        "logo_width_fraction": 0.10,
    },
    "Static feed post": {
        "width": 1080,
        "height": 1350,
        "safe_zone": {"left": 64, "right": 64, "top": 72, "bottom": 96},
        "logo_width_fraction": 0.10,
    },
    "UGC/collector proof": {
        "width": 1080,
        "height": 1350,
        "safe_zone": {"left": 64, "right": 64, "top": 72, "bottom": 96},
        "logo_width_fraction": 0.08,
    },
    "Pinterest Pin": {
        "width": 1000,
        "height": 1500,
        "safe_zone": {"left": 64, "right": 64, "top": 80, "bottom": 112},
        "logo_width_fraction": 0.10,
    },
}


class SocialBrandAssetError(RuntimeError):
    pass


class SocialBrandClaimError(RuntimeError):
    pass


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require_brand_assets():
    required = (
        (LOGO_ASSET_PATH, LOGO_SHA256, "approved Sports Cave website logo"),
        (FONT_BOLD_PATH, FONT_BOLD_SHA256, "Montserrat Bold brand font"),
        (FONT_MEDIUM_PATH, FONT_MEDIUM_SHA256, "Montserrat Medium brand font"),
    )
    for path, expected_hash, label in required:
        if not path.is_file():
            raise SocialBrandAssetError(
                f"The {label} is missing at {path}. Branded exports are disabled."
            )
        if _sha256(path) != expected_hash:
            raise SocialBrandAssetError(
                f"The {label} at {path} does not match the approved asset hash. "
                "Branded exports are disabled."
            )
    return True


def brand_manifest():
    require_brand_assets()
    return {
        "logo_asset": LOGO_ASSET_RELATIVE_PATH,
        "logo_source_url": LOGO_SOURCE_URL,
        "logo_sha256": LOGO_SHA256,
        "logo_variant": LOGO_VARIANT,
        "font_family": BRAND_FONT_FAMILY,
        "font_files": {
            "headline": str(FONT_BOLD_PATH.relative_to(ROOT)).replace("\\", "/"),
            "supporting": str(FONT_MEDIUM_PATH.relative_to(ROOT)).replace("\\", "/"),
        },
        "colours": dict(BRAND_COLOURS),
    }


def _profile_for_format(content_format):
    return dict(FORMAT_PROFILES.get(content_format) or FORMAT_PROFILES["Static feed post"])


def build_branding_plan(
    *,
    content_format,
    label,
    headline,
    subline="",
    cta="",
    logo_placement="top-left",
    text_placement="upper-left below logo",
    native_sticker_space="none",
    publish_ready=True,
    blockers=(),
):
    manifest = brand_manifest()
    profile = _profile_for_format(content_format)
    is_ugc = content_format == "UGC/collector proof"
    return {
        "label": str(label or "Creative"),
        "content_format": content_format,
        "canvas": {
            "width": int(profile["width"]),
            "height": int(profile["height"]),
            "colour_space": "sRGB",
        },
        "clean_master": {
            "required": True,
            "generated_overlays": False,
            "instruction": (
                "Generate and retain a clean product-led master with safe negative space. "
                "Do not ask the image model to render a logo, headline, CTA or native sticker."
            ),
        },
        "branded_final": {
            "required": True,
            "deterministic_compositing": True,
            "publish_ready": bool(publish_ready and not blockers),
            "blockers": tuple(str(value) for value in blockers if str(value).strip()),
        },
        "logo": {
            "asset": manifest["logo_asset"],
            "source_url": manifest["logo_source_url"],
            "sha256": manifest["logo_sha256"],
            "variant": manifest["logo_variant"],
            "placement": logo_placement,
            "width_percent": round(float(profile["logo_width_fraction"]) * 100, 1),
            "clear_space": "At least one logo-height on every side where practical.",
            "instruction": (
                "Composite this exact verified file at export time. Never regenerate, "
                "redraw, type, recolour, crop, stretch or approximate the logo."
            ),
        },
        "copy": {
            "headline": str(headline or "").strip(),
            "subline": str(subline or "").strip(),
            "cta": str(cta or "").strip(),
        },
        "typography": {
            "family": manifest["font_family"],
            "headline_file": manifest["font_files"]["headline"],
            "supporting_file": manifest["font_files"]["supporting"],
            "headline_style": "Montserrat Bold, 3-7 words where possible, mobile-first",
            "supporting_style": "Montserrat Medium, short and restrained",
        },
        "colours": manifest["colours"],
        "placement": {
            "text": text_placement,
            "safe_zone": dict(profile["safe_zone"]),
            "native_sticker_space": native_sticker_space,
            "product_protection": (
                "Do not cover a face, athlete, car, product title, edition badge, plaque, "
                "signature or important artwork detail. The product remains the hero."
            ),
        },
        "treatment": (
            "Restrained UGC treatment: exact small logo plus branded end treatment."
            if is_ugc
            else "Premium dark collector treatment with one restrained gold accent."
        ),
    }


def branding_plan_text(plan):
    copy = plan["copy"]
    safe = plan["placement"]["safe_zone"]
    blockers = plan["branded_final"].get("blockers") or ()
    blocker_text = ", ".join(blockers) if blockers else "none"
    return f"""SPORTS CAVE BRANDING AND OVERLAY PLAN
Output both versions:
1. CLEAN MASTER - no generated logo, advertising text, CTA, button or native platform sticker.
2. BRANDED FINAL - deterministic application compositing using the exact approved assets below.

Exact logo asset: {plan['logo']['asset']}
Verified storefront source: {plan['logo']['source_url']}
Approved asset SHA-256: {plan['logo']['sha256']}
Logo variant: {plan['logo']['variant']}
Logo placement: {plan['logo']['placement']}
Logo size: {plan['logo']['width_percent']}% of canvas width, preserving original aspect ratio and clear space.
Logo rule: {plan['logo']['instruction']}
Exact headline: {copy['headline'] or '[no headline on this beat]'}
Exact subline: {copy['subline'] or '[no subline]'}
Exact CTA: {copy['cta'] or '[no CTA on this creative]'}
Text placement: {plan['placement']['text']}
Text hierarchy: {plan['typography']['headline_style']}; {plan['typography']['supporting_style']}.
Approved font: {plan['typography']['family']} using {plan['typography']['headline_file']} and {plan['typography']['supporting_file']}.
Brand colours: near-black {plan['colours']['near_black']}; charcoal {plan['colours']['charcoal']}; gold {plan['colours']['gold']}; off-white {plan['colours']['off_white']}.
Safe zone: left {safe['left']} px, right {safe['right']} px, top {safe['top']} px, bottom {safe['bottom']} px.
Native sticker space: {plan['placement']['native_sticker_space']}.
Product protection: {plan['placement']['product_protection']}
Treatment: {plan['treatment']}
Publish-ready: {'yes' if plan['branded_final']['publish_ready'] else 'no'}
Publish blockers: {blocker_text}

The clean visual is the source master. Apply the exact logo and exact supplied copy only through the deterministic Sports Cave export layer. Never ask an image or video model to recreate the logo or final typography from memory. Never fake a native poll, quiz, slider, question box or link sticker."""


def _hex_colour(value):
    text = str(value or "").lstrip("#")
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


def _srgb_profile_bytes():
    try:
        return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    except Exception:
        return None


def _font(path, size):
    return ImageFont.truetype(str(path), max(int(size), 10))


def _wrapped_lines(draw, text, font, max_width):
    words = str(text or "").split()
    if not words:
        return []
    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bounds = draw.textbbox((0, 0), candidate, font=font)
        if bounds[2] - bounds[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _fitted_text(draw, text, *, max_width, preferred_size, minimum_size):
    size = int(preferred_size)
    while size > minimum_size:
        font = _font(FONT_BOLD_PATH, size)
        lines = _wrapped_lines(draw, text, font, max_width)
        if len(lines) <= 3 and all(
            draw.textbbox((0, 0), line, font=font)[2] <= max_width
            for line in lines
        ):
            return font, lines
        size -= 2
    font = _font(FONT_BOLD_PATH, minimum_size)
    return font, _wrapped_lines(draw, text, font, max_width)


def _draw_backdrop(overlay, *, top_height, bottom_height=0):
    width, height = overlay.size
    near_black = _hex_colour(BRAND_COLOURS["near_black"])
    fade = Image.new("RGBA", overlay.size, (0, 0, 0, 0))
    fade_draw = ImageDraw.Draw(fade)
    bounded_top = min(top_height, height)
    for y in range(bounded_top):
        strength = int(178 * (1 - (y / max(bounded_top, 1))) ** 1.7)
        fade_draw.line((0, y, width, y), fill=(*near_black, strength))
    if bottom_height:
        start = max(height - bottom_height, 0)
        for y in range(start, height):
            strength = int(172 * ((y - start) / max(bottom_height, 1)) ** 1.5)
            fade_draw.line((0, y, width, y), fill=(*near_black, strength))
    overlay.alpha_composite(fade)


def _logo_position(plan, logo_size, canvas_size):
    safe = plan["placement"]["safe_zone"]
    canvas_width, _ = canvas_size
    logo_width, _ = logo_size
    placement = plan["logo"]["placement"]
    x = safe["left"]
    if placement == "top-right":
        x = canvas_width - safe["right"] - logo_width
    return int(x), int(safe["top"])


def render_overlay(plan, *, mode="full"):
    require_brand_assets()
    width = int(plan["canvas"]["width"])
    height = int(plan["canvas"]["height"])
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    safe = plan["placement"]["safe_zone"]
    copy = plan["copy"]

    draw_logo = mode in {"full", "watermark"}
    draw_opening = mode in {"full", "opening"}
    draw_end = mode in {"full", "end"}
    if draw_opening:
        _draw_backdrop(
            overlay,
            top_height=int(height * 0.42),
            bottom_height=int(height * 0.27) if draw_end and copy.get("cta") else 0,
        )
    elif draw_end and copy.get("cta"):
        _draw_backdrop(overlay, top_height=0, bottom_height=int(height * 0.30))

    logo_bottom = safe["top"]
    if draw_logo:
        logo = Image.open(LOGO_ASSET_PATH).convert("RGBA")
        logo_width = int(width * (float(plan["logo"]["width_percent"]) / 100))
        logo_height = max(int(logo.height * (logo_width / logo.width)), 1)
        logo = logo.resize((logo_width, logo_height), Image.Resampling.LANCZOS)
        logo_x, logo_y = _logo_position(plan, logo.size, overlay.size)
        overlay.alpha_composite(logo, (logo_x, logo_y))
        logo_bottom = logo_y + logo_height

    text_x = int(safe["left"])
    max_text_width = width - safe["left"] - safe["right"]
    gold = _hex_colour(BRAND_COLOURS["gold"])
    off_white = _hex_colour(BRAND_COLOURS["off_white"])
    if draw_opening:
        subline = copy.get("subline") or ""
        headline = copy.get("headline") or ""
        if draw_end and headline == copy.get("cta"):
            headline = ""
        text_y = max(logo_bottom + int(height * 0.025), safe["top"])
        if subline:
            subline_font = _font(FONT_MEDIUM_PATH, max(int(width * 0.026), 22))
            draw.text(
                (text_x, text_y),
                subline,
                font=subline_font,
                fill=(*gold, 255),
                stroke_width=1,
                stroke_fill=(*_hex_colour(BRAND_COLOURS["near_black"]), 180),
            )
            text_y += int(subline_font.size * 1.75)
        if headline:
            headline_font, lines = _fitted_text(
                draw,
                headline,
                max_width=max_text_width,
                preferred_size=max(int(width * 0.072), 48),
                minimum_size=max(int(width * 0.042), 34),
            )
            line_height = int(headline_font.size * 1.12)
            for line in lines:
                draw.text(
                    (text_x, text_y),
                    line,
                    font=headline_font,
                    fill=(*off_white, 255),
                    stroke_width=max(int(width * 0.002), 1),
                    stroke_fill=(*_hex_colour(BRAND_COLOURS["near_black"]), 210),
                )
                text_y += line_height

    if draw_end and copy.get("cta"):
        cta = str(copy["cta"])
        cta_font, cta_lines = _fitted_text(
            draw,
            cta,
            max_width=max_text_width,
            preferred_size=max(int(width * 0.046), 34),
            minimum_size=max(int(width * 0.032), 26),
        )
        line_height = int(cta_font.size * 1.16)
        block_height = line_height * len(cta_lines)
        cta_y = height - safe["bottom"] - block_height
        accent_y = max(cta_y - int(height * 0.025), 0)
        draw.rounded_rectangle(
            (
                text_x,
                accent_y,
                text_x + int(width * 0.12),
                accent_y + max(int(height * 0.004), 4),
            ),
            radius=2,
            fill=(*gold, 255),
        )
        for line in cta_lines:
            draw.text(
                (text_x, cta_y),
                line,
                font=cta_font,
                fill=(*off_white, 255),
                stroke_width=max(int(width * 0.0015), 1),
                stroke_fill=(*_hex_colour(BRAND_COLOURS["near_black"]), 210),
            )
            cta_y += line_height
    return overlay


def _fit_image_to_canvas(image, size):
    source = ImageOps.exif_transpose(image).convert("RGB")
    fitted = ImageOps.contain(source, size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", size, _hex_colour(BRAND_COLOURS["near_black"]))
    x = (size[0] - fitted.width) // 2
    y = (size[1] - fitted.height) // 2
    canvas.paste(fitted, (x, y))
    return canvas


def prepare_clean_image(data, plan):
    image = Image.open(io.BytesIO(data))
    size = (int(plan["canvas"]["width"]), int(plan["canvas"]["height"]))
    clean = _fit_image_to_canvas(image, size)
    output = io.BytesIO()
    save_options = {"format": "PNG", "optimize": True}
    profile = _srgb_profile_bytes()
    if profile:
        save_options["icc_profile"] = profile
    clean.save(output, **save_options)
    return output.getvalue()


def compose_branded_image(clean_png, plan):
    if not plan["branded_final"]["publish_ready"]:
        blockers = ", ".join(plan["branded_final"].get("blockers") or ())
        raise SocialBrandClaimError(
            f"The branded final is not publish-ready: {blockers or 'verification required'}."
        )
    clean = Image.open(io.BytesIO(clean_png)).convert("RGBA")
    overlay = render_overlay(plan, mode="full")
    branded = Image.alpha_composite(clean, overlay).convert("RGB")
    output = io.BytesIO()
    save_options = {"format": "PNG", "optimize": True}
    profile = _srgb_profile_bytes()
    if profile:
        save_options["icc_profile"] = profile
    branded.save(output, **save_options)
    return output.getvalue()


def _ffmpeg_executable():
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as error:
        raise SocialBrandAssetError(
            "The deterministic video branding runtime is unavailable. "
            "Install the configured imageio-ffmpeg dependency."
        ) from error


def _write_overlay(path, plan, mode):
    overlay = render_overlay(plan, mode=mode)
    overlay.save(path, format="PNG", optimize=True)


def _video_filter(width, height):
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x0B0B0D,"
        "setsar=1"
    )


def _run_ffmpeg(command):
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=180,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-1200:]
        raise SocialBrandAssetError(
            f"The deterministic video export failed. {detail}"
        )


def prepare_clean_video(data, extension, plan):
    executable = _ffmpeg_executable()
    width = int(plan["canvas"]["width"])
    height = int(plan["canvas"]["height"])
    suffix = f".{str(extension or 'mp4').casefold().lstrip('.')}"
    with tempfile.TemporaryDirectory(prefix="sports-cave-social-") as temp:
        temp_path = Path(temp)
        source = temp_path / f"source{suffix}"
        output = temp_path / "clean-master.mp4"
        source.write_bytes(data)
        command = [
            executable,
            "-y",
            "-i",
            str(source),
            "-vf",
            _video_filter(width, height),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output),
        ]
        _run_ffmpeg(command)
        return output.read_bytes()


def _video_duration(path):
    try:
        import imageio_ffmpeg

        reader = imageio_ffmpeg.read_frames(str(path), pix_fmt="rgb24")
        metadata = next(reader)
        reader.close()
        return max(float(metadata.get("duration") or 0), 0)
    except Exception:
        return 0


def compose_branded_video(clean_mp4, plan):
    if not plan["branded_final"]["publish_ready"]:
        blockers = ", ".join(plan["branded_final"].get("blockers") or ())
        raise SocialBrandClaimError(
            f"The branded final is not publish-ready: {blockers or 'verification required'}."
        )
    executable = _ffmpeg_executable()
    with tempfile.TemporaryDirectory(prefix="sports-cave-social-brand-") as temp:
        temp_path = Path(temp)
        source = temp_path / "clean-master.mp4"
        logo_overlay = temp_path / "logo.png"
        opening_overlay = temp_path / "opening.png"
        end_overlay = temp_path / "end.png"
        output = temp_path / "branded-final.mp4"
        source.write_bytes(clean_mp4)
        _write_overlay(logo_overlay, plan, "watermark")
        _write_overlay(opening_overlay, plan, "opening")
        _write_overlay(end_overlay, plan, "end")
        duration = _video_duration(source)
        if duration <= 0:
            raise SocialBrandAssetError(
                "The clean video duration could not be verified for branded export."
            )
        end_start = max(duration - 3.0, 0)
        filter_complex = (
            "[0:v][1:v]overlay=0:0:format=auto[logo];"
            "[logo][2:v]overlay=0:0:format=auto:enable='between(t,0,2)'[opening];"
            f"[opening][3:v]overlay=0:0:format=auto:enable='gte(t,{end_start:.3f})'[final]"
        )
        command = [
            executable,
            "-y",
            "-i",
            str(source),
            "-loop",
            "1",
            "-i",
            str(logo_overlay),
            "-loop",
            "1",
            "-i",
            str(opening_overlay),
            "-loop",
            "1",
            "-i",
            str(end_overlay),
            "-filter_complex",
            filter_complex,
            "-map",
            "[final]",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-colorspace",
            "bt709",
            "-color_primaries",
            "bt709",
            "-color_trc",
            "bt709",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            "-t",
            f"{duration:.3f}",
            "-shortest",
            str(output),
        ]
        _run_ffmpeg(command)
        return output.read_bytes()


def prepare_clean_asset(data, extension, plan):
    suffix = str(extension or "").casefold().lstrip(".")
    if suffix in IMAGE_EXTENSIONS:
        return prepare_clean_image(data, plan), "png"
    if suffix in VIDEO_EXTENSIONS:
        return prepare_clean_video(data, suffix, plan), "mp4"
    raise SocialBrandAssetError(f"Unsupported Social Media asset type: {suffix or 'unknown'}")


def compose_branded_asset(clean_data, clean_extension, plan):
    suffix = str(clean_extension or "").casefold().lstrip(".")
    if suffix == "png":
        return compose_branded_image(clean_data, plan), "png"
    if suffix == "mp4":
        return compose_branded_video(clean_data, plan), "mp4"
    raise SocialBrandAssetError(f"Unsupported clean-master type: {suffix or 'unknown'}")
