"""Small, server-owned contracts for Sports Cave Marketplace."""
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import base64
import io
import json
from pathlib import Path
import re
import warnings
from uuid import UUID

ROOT = Path(__file__).resolve().parent
SITE_PATH = 'static/marketplace/site.json'
BASE_PATH = '/marketplace'
PUBLIC_ORIGIN = 'https://sports-cave-image-factory.onrender.com'
SHOP_URL = 'https://www.sportscaveshop.com'
CATEGORIES = {'memorabilia': 'Memorabilia', 'jerseys': 'Jerseys', 'cards': 'Trading cards'}
CONDITIONS = ('New / unused', 'Excellent', 'Good', 'Fair')
SPORTS = ('NRL', 'AFL', 'Cricket', 'Basketball', 'Football', 'Motorsport', 'Other sports')
PUBLIC_FIELDS = ('id', 'title', 'category', 'sport', 'team', 'condition', 'description',
                 'price_cents', 'shipping_cents', 'location', 'seller_name', 'seller_type',
                 'provenance', 'photo_count', 'has_video', 'video_seconds', 'published_at', 'status')
DEFAULT_SITE = {'release_id': 'marketplace-launch-1', 'headline': 'Great collections keep moving.',
                'description': 'Buy and sell sporting memorabilia, jerseys and trading cards.',
                'intake_open': True}


def now():
    return datetime.now(timezone.utc).isoformat()


def site_config(value):
    if not isinstance(value, dict):
        raise ValueError('Website settings must be an object.')
    result = {}
    for field, limit in (('headline', 80), ('description', 160)):
        result[field] = clean_text(value.get(field), field.replace('_', ' '), limit)
    if not isinstance(value.get('intake_open'), bool):
        raise ValueError('Choose whether seller submissions are open.')
    result['intake_open'] = value['intake_open']
    result['release_id'] = str(value.get('release_id', ''))[:80]
    return result


def deployed_site():
    path = ROOT / SITE_PATH
    return site_config(json.loads(path.read_text(encoding='utf-8'))) if path.exists() else deepcopy(DEFAULT_SITE)


def clean_text(value, label, limit, *, required=True):
    if not isinstance(value, str):
        raise ValueError(f'Enter {label}.')
    value = value.strip()
    if (required and not value) or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'Enter {label} using up to {limit} characters.')
    return value


def email(value):
    value = clean_text(value, 'your email', 254).lower()
    if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ValueError('Enter a valid email address.')
    return value


def cents(value, *, shipping=False):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount != amount.quantize(Decimal('.01')):
            raise ValueError
        if not (Decimal('0') if shipping else Decimal('10')) <= amount <= (Decimal('1000') if shipping else Decimal('50000')):
            raise ValueError
        return int(amount * 100)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError('Use postage from A$0–1,000.' if shipping else 'Use an asking price from A$10–50,000 with up to two decimal places.') from None


def money(value):
    return 'A$' + f'{int(value) / 100:,.2f}'.removesuffix('.00')


def fee_quote(price_cents):
    fee = int((Decimal(price_cents) * Decimal('.05')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return {'fee_cents': fee, 'payout_cents': price_cents - fee}


def identifier(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Item not found.') from None


def submission(payload):
    if not isinstance(payload, dict):
        raise ValueError('Check your submission.')
    row = {}
    for field, limit in (('title', 110), ('description', 1800), ('seller_name', 70), ('location', 80),
                         ('team', 80), ('provenance', 800)):
        row[field] = clean_text(payload.get(field, ''), field.replace('_', ' '), limit,
                                required=field not in ('team', 'provenance'))
    for field, choices in (('category', CATEGORIES), ('condition', CONDITIONS), ('sport', SPORTS),
                            ('seller_type', ('Private collector', 'Business seller'))):
        if payload.get(field) not in choices:
            raise ValueError('Choose ' + field.replace('_', ' ') + '.')
        row[field] = payload[field]
    row['seller_email'] = email(payload.get('seller_email'))
    row['price_cents'] = cents(payload.get('price'))
    row['shipping_cents'] = cents(payload.get('shipping'), shipping=True)
    if payload.get('consent') is not True:
        raise ValueError('Confirm you own the item and agree to the submission terms.')
    row['consent_version'] = 'recorded-media-2026-11-22'
    row['consented_at'] = now()
    return row


def prepare_photos(values):
    """Decode actual photographs, strip metadata and bound stored dimensions/bytes."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not isinstance(values, list) or not 2 <= len(values) <= 4:
        raise ValueError('Add 2–4 photographs of the actual item, including any flaws.')
    result = []
    for value in values:
        try:
            if not isinstance(value, str) or len(value) > 2800000:
                raise ValueError
            raw = base64.b64decode(value, validate=True)
            if len(raw) > 2000000:
                raise ValueError
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(io.BytesIO(raw)) as original:
                    if original.format not in ('JPEG', 'PNG', 'WEBP') or original.width * original.height > 24000000:
                        raise ValueError
                    image = ImageOps.exif_transpose(original)
                    image.thumbnail((1400, 1400))
                    if min(image.size) < 250:
                        raise ValueError
                    image = image.convert('RGB')
                    output = io.BytesIO()
                    image.save(output, format='WEBP', quality=80, method=3)
                    if output.tell() > 450000:
                        output = io.BytesIO()
                        image.save(output, format='WEBP', quality=60, method=3)
                    if output.tell() > 450000:
                        raise ValueError
                    result.append(base64.b64encode(output.getvalue()).decode('ascii'))
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise ValueError('Use clear JPG, PNG or WebP photographs, at least 250px and up to 2 MB each.') from None
    return result


def public_listing(row):
    return {key: deepcopy(row[key]) for key in PUBLIC_FIELDS if key in row}


def listing_url(row):
    return BASE_PATH + '/item/' + identifier(row['id'])
