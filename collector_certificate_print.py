"""Download-only rasterization of an existing issued certificate PDF.

Use a short-lived process: PDFium is not thread-safe and supplier rendering
must remain independent of account downloads. No stored asset is modified.
"""
import io
import subprocess
import sys
import threading
from pathlib import Path

_SLOTS = threading.BoundedSemaphore(2)
MAX_SOURCE_BYTES = 32 * 1024 * 1024


def rasterize(content):
    import pypdfium2 as pdfium
    if not content or len(content) > MAX_SOURCE_BYTES:
        raise ValueError("Certificate source exceeds the download limit.")
    with pdfium.PdfDocument(content) as document:
        if len(document) != 1:
            raise ValueError("A certificate must contain one page.")
        page = document[0]
        try:
            width, height = page.get_size()
            if width <= 0 or height <= 0 or width * height * (300 / 72) ** 2 > 40_000_000:
                raise ValueError("Certificate exceeds the print pixel limit.")
            bitmap = page.render(scale=300 / 72)
            try:
                with bitmap.to_pil().convert("RGB") as image:
                    output = io.BytesIO()
                    image.save(output, "JPEG", quality=95, subsampling=0, dpi=(300, 300))
                    return output.getvalue()
            finally:
                bitmap.close()
        finally:
            page.close()


def render_print_jpg(content):
    if not _SLOTS.acquire(timeout=10):
        raise ValueError("Certificate download is busy. Please try again.")
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve())],
            input=content, capture_output=True, timeout=45, check=False)
        if result.returncode or not result.stdout.startswith(b"\xff\xd8"):
            raise ValueError("The original certificate could not be prepared for download.")
        return result.stdout
    finally:
        _SLOTS.release()


if __name__ == "__main__":
    try:
        data = sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1)
        sys.stdout.buffer.write(rasterize(data))
    except Exception:
        sys.stderr.write("Certificate conversion failed.\n")
        sys.exit(1)
