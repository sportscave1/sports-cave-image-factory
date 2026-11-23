import io
from unittest.mock import patch
import pytest
from PIL import Image
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

import collector_vault as vault
import collector_vault_api as api
from collector_certificate_print import render_print_jpg
from certificate_service import write_simple_certificate_pdf


@pytest.fixture
def original_pdf(tmp_path):
    path = tmp_path / "original.pdf"
    write_simple_certificate_pdf(path, [("Original issued edition 027", 72, 420, 22, "1 1 1"), ("Certificate print download test", 72, 380, 16, "1 1 1")])
    return path.read_bytes()


def test_pdf_only_certificates_use_original_pdf_as_print_source():
    row = {"certificate_pdf_url": "https://cdn.shopify.com/original.pdf"}
    source = vault._asset_reference(row, "print")
    assert source["url"] == row["certificate_pdf_url"]
    assert source["render_print"] and source["mime_type"] == "application/pdf"
    assert row == {"certificate_pdf_url": "https://cdn.shopify.com/original.pdf"}


def test_existing_print_jpg_stays_the_original_file():
    source = vault._asset_reference({"certificate_print_jpg_url": "https://cdn.shopify.com/original.jpg"}, "print")
    assert source["url"].endswith("original.jpg") and not source.get("render_print")


def test_isolated_renderer_returns_full_page_300dpi_jpeg(original_pdf):
    original = bytes(original_pdf)
    result = render_print_jpg(original_pdf)
    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "JPEG" and image.width >= 3507 and image.height >= 2480
        assert image.info["dpi"] == (300, 300)
    assert original_pdf == original


def test_invalid_pdf_never_downloads_as_a_fake_jpg():
    with pytest.raises(ValueError):
        render_print_jpg(b"not a PDF")


@pytest.mark.parametrize("derive", [False, True])
def test_print_download_is_attachment_and_preserves_original_jpg_bytes(original_pdf, derive):
    asset = {"kind": "print", "filename": "Edition 027 - print.jpg", "storage": "https",
             "url": "https://cdn.shopify.com/original", "mime_type": "application/pdf" if derive else "image/jpeg"}
    if derive: asset["render_print"] = True
    original_jpg = b"\xff\xd8original-full-quality-print-file\xff\xd9"
    class Upstream:
        headers = {}
        closed = False
        def raise_for_status(self): pass
        def iter_content(self, chunk_size): yield original_pdf if derive else original_jpg
        def close(self): self.closed = True
    upstream = Upstream()
    application = Starlette(routes=[Route("/asset", api.collector_vault_asset)])
    with patch.object(vault, "resolve_asset_token", return_value=asset), patch.object(api.requests, "get", return_value=upstream):
        response = TestClient(application).get("/asset?token=owned")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.headers["content-disposition"].startswith("attachment;")
    assert "print.jpg" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store" and upstream.closed
    assert response.content.startswith(b"\xff\xd8")
    if not derive: assert response.content == original_jpg
