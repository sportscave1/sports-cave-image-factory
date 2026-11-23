import base64
import io
from unittest.mock import patch

import pytest
from PIL import Image
import collector_vault as vault


def photo_payload(kind, mode="RGB", color="red"):
    with Image.new(mode, (12, 8), color) as image:
        stream = io.BytesIO()
        image.save(stream, kind)
    return {"mime_type": {"WEBP": "image/webp", "PNG": "image/png", "JPEG": "image/jpeg"}[kind],
            "filename": "collector-photo", "base64": base64.b64encode(stream.getvalue()).decode()}


@pytest.mark.parametrize("kind", ["JPEG", "PNG", "WEBP"])
def test_all_account_photo_types_produce_judgeme_supported_content(kind):
    result = vault.validate_review_photo(photo_payload(kind))
    assert result["mime_type"] in {"image/jpeg", "image/png"}
    assert result["extension"] in {".jpg", ".png"}
    with Image.open(io.BytesIO(result["bytes"])) as image:
        assert image.format in {"JPEG", "PNG"}
        assert image.size == (12, 8)


def test_transparent_webp_uses_white_background_for_review_photo():
    result = vault.validate_review_photo(photo_payload("WEBP", "RGBA", (0, 0, 0, 0)))
    with Image.open(io.BytesIO(result["bytes"])) as image:
        assert all(channel > 245 for channel in image.getpixel((5, 5)))


def deliver(status, result=None, content=b"json"):
    class Response:
        status_code = status
        def json(self):
            return result
    response = Response()
    response.content = content
    captured = {}
    def post(url, **options):
        captured.update(url=url, **options)
        return response
    with patch.object(vault, "lookup_judgeme_product", return_value={"id": 22}), \
         patch.object(vault, "_judgeme_shop_domain", return_value="fixture.myshopify.com"):
        receipt = vault._submit_judgeme_review(
            {"shopify_product_id": "gid://shopify/Product/55"},
            {"rating": 4, "review_title": "My print", "review_body": "Looks great on the wall."},
            name="Fixture Collector", email="collector@example.test",
            photo_upload={"url": "https://fixture.test/photo.jpg"}, request_post=post)
    return receipt, captured


def test_correct_product_customer_photo_and_rating_reach_judgeme():
    receipt, sent = deliver(200, {"review": {"id": 88, "verified": False}})
    assert sent["url"].endswith("/api/v1/reviews")
    payload = sent["json"]
    assert payload["id"] == "55"
    assert payload["name"] == "Fixture Collector" and payload["email"] == "collector@example.test"
    assert payload["rating"] == 4 and payload["title"] == "My print"
    assert payload["picture_urls"] == ["https://fixture.test/photo.jpg"]
    assert "verified" not in payload and "youtube_url" not in payload
    assert receipt["review_id"] == "88" and receipt["verification_status"] == "unverified"


@pytest.mark.parametrize("body", [{"error": "disabled"}, {"errors": ["rejected"]}, {"success": False}, ["invalid"]])
def test_provider_error_body_never_becomes_success_even_with_http_200(body):
    with pytest.raises(vault.CollectorVaultUnavailableError):
        deliver(200, body)


def test_documented_background_acceptance_does_not_require_immediate_review_id():
    receipt, _ = deliver(200, content=b"")
    assert receipt["review_id"] == ""
    assert receipt["verification_status"] != "verified"


@pytest.mark.parametrize("status", [302, 422, 503])
def test_non_success_http_response_is_not_reported_as_submitted(status):
    with pytest.raises(vault.CollectorVaultUnavailableError):
        deliver(status, {})
