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
def test_cached_account_photo_types_remain_supported(kind):
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


def test_cached_account_submit_uses_native_os_with_media():
    from unittest.mock import Mock
    photo=photo_payload('WEBP')
    store,shop=Mock(),Mock()
    with patch('reviews_store.ReviewsStore',return_value=store),patch('crm_shopify.Shopify',return_value=shop),patch('reviews_account.submit',return_value={'status':'submitted'}) as submit:
        assert vault.submit_review('owner',review_reference='signed',rating=5,body='A native account review',photo=photo)['status']=='submitted'
    args=submit.call_args.args
    assert args[:4]==(store,shop,'owner','signed')
    assert args[4]['rating']==5 and args[5][0]['kind']=='image'
    assert args[5][0]['data']
