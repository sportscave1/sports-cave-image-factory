from pathlib import Path
import re


BASE_DIR = Path(__file__).resolve().parent
CERTIFICATE_TEMPLATE_PRINT_PATH = BASE_DIR / "assets" / "certificates" / "certificate-template-print.png"
CERTIFICATE_TEMPLATE_PREVIEW_PATH = BASE_DIR / "assets" / "certificates" / "certificate-template-preview.webp"


def safe_filename_part(value):
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip().lower())
    return cleaned.strip("-") or "sports-cave"


def escape_pdf_text(value):
    return str(value or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_certificate_pdf(path, lines):
    width = 841.89
    height = 595.28
    content = [
        "0.043 0.043 0.051 rg",
        f"0 0 {width:.2f} {height:.2f} re f",
        "0.831 0.647 0.298 RG",
        "3 w",
        "42 42 758 512 re S",
        "0.831 0.647 0.298 rg",
        "72 470 698 2 re f",
    ]
    for text, x, y, size, color in lines:
        if color == "gold":
            content.append("0.831 0.647 0.298 rg")
        else:
            content.append("0.961 0.949 0.918 rg")
        content.append(f"BT /F1 {size} Tf {x} {y} Td ({escape_pdf_text(text)}) Tj ET")
    stream = "\n".join(content).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 841.89 595.28] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(pdf))


def certificate_id(order_name, edition_number, handle=""):
    cleaned_order = safe_filename_part(str(order_name or "order").replace("#", ""))
    if handle:
        cleaned_handle = safe_filename_part(handle).upper()
        return f"SC-{cleaned_order.upper()}-{cleaned_handle}-EDITION-{int(edition_number):03d}"
    return f"SC-{cleaned_order.upper()}-{int(edition_number):04d}"


def format_edition_number(edition_number, edition_total):
    return f"#{int(edition_number):03d}/{int(edition_total)}"


def certificate_pdf_filename(order_name, handle, edition_number, edition_total):
    return (
        f"sports-cave-certificate-{safe_filename_part(order_name)}-"
        f"{safe_filename_part(handle)}-edition-{int(edition_number):03d}-"
        f"of-{int(edition_total or 0)}.pdf"
    )


def certificate_print_jpg_filename(order_name, handle, edition_number):
    return (
        f"sports-cave-certificate-{safe_filename_part(order_name)}-"
        f"{safe_filename_part(handle)}-edition-{int(edition_number):03d}-print.jpg"
    )


def certificate_preview_webp_filename(order_name, handle, edition_number):
    return (
        f"sports-cave-certificate-{safe_filename_part(order_name)}-"
        f"{safe_filename_part(handle)}-edition-{int(edition_number):03d}-preview.webp"
    )


def certificate_template_status():
    return {
        "print_template_path": str(CERTIFICATE_TEMPLATE_PRINT_PATH),
        "preview_template_path": str(CERTIFICATE_TEMPLATE_PREVIEW_PATH),
        "print_template_found": CERTIFICATE_TEMPLATE_PRINT_PATH.exists(),
        "preview_template_found": CERTIFICATE_TEMPLATE_PREVIEW_PATH.exists(),
    }


def font_candidates():
    return [
        BASE_DIR / "assets" / "fonts" / "DejaVuSerif.ttf",
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
        Path("/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf"),
        Path("C:/Windows/Fonts/georgia.ttf"),
        Path("C:/Windows/Fonts/times.ttf"),
    ]


def load_serif_font(size):
    from PIL import ImageFont

    for font_path in font_candidates():
        if font_path.exists():
            return ImageFont.truetype(str(font_path), size=size)
    return ImageFont.load_default()


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def truncate_to_fit(draw, text, font, max_width):
    if text_width(draw, text, font) <= max_width:
        return text
    ellipsis = "..."
    candidate = str(text or "")
    while candidate and text_width(draw, candidate + ellipsis, font) > max_width:
        candidate = candidate[:-1]
    return (candidate.rstrip() + ellipsis) if candidate else ellipsis


def fit_font(draw, text, max_width, max_size, min_size):
    for size in range(int(max_size), int(min_size) - 1, -1):
        font = load_serif_font(size)
        if text_width(draw, text, font) <= max_width:
            return font, text
    font = load_serif_font(int(min_size))
    return font, truncate_to_fit(draw, text, font, max_width)


def draw_fitted_text(draw, text, x_start, x_end, y_center, max_size, min_size):
    max_width = max(1, x_end - x_start)
    font, fitted_text = fit_font(draw, text, max_width, max_size, min_size)
    try:
        draw.text((x_start, y_center), fitted_text, fill=(0, 0, 0), font=font, anchor="lm")
    except TypeError:
        bbox = draw.textbbox((0, 0), fitted_text, font=font)
        text_height = bbox[3] - bbox[1]
        draw.text((x_start, y_center - text_height / 2), fitted_text, fill=(0, 0, 0), font=font)
    return fitted_text


def render_template_certificate_image(
    *,
    product_title,
    edition_number,
    edition_total,
    template_path=None,
    target_size=None,
):
    from PIL import Image, ImageDraw

    template_path = Path(template_path or CERTIFICATE_TEMPLATE_PRINT_PATH)
    if not template_path.exists():
        raise FileNotFoundError(f"Certificate template missing: {template_path}")

    with Image.open(template_path) as template:
        certificate = template.convert("RGB")
    if target_size:
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS
        certificate = certificate.resize(tuple(int(item) for item in target_size), resample)

    draw = ImageDraw.Draw(certificate)
    width, height = certificate.size
    scale = width / 1536

    draw_fitted_text(
        draw,
        str(product_title or "Sports Cave Artwork"),
        int(width * 0.41),
        int(width * 0.82),
        int(height * 0.682),
        max_size=max(13, int(25 * scale)),
        min_size=max(10, int(13 * scale)),
    )
    draw_fitted_text(
        draw,
        format_edition_number(edition_number, edition_total),
        int(width * 0.43),
        int(width * 0.54),
        int(height * 0.744),
        max_size=max(15, int(27 * scale)),
        min_size=max(10, int(15 * scale)),
    )
    return certificate


def generate_template_certificate_pdf(
    output_dir,
    *,
    product_title,
    edition_number,
    edition_total,
    order_name,
    shopify_handle="",
    filename="",
):
    if not CERTIFICATE_TEMPLATE_PRINT_PATH.exists():
        raise FileNotFoundError(f"Certificate template missing: {CERTIFICATE_TEMPLATE_PRINT_PATH}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    handle_part = safe_filename_part(shopify_handle or product_title)
    filename = filename or certificate_pdf_filename(order_name, handle_part, edition_number, edition_total)
    pdf_path = output_dir / filename

    certificate = render_template_certificate_image(
        product_title=product_title,
        edition_number=edition_number,
        edition_total=edition_total,
        template_path=CERTIFICATE_TEMPLATE_PRINT_PATH,
    )

    certificate.save(pdf_path, "PDF", resolution=300.0)
    certificate.close()
    return str(pdf_path)


def generate_certificate_preview_png(
    output_dir,
    *,
    product_title,
    edition_number,
    edition_total,
    order_name,
    shopify_handle="",
):
    template_path = (
        CERTIFICATE_TEMPLATE_PREVIEW_PATH
        if CERTIFICATE_TEMPLATE_PREVIEW_PATH.exists()
        else CERTIFICATE_TEMPLATE_PRINT_PATH
    )
    if not template_path.exists():
        raise FileNotFoundError(f"Certificate template missing: {template_path}")

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    handle_part = safe_filename_part(shopify_handle or product_title)
    filename = (
        f"certificate_{safe_filename_part(order_name)}_{handle_part}"
        f"_edition_{int(edition_number):03d}_preview.png"
    )
    preview_path = output_dir / filename

    certificate = render_template_certificate_image(
        product_title=product_title,
        edition_number=edition_number,
        edition_total=edition_total,
        template_path=template_path,
    )
    certificate.save(preview_path, "PNG")
    certificate.close()
    return str(preview_path)


def generate_certificate_print_jpg(
    output_dir,
    *,
    product_title,
    edition_number,
    edition_total,
    order_name,
    shopify_handle="",
    quality=94,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    handle_part = safe_filename_part(shopify_handle or product_title)
    output_path = output_dir / certificate_print_jpg_filename(order_name, handle_part, edition_number)
    certificate = render_template_certificate_image(
        product_title=product_title,
        edition_number=edition_number,
        edition_total=edition_total,
        template_path=CERTIFICATE_TEMPLATE_PRINT_PATH,
        target_size=(3508, 2480),
    )
    certificate.save(output_path, "JPEG", quality=int(quality), optimize=True, dpi=(300, 300))
    certificate.close()
    return str(output_path)


def generate_certificate_preview_webp(
    output_dir,
    *,
    product_title,
    edition_number,
    edition_total,
    order_name,
    shopify_handle="",
    width=1200,
    quality=82,
):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    handle_part = safe_filename_part(shopify_handle or product_title)
    output_path = output_dir / certificate_preview_webp_filename(order_name, handle_part, edition_number)
    template_path = (
        CERTIFICATE_TEMPLATE_PREVIEW_PATH
        if CERTIFICATE_TEMPLATE_PREVIEW_PATH.exists()
        else CERTIFICATE_TEMPLATE_PRINT_PATH
    )
    with render_template_certificate_image(
        product_title=product_title,
        edition_number=edition_number,
        edition_total=edition_total,
        template_path=template_path,
    ) as certificate:
        original_width, original_height = certificate.size
        target_width = int(width)
        target_height = max(1, round(original_height * (target_width / max(original_width, 1))))
        try:
            from PIL import Image

            resample = Image.Resampling.LANCZOS
        except AttributeError:
            from PIL import Image

            resample = Image.LANCZOS
        preview = certificate.resize((target_width, target_height), resample)
        preview.save(output_path, "WEBP", quality=int(quality), method=6)
        preview.close()
    return str(output_path)


def generate_certificate_pdf(
    output_dir,
    *,
    product_title,
    edition_number,
    edition_total,
    order_name,
    customer_name="",
    assigned_at="",
    shopify_handle="",
    filename="",
    allow_fallback=False,
):
    try:
        return generate_template_certificate_pdf(
            output_dir,
            product_title=product_title,
            edition_number=edition_number,
            edition_total=edition_total,
            order_name=order_name,
            shopify_handle=shopify_handle,
            filename=filename,
        )
    except FileNotFoundError:
        if not allow_fallback:
            raise
        return generate_simple_certificate_pdf(
            output_dir,
            product_title=product_title,
            edition_number=edition_number,
            edition_total=edition_total,
            order_name=order_name,
            customer_name=customer_name,
            assigned_at=assigned_at,
            filename=filename,
        )
    except Exception:
        raise


def generate_simple_certificate_pdf(
    output_dir,
    *,
    product_title,
    edition_number,
    edition_total,
    order_name,
    customer_name,
    assigned_at,
    filename="",
):
    filename = filename or certificate_pdf_filename(order_name, product_title, edition_number, edition_total)
    pdf_path = Path(output_dir) / filename
    edition_text = f"{int(edition_number):03d}/{int(edition_total):03d}"
    lines = [
        ("SPORTS CAVE", 72, 505, 40, "gold"),
        ("LIMITED EDITION CERTIFICATE", 72, 455, 24, "white"),
        (str(product_title or "Sports Cave Artwork")[:72], 72, 365, 26, "white"),
        (f"Edition {edition_text}", 72, 315, 30, "gold"),
        (f"Order: {order_name or 'Shopify Order'}", 72, 250, 17, "white"),
        (f"Collector: {customer_name or 'Sports Cave Collector'}", 72, 220, 17, "white"),
        (f"Date assigned: {assigned_at or ''}", 72, 190, 17, "white"),
        ("This certifies this Sports Cave artwork as part of a numbered collector release.", 72, 105, 15, "white"),
    ]
    write_simple_certificate_pdf(pdf_path, lines)
    return str(pdf_path)
