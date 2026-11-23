"""Presentation only: never assigns or changes a customer's edition number."""
from pathlib import Path
import re


FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
# Relative to the final master: below the body ornament, above Handcrafted.
TEXT_BAND = (0.665, 0.825)


def display_title(value):
    title = re.sub(r"\s+", " ", str(value or "Sports Cave Artwork")).strip()
    title = re.sub(r"\s+Wall\s+Art\s*$", "", title, flags=re.I)
    return re.sub(r"\s+[–—-]\s+", " — ", title).strip()


def display_number(number, total):
    # Formatting only; both values come from the existing allocation record.
    return f"No. {int(number):03d} of {int(total)}"


def _font(size, *, title=False):
    from PIL import ImageFont
    name = "SourceSerif4-Semibold.ttf" if title else "SourceSerif4-Regular.ttf"
    return ImageFont.truetype(str(FONT_DIR / name), size=max(1, int(size)))


def _wrap(draw, text, font, max_width):
    lines = []
    for word in text.split():
        candidate = f"{lines[-1]} {word}" if lines else word
        if lines and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
            lines.append(word)
        elif lines:
            lines[-1] = candidate
        else:
            lines.append(word)
    return lines


def text_layout(draw, size, product_title, edition_number, edition_total):
    width, height = size
    scale = width / 1536
    max_width = width * 0.58
    title = display_title(product_title)
    for font_size in range(max(1, round(54 * scale)), 0, -1):
        title_font = _font(font_size, title=True)
        lines = _wrap(draw, title, title_font, max_width)
        if len(lines) <= 2 and all(draw.textbbox((0, 0), line, font=title_font)[2] <= max_width for line in lines):
            break
    number = display_number(edition_number, edition_total)
    number_font = _font(round(42 * scale))
    for font_size in range(round(42 * scale), 0, -1):
        number_font = _font(font_size)
        if draw.textbbox((0, 0), number, font=number_font)[2] <= max_width:
            break
    entries = [(line, title_font) for line in lines] + [(number, number_font)]
    boxes = [draw.textbbox((0, 0), text, font=font) for text, font in entries]
    gaps = [round(10 * scale)] * max(0, len(lines) - 1) + [round(17 * scale)]
    block_height = sum(box[3] - box[1] for box in boxes) + sum(gaps)
    band_top, band_bottom = (height * fraction for fraction in TEXT_BAND)
    if block_height > band_bottom - band_top:
        raise ValueError("Certificate title does not fit the template text area")
    top = (band_top + band_bottom - block_height) / 2
    result = []
    for index, ((text, font), box) in enumerate(zip(entries, boxes)):
        text_width, text_height = box[2] - box[0], box[3] - box[1]
        left = (width - text_width) / 2
        result.append({"text": text, "font": font,
                       "position": (left - box[0], top - box[1]),
                       "bounds": (left, top, left + text_width, top + text_height)})
        top += text_height + (gaps[index] if index < len(gaps) else 0)
    return result


def draw_certificate_text(draw, size, product_title, edition_number, edition_total):
    layout = text_layout(draw, size, product_title, edition_number, edition_total)
    for item in layout:
        draw.text(item["position"], item["text"], font=item["font"], fill=(0, 0, 0))
    return layout
