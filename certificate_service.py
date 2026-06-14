from pathlib import Path
import re


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


def generate_certificate_pdf(output_dir, *, product_title, edition_number, edition_total, order_name, customer_name, assigned_at):
    filename = (
        f"certificate_{safe_filename_part(order_name)}_{safe_filename_part(product_title)}"
        f"_edition_{int(edition_number):03d}.pdf"
    )
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
