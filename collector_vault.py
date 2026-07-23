import base64
import hashlib
import hmac
import html
import io
import json
import logging
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError

import shopify_sync
import supabase_backend
from services import r2_storage


API_BASE_PATH = "/api/collector-vault"
FRAME_PRODUCT_HANDLE = "framed-collector-certificate"
FRAME_PRODUCT_SKU = "SC-FCC-A4-BLK"
FRAME_PRODUCT_DEFAULT_COUNTRY = "AU"
SESSION_TOKEN_LEEWAY_SECONDS = 30
ASSET_TOKEN_TTL_SECONDS = 30 * 60
CERTIFICATE_REFERENCE_TTL_SECONDS = 60 * 60
REVIEW_REFERENCE_TTL_SECONDS = 60 * 60
REVIEW_PHOTO_MAX_BYTES = 6 * 1024 * 1024
REVIEW_BODY_MIN_LENGTH = 10
REVIEW_BODY_MAX_LENGTH = 2000
REVIEW_TITLE_MAX_LENGTH = 120
REVIEW_PHOTO_MAX_PIXELS = 40_000_000
DELIVERY_CACHE_TTL_SECONDS = 5 * 60
FRAME_PRODUCT_CACHE_TTL_SECONDS = 5 * 60
JUDGEME_PRODUCT_CACHE_TTL_SECONDS = 15 * 60
SAFE_REVIEW_MIME_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}
COLLECTOR_EVENTS = {
    "collection_viewed",
    "certificate_opened",
    "certificate_downloaded",
    "certificate_printed",
    "frame_offer_viewed",
    "frame_offer_clicked",
    "frame_checkout_created",
    "frame_order_completed",
    "review_prompt_viewed",
    "review_started",
    "review_photo_added",
    "review_submitted",
    "review_submission_failed",
}
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,120}$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_CACHE_LOCK = threading.RLock()
_DELIVERY_CACHE = {}
_FRAME_PRODUCT_CACHE = {}
_JUDGEME_PRODUCT_CACHE = {}
LOGGER = logging.getLogger(__name__)


class CollectorVaultError(RuntimeError):
    status_code = 400
    public_message = "The request could not be completed."
    error_code = "request_failed"

    def __init__(self, message="", *, error_code=None):
        super().__init__(message)
        if error_code:
            self.error_code = str(error_code)


class CollectorVaultAuthenticationError(CollectorVaultError):
    status_code = 401
    public_message = "Your customer session has expired. Please refresh and sign in again."
    error_code = "customer_authentication_failed"


class CollectorVaultAuthorizationError(CollectorVaultError):
    status_code = 403
    public_message = "That item is not available in this collection."
    error_code = "customer_authorization_failed"


class CollectorVaultNotFoundError(CollectorVaultError):
    status_code = 404
    public_message = "That item could not be found."
    error_code = "record_not_found"


class CollectorVaultConflictError(CollectorVaultError):
    status_code = 409
    error_code = "request_conflict"


class CollectorVaultUnavailableError(CollectorVaultError):
    status_code = 503
    public_message = "This service is temporarily unavailable. Please try again."
    error_code = "service_unavailable"


class CollectorVaultDataError(CollectorVaultError):
    status_code = 503
    public_message = "Your collection could not be loaded. Please try again."
    error_code = "collection_data_unavailable"


def _b64url_decode(value):
    text = str(value or "").strip()
    padding = "=" * (-len(text) % 4)
    try:
        return base64.urlsafe_b64decode((text + padding).encode("ascii"))
    except Exception as error:
        raise CollectorVaultAuthenticationError("Malformed signed token.") from error


def _b64url_encode(value):
    return base64.urlsafe_b64encode(bytes(value)).rstrip(b"=").decode("ascii")


def _json_segment(value):
    return _b64url_encode(
        json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )


def _clean_shop_domain(value):
    raw = str(value or "").strip().lower()
    if raw.startswith(("https://", "http://")):
        raw = urlparse(raw).hostname or ""
    return raw.rstrip("/")


def _app_client_id():
    configured = str(
        os.getenv("SHOPIFY_CLIENT_ID")
        or os.getenv("SHOPIFY_API_KEY")
        or os.getenv("SPORTS_CAVE_SHOPIFY_CLIENT_ID")
        or ""
    ).strip()
    if configured:
        return configured
    app_config = Path(__file__).resolve().parent / "shopify_customer_account" / "shopify.app.toml"
    try:
        for line in app_config.read_text(encoding="utf-8").splitlines():
            match = re.match(r'^\s*client_id\s*=\s*"([^"]+)"', line)
            if match:
                return match.group(1).strip()
    except OSError:
        pass
    return ""


def _session_token_secrets():
    values = []
    for name in (
        "SHOPIFY_API_SECRET_KEY",
        "SHOPIFY_API_SECRET",
        "SHOPIFY_CLIENT_SECRET",
        "SHOPIFY_SHARED_SECRET",
        "SHOPIFY_WEBHOOK_SECRET",
    ):
        value = str(os.getenv(name) or "").strip()
        if value and not value.startswith(("shpat_", "shpca_", "shppa_")):
            values.append(value)
    return list(dict.fromkeys(values))


def _asset_signing_secret():
    configured = str(os.getenv("COLLECTOR_VAULT_ASSET_SIGNING_SECRET") or "").strip()
    if configured:
        return configured
    raise CollectorVaultUnavailableError(
        "Collector Vault signing is not configured.",
        error_code="asset_signing_not_configured",
    )


def _asset_signing_configured():
    return bool(
        str(
            os.getenv("COLLECTOR_VAULT_ASSET_SIGNING_SECRET")
            or ""
        ).strip()
    )


def verify_shopify_session_token(token, *, now=None, secret_candidates=None, audience=None, shop_domain=None):
    parts = str(token or "").strip().split(".")
    if len(parts) != 3:
        raise CollectorVaultAuthenticationError("Shopify session token is missing or malformed.")
    header_segment, payload_segment, signature_segment = parts
    try:
        header = json.loads(_b64url_decode(header_segment).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_segment).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CollectorVaultAuthenticationError("Shopify session token is malformed.") from error
    if header.get("alg") != "HS256":
        raise CollectorVaultAuthenticationError("Unsupported Shopify session token algorithm.")

    signing_input = f"{header_segment}.{payload_segment}".encode("ascii")
    received_signature = _b64url_decode(signature_segment)
    candidates = list(secret_candidates if secret_candidates is not None else _session_token_secrets())
    if not candidates:
        raise CollectorVaultUnavailableError(
            "Shopify app authentication is not configured.",
            error_code="shopify_session_secret_not_configured",
        )
    if not any(
        hmac.compare_digest(
            hmac.new(str(candidate).encode("utf-8"), signing_input, hashlib.sha256).digest(),
            received_signature,
        )
        for candidate in candidates
    ):
        raise CollectorVaultAuthenticationError("Shopify session token signature is invalid.")

    now_value = int(time.time() if now is None else now)
    try:
        expires_at = int(payload.get("exp") or 0)
        issued_at = int(payload.get("iat") or 0)
        not_before = int(payload.get("nbf") or issued_at or 0)
    except (TypeError, ValueError) as error:
        raise CollectorVaultAuthenticationError("Shopify session token timing is invalid.") from error
    if expires_at <= now_value - SESSION_TOKEN_LEEWAY_SECONDS:
        raise CollectorVaultAuthenticationError("Shopify session token has expired.")
    if issued_at and issued_at > now_value + SESSION_TOKEN_LEEWAY_SECONDS:
        raise CollectorVaultAuthenticationError("Shopify session token was issued in the future.")
    if not_before and not_before > now_value + SESSION_TOKEN_LEEWAY_SECONDS:
        raise CollectorVaultAuthenticationError("Shopify session token is not active yet.")

    expected_audience = str(audience or _app_client_id()).strip()
    token_audience = payload.get("aud")
    token_audiences = token_audience if isinstance(token_audience, list) else [token_audience]
    if not expected_audience or expected_audience not in {str(value or "") for value in token_audiences}:
        raise CollectorVaultAuthenticationError("Shopify session token audience is invalid.")

    expected_shop = _clean_shop_domain(
        shop_domain or (shopify_sync.get_config().get("store_domain") if shopify_sync else "")
    )
    token_shop = _clean_shop_domain(payload.get("dest"))
    if not expected_shop or token_shop != expected_shop:
        raise CollectorVaultAuthenticationError("Shopify session token shop is invalid.")

    customer_id = str(payload.get("sub") or "").strip()
    if not re.match(r"^gid://shopify/Customer/\d+$", customer_id):
        raise CollectorVaultAuthenticationError("A signed-in Shopify customer is required.")
    return {
        "shopify_customer_id": customer_id,
        "shop_domain": token_shop,
        "claims": payload,
    }


def _signed_token(payload, *, ttl_seconds):
    now_value = int(time.time())
    body = dict(payload or {})
    body.update({"iat": now_value, "exp": now_value + max(int(ttl_seconds), 60)})
    segment = _json_segment(body)
    signature = hmac.new(
        _asset_signing_secret().encode("utf-8"),
        segment.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{segment}.{_b64url_encode(signature)}"


def _verify_signed_token(token, *, expected_purpose):
    parts = str(token or "").strip().split(".")
    if len(parts) != 2:
        raise CollectorVaultAuthenticationError("Signed reference is malformed.")
    segment, signature_segment = parts
    expected_signature = hmac.new(
        _asset_signing_secret().encode("utf-8"),
        segment.encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected_signature, _b64url_decode(signature_segment)):
        raise CollectorVaultAuthenticationError("Signed reference is invalid.")
    try:
        payload = json.loads(_b64url_decode(segment).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CollectorVaultAuthenticationError("Signed reference is malformed.") from error
    if payload.get("purpose") != expected_purpose:
        raise CollectorVaultAuthenticationError("Signed reference cannot be used for this action.")
    if int(payload.get("exp") or 0) <= int(time.time()):
        raise CollectorVaultAuthenticationError("Signed reference has expired.")
    return payload


def _customer_numeric_id(customer_id):
    return str(customer_id or "").strip().rsplit("/", 1)[-1]


def customer_id_candidates(customer_id):
    raw = str(customer_id or "").strip()
    numeric = _customer_numeric_id(raw)
    values = [raw]
    if numeric.isdigit():
        values.extend([numeric, f"gid://shopify/Customer/{numeric}"])
    return list(dict.fromkeys(value for value in values if value))


def _canonical_gid(resource_type, value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    numeric = raw.rsplit("/", 1)[-1]
    return f"gid://shopify/{resource_type}/{numeric}" if numeric.isdigit() else raw


def customer_hash(customer_id):
    salt = _asset_signing_secret().encode("utf-8")
    return hmac.new(salt, str(customer_id or "").encode("utf-8"), hashlib.sha256).hexdigest()


def _require_database():
    if not supabase_backend.is_configured():
        raise CollectorVaultUnavailableError(
            "Supabase is not configured.",
            error_code="database_not_configured",
        )


def _database_error_sqlstate(error):
    return str(
        getattr(error, "sqlstate", "")
        or getattr(error, "pgcode", "")
        or ""
    ).strip()


def _int_value(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _log_optional_feature_unavailable(feature, error):
    LOGGER.warning(
        "Collector Vault optional feature unavailable feature=%s error_type=%s sqlstate=%s",
        feature,
        type(error).__name__,
        _database_error_sqlstate(error) or "unknown",
    )


def _row_customer_id(row):
    return str(
        row.get("order_customer_id")
        or row.get("certificate_customer_id")
        or row.get("edition_customer_id")
        or ""
    ).strip()


def _asset_reference(row, kind):
    if kind == "preview":
        bucket = str(row.get("certificate_preview_r2_bucket") or "").strip()
        key = str(row.get("certificate_preview_r2_key") or "").strip()
        url = str(row.get("certificate_preview_image_url") or "").strip()
        mime_type = "image/webp" if url.lower().endswith(".webp") else "image/png"
    elif kind == "print":
        bucket = ""
        key = ""
        url = str(row.get("certificate_print_jpg_url") or "").strip()
        mime_type = "image/jpeg"
    else:
        bucket = str(row.get("certificate_r2_bucket") or "").strip()
        key = str(row.get("certificate_r2_key") or "").strip()
        url = str(
            row.get("certificate_pdf_url")
            or row.get("certificate_file_url")
            or row.get("shopify_file_url")
            or ""
        ).strip()
        mime_type = "application/pdf"
    if bucket and key:
        return {"storage": "r2", "bucket": bucket, "key": key, "mime_type": mime_type}
    parsed = urlparse(url)
    if parsed.scheme == "https" and parsed.hostname:
        return {"storage": "https", "url": url, "mime_type": mime_type}
    return {}


def _certificate_filename(row, kind):
    title = _CONTROL_CHARACTERS.sub(
        "",
        str(row.get("product_title") or "certificate"),
    )
    title = re.sub(r'[<>:"/\\|?*]+', "", title).strip(" .")
    title = re.sub(r"\s+", " ", title)[:90] or "certificate"
    edition = int(row.get("edition_number") or 0)
    suffix = "print.jpg" if kind == "print" else ("preview.png" if kind == "preview" else "certificate.pdf")
    return f"{title} - Edition {edition:03d} - {suffix}"


def _certificate_public_row(row, *, include_secure_assets=True):
    record_id = int(row.get("certificate_row_id") or 0)
    if record_id <= 0:
        raise ValueError("Certificate row ID is invalid.")
    owner_hash = ""
    metadata_identity = (
        f"{_row_customer_id(row)}:{record_id}".encode("utf-8")
    )
    certificate_ref = (
        f"metadata-{hashlib.sha256(metadata_identity).hexdigest()[:32]}"
    )
    assets = {}
    if include_secure_assets:
        owner_hash = customer_hash(_row_customer_id(row))
        certificate_ref = _signed_token(
            {
                "purpose": "certificate",
                "certificate_row_id": record_id,
                "customer_hash": owner_hash,
            },
            ttl_seconds=CERTIFICATE_REFERENCE_TTL_SECONDS,
        )
        for kind in ("preview", "pdf", "print"):
            if not _asset_reference(row, kind):
                continue
            token = _signed_token(
                {
                    "purpose": "asset",
                    "certificate_row_id": record_id,
                    "customer_hash": owner_hash,
                    "kind": kind,
                },
                ttl_seconds=ASSET_TOKEN_TTL_SECONDS,
            )
            assets[kind] = f"{API_BASE_PATH}/asset?token={token}"
    return {
        "reference": certificate_ref,
        "product_title": str(row.get("product_title") or "Sports Cave limited edition").strip(),
        "product_handle": str(row.get("product_handle") or row.get("shopify_handle") or "").strip(),
        "shopify_product_id": _canonical_gid("Product", row.get("shopify_product_id")),
        "shopify_variant_id": _canonical_gid("ProductVariant", row.get("shopify_variant_id")),
        "variant_title": str(row.get("variant_title") or "").strip(),
        "edition_number": int(row.get("edition_number") or 0),
        "edition_limit": int(row.get("edition_limit") or row.get("edition_total") or 100),
        "certificate_id": str(row.get("certificate_id") or "").strip(),
        "order_name": str(row.get("shopify_order_name") or "").strip(),
        "purchase_date": _iso_value(row.get("purchase_date") or row.get("processed_at")),
        "preview_url": assets.get("preview"),
        "pdf_url": assets.get("pdf"),
        "print_url": assets.get("print"),
        "frame_status": str(row.get("frame_status") or "").strip(),
        "frame_request_reference": str(row.get("frame_request_reference") or "").strip(),
    }


def _iso_value(value):
    if not value:
        return ""
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _latest_frame_request_state(rows, owner_hash):
    certificate_row_ids = sorted(
        {
            _int_value(row.get("certificate_row_id"))
            for row in rows
            if _int_value(row.get("certificate_row_id")) > 0
        }
    )
    if not certificate_row_ids:
        return {}, True
    try:
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT ON (certificate_row_id)
                           certificate_row_id, status, request_reference
                    FROM collector_frame_requests
                    WHERE customer_hash=%s
                      AND certificate_row_id = ANY(%s)
                    ORDER BY certificate_row_id, created_at DESC
                    """,
                    (owner_hash, certificate_row_ids),
                )
                frame_rows = cur.fetchall() or []
    except Exception as error:
        _log_optional_feature_unavailable("frame_requests", error)
        return {}, False
    return {
        _int_value(row.get("certificate_row_id")): dict(row)
        for row in frame_rows
        if _int_value(row.get("certificate_row_id")) > 0
    }, True


def _list_owned_certificates_with_capabilities(shopify_customer_id):
    _require_database()
    candidates = customer_id_candidates(shopify_customer_id)
    try:
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.id AS certificate_row_id,
                        c.shopify_customer_id AS certificate_customer_id,
                        eo.shopify_customer_id AS edition_customer_id,
                        o.customer_id AS order_customer_id,
                        c.shopify_order_id,
                        COALESCE(NULLIF(c.shopify_order_name, ''), NULLIF(o.order_name, '')) AS shopify_order_name,
                        c.shopify_line_item_id,
                        COALESCE(NULLIF(c.shopify_product_id, ''), NULLIF(eo.shopify_product_id, ''), NULLIF(li.shopify_product_id, '')) AS shopify_product_id,
                        COALESCE(NULLIF(c.shopify_variant_id, ''), NULLIF(eo.shopify_variant_id, ''), NULLIF(li.raw_json->>'shopify_variant_id', '')) AS shopify_variant_id,
                        COALESCE(NULLIF(c.product_handle, ''), NULLIF(c.shopify_handle, ''), NULLIF(eo.product_handle, ''), NULLIF(eo.shopify_handle, ''), NULLIF(li.shopify_handle, '')) AS product_handle,
                        COALESCE(NULLIF(c.product_title, ''), NULLIF(eo.product_title, ''), NULLIF(li.product_title, '')) AS product_title,
                        COALESCE(NULLIF(c.variant_title, ''), NULLIF(eo.variant_title, ''), NULLIF(li.variant_title, '')) AS variant_title,
                        c.certificate_id, c.edition_number,
                        COALESCE(c.edition_limit, c.edition_total, eo.edition_total, 100) AS edition_limit,
                        c.purchase_date, o.processed_at,
                        c.certificate_pdf_url, c.certificate_file_url, c.shopify_file_url,
                        c.certificate_print_jpg_url, c.certificate_preview_image_url,
                        c.certificate_r2_bucket, c.certificate_r2_key,
                        c.certificate_preview_r2_bucket, c.certificate_preview_r2_key,
                        o.customer_name, o.customer_email
                    FROM certificates c
                    JOIN shopify_orders o
                      ON regexp_replace(COALESCE(o.shopify_order_id, ''), '^.*/', '')
                       = regexp_replace(COALESCE(c.shopify_order_id, ''), '^.*/', '')
                    LEFT JOIN edition_orders eo
                      ON COALESCE(c.related_edition_order_id::text, c.edition_order_id::text) = eo.id::text
                    LEFT JOIN shopify_order_lines li
                      ON li.shopify_line_item_id = c.shopify_line_item_id
                    WHERE o.customer_id = ANY(%s)
                      AND (COALESCE(c.shopify_customer_id, '') = '' OR c.shopify_customer_id = ANY(%s))
                      AND (COALESCE(eo.shopify_customer_id, '') = '' OR eo.shopify_customer_id = ANY(%s))
                      AND COALESCE(c.certificate_status, c.status, '') NOT IN ('Deleted', 'Cancelled')
                    ORDER BY COALESCE(c.purchase_date, o.processed_at, c.created_at) DESC NULLS LAST,
                             c.id DESC
                    """,
                    (candidates, candidates, candidates),
                )
                rows = [dict(row) for row in (cur.fetchall() or [])]
    except CollectorVaultError:
        raise
    except Exception as error:
        LOGGER.error(
            "Collector Vault certificate read failed error_type=%s sqlstate=%s",
            type(error).__name__,
            _database_error_sqlstate(error) or "unknown",
            exc_info=True,
        )
        raise CollectorVaultDataError("Certificate ownership query failed.") from error

    secure_assets_available = _asset_signing_configured()
    if secure_assets_available:
        frame_state, frame_requests_available = _latest_frame_request_state(
            rows,
            customer_hash(shopify_customer_id),
        )
    else:
        frame_state, frame_requests_available = {}, False
    for row in rows:
        state = frame_state.get(_int_value(row.get("certificate_row_id")), {})
        row["frame_status"] = str(state.get("status") or "")
        row["frame_request_reference"] = str(
            state.get("request_reference") or ""
        )
    return rows, {
        "frame_requests": frame_requests_available,
        "secure_assets": secure_assets_available,
    }


def list_owned_certificates(shopify_customer_id):
    rows, _capabilities = _list_owned_certificates_with_capabilities(
        shopify_customer_id
    )
    return rows


def _resolve_certificate_reference(reference, shopify_customer_id):
    payload = _verify_signed_token(reference, expected_purpose="certificate")
    expected_hash = customer_hash(shopify_customer_id)
    if not hmac.compare_digest(str(payload.get("customer_hash") or ""), expected_hash):
        raise CollectorVaultAuthorizationError("Certificate reference belongs to another customer.")
    certificate_row_id = int(payload.get("certificate_row_id") or 0)
    for row in list_owned_certificates(shopify_customer_id):
        if int(row.get("certificate_row_id") or 0) == certificate_row_id:
            return row
    raise CollectorVaultNotFoundError("Certificate is not owned by this customer.")


def resolve_asset_token(token):
    payload = _verify_signed_token(token, expected_purpose="asset")
    certificate_row_id = int(payload.get("certificate_row_id") or 0)
    kind = str(payload.get("kind") or "").strip()
    if kind not in {"preview", "pdf", "print"}:
        raise CollectorVaultAuthenticationError("Asset type is invalid.")
    _require_database()
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id AS certificate_row_id, c.*, o.customer_id AS order_customer_id,
                       c.shopify_customer_id AS certificate_customer_id
                FROM certificates c
                JOIN shopify_orders o
                  ON regexp_replace(COALESCE(o.shopify_order_id, ''), '^.*/', '')
                   = regexp_replace(COALESCE(c.shopify_order_id, ''), '^.*/', '')
                WHERE c.id=%s
                LIMIT 1
                """,
                (certificate_row_id,),
            )
            row = cur.fetchone() or {}
    if not row:
        raise CollectorVaultNotFoundError("Certificate asset was not found.")
    actual_hash = customer_hash(_row_customer_id(row))
    if not hmac.compare_digest(str(payload.get("customer_hash") or ""), actual_hash):
        raise CollectorVaultAuthorizationError("Certificate asset ownership does not match.")
    asset = _asset_reference(row, kind)
    if not asset:
        raise CollectorVaultNotFoundError("Certificate asset is not ready.")
    asset.update(
        {
            "filename": _certificate_filename(row, kind),
            "kind": kind,
            "certificate_row_id": certificate_row_id,
        }
    )
    return asset


FRAME_PRODUCT_BY_ID_QUERY = """
query CollectorVaultFrameProductById($id: ID!, $country: CountryCode!) {
  product(id: $id) {
    id
    title
    handle
    status
    onlineStoreUrl
    tracksInventory
    variants(first: 20) {
      nodes {
        id
        sku
        availableForSale
        inventoryItem { tracked }
        contextualPricing(context: {country: $country}) {
          price { amount currencyCode }
        }
      }
    }
  }
}
"""

FRAME_PRODUCT_BY_HANDLE_QUERY = """
query CollectorVaultFrameProductByHandle($query: String!, $country: CountryCode!) {
  products(first: 2, query: $query) {
    nodes {
      id
      title
      handle
      status
      onlineStoreUrl
      tracksInventory
      variants(first: 20) {
        nodes {
          id
          sku
          availableForSale
          inventoryItem { tracked }
          contextualPricing(context: {country: $country}) {
            price { amount currencyCode }
          }
        }
      }
    }
  }
}
"""


def _frame_product_handle():
    return str(os.getenv("FRAMED_CERTIFICATE_PRODUCT_HANDLE") or FRAME_PRODUCT_HANDLE).strip()


def _configured_frame_product_id():
    return _canonical_gid("Product", os.getenv("FRAMED_CERTIFICATE_PRODUCT_ID") or "")


def _configured_frame_variant_id():
    return _canonical_gid("ProductVariant", os.getenv("FRAMED_CERTIFICATE_VARIANT_ID") or "")


def _frame_product_country():
    country = str(
        os.getenv("COLLECTOR_VAULT_DEFAULT_COUNTRY")
        or FRAME_PRODUCT_DEFAULT_COUNTRY
    ).strip().upper()
    return country if re.match(r"^[A-Z]{2}$", country) else FRAME_PRODUCT_DEFAULT_COUNTRY


def _frame_product_environment_ready():
    return bool(
        _configured_frame_product_id()
        and _configured_frame_variant_id()
        and _frame_product_handle()
    )


def _frame_product_from_response(data, configured_product_id):
    if configured_product_id:
        return dict(data.get("product") or {})
    matches = [
        product
        for product in ((data.get("products") or {}).get("nodes") or [])
        if str(product.get("handle") or "") == _frame_product_handle()
    ]
    return dict(matches[0]) if len(matches) == 1 else {}


def _frame_product_state(product, configured_product_id, configured_variant_id):
    if not _frame_product_environment_ready():
        return "framed_product_not_configured"
    if not product:
        return "framed_product_not_found"
    product_id = _canonical_gid("Product", product.get("id"))
    if configured_product_id and product_id != configured_product_id:
        return "framed_product_not_found"
    if (
        not configured_product_id
        and str(product.get("handle") or "") != _frame_product_handle()
    ):
        return "framed_product_not_found"
    status = str(product.get("status") or "").strip().upper()
    if status == "DRAFT":
        return "framed_product_draft"
    if status != "ACTIVE":
        return "framed_product_unavailable"
    if not str(product.get("onlineStoreUrl") or "").strip():
        return "framed_product_not_published"
    variants = (product.get("variants") or {}).get("nodes") or []
    selected = next(
        (
            variant
            for variant in variants
            if _canonical_gid("ProductVariant", variant.get("id"))
            == configured_variant_id
        ),
        {},
    )
    if not selected:
        return "framed_variant_unavailable"
    price = (selected.get("contextualPricing") or {}).get("price") or {}
    if (
        str(selected.get("sku") or "").strip() != FRAME_PRODUCT_SKU
        or not selected.get("availableForSale")
        or not str(price.get("amount") or "").strip()
        or not str(price.get("currencyCode") or "").strip()
    ):
        return "framed_variant_unavailable"
    return "ready_for_purchase"


def get_frame_product(*, force=False):
    handle = _frame_product_handle()
    configured_product = _configured_frame_product_id()
    configured_variant = _configured_frame_variant_id()
    cache_key = (
        configured_product,
        handle,
        configured_variant,
        _frame_product_country(),
    )
    now_value = time.time()
    with _CACHE_LOCK:
        cached = _FRAME_PRODUCT_CACHE.get(cache_key)
        if not force and cached and cached["expires_at"] > now_value:
            return dict(cached["value"])
    if not handle or not configured_variant:
        value = {
            "state": "framed_product_not_configured",
            "available": False,
        }
        with _CACHE_LOCK:
            _FRAME_PRODUCT_CACHE[cache_key] = {
                "value": dict(value),
                "expires_at": now_value + FRAME_PRODUCT_CACHE_TTL_SECONDS,
            }
        return value
    try:
        if configured_product:
            query = FRAME_PRODUCT_BY_ID_QUERY
            variables = {
                "id": configured_product,
                "country": _frame_product_country(),
            }
        else:
            query = FRAME_PRODUCT_BY_HANDLE_QUERY
            variables = {
                "query": f"handle:{handle}",
                "country": _frame_product_country(),
            }
        data, _served_version = shopify_sync.graphql_request(
            query,
            variables=variables,
        )
    except Exception as error:
        LOGGER.warning(
            "Collector Vault framed product lookup failed error_type=%s",
            type(error).__name__,
        )
        value = {
            "state": "shopify_unavailable",
            "available": False,
        }
    else:
        product = _frame_product_from_response(data, configured_product)
        state = _frame_product_state(
            product,
            configured_product,
            configured_variant,
        )
        variants = (product.get("variants") or {}).get("nodes") or []
        selected_variant = next(
            (
                variant
                for variant in variants
                if _canonical_gid("ProductVariant", variant.get("id"))
                == configured_variant
            ),
            {},
        )
        contextual_price = (
            (selected_variant.get("contextualPricing") or {}).get("price") or {}
        )
        value = {
            "state": state,
            "product_id": _canonical_gid("Product", product.get("id")),
            "handle": str(product.get("handle") or ""),
            "variant_id": _canonical_gid(
                "ProductVariant",
                selected_variant.get("id"),
            ),
            "sku": str(selected_variant.get("sku") or ""),
            "status": str(product.get("status") or "").strip().upper(),
            "published": bool(str(product.get("onlineStoreUrl") or "").strip()),
            "variant_available": bool(selected_variant.get("availableForSale")),
            "inventory_tracked": bool(
                (selected_variant.get("inventoryItem") or {}).get("tracked")
            ),
            "contextual_price": {
                "amount": str(contextual_price.get("amount") or ""),
                "currency_code": str(
                    contextual_price.get("currencyCode") or ""
                ).upper(),
            },
            "available": state == "ready_for_purchase",
        }
    with _CACHE_LOCK:
        _FRAME_PRODUCT_CACHE[cache_key] = {
            "value": dict(value),
            "expires_at": now_value + FRAME_PRODUCT_CACHE_TTL_SECONDS,
        }
    return value


def collector_vault_readiness(*, check_shopify=False, force=False):
    judge_private = bool(
        str(os.getenv("JUDGEME_PRIVATE_API_TOKEN") or "").strip()
    )
    judge_public = bool(
        str(os.getenv("JUDGEME_PUBLIC_API_TOKEN") or "").strip()
    )
    judge_domain = bool(_judgeme_shop_domain())
    signing_ready = _asset_signing_configured()
    session_auth_ready = bool(_session_token_secrets()) and bool(_app_client_id())
    database_ready = supabase_backend.is_configured()
    frame_configured = _frame_product_environment_ready()
    frame_product = (
        get_frame_product(force=force)
        if check_shopify and frame_configured
        else {}
    )
    frame_state = (
        frame_product.get("state")
        if frame_product
        else (
            "framed_product_configured"
            if frame_configured
            else "framed_product_not_configured"
        )
    )
    judge_configured = judge_private and judge_public and judge_domain
    return {
        "judge_me_state": (
            "judge_me_configured"
            if judge_configured
            else "judge_me_not_configured"
        ),
        "framed_product_state": frame_state,
        "signing_state": (
            "signing_secret_configured"
            if signing_ready
            else "signing_secret_missing"
        ),
        "session_auth_state": (
            "shopify_session_auth_configured"
            if session_auth_ready
            else "shopify_session_auth_not_configured"
        ),
        "database_state": (
            "collector_vault_database_configured"
            if database_ready
            else "collector_vault_database_not_configured"
        ),
        "backend_state": (
            "collector_vault_backend_ready"
            if session_auth_ready and database_ready
            else "collector_vault_backend_not_ready"
        ),
    }


def log_collector_vault_readiness(*, check_shopify=True, force=False):
    readiness = collector_vault_readiness(
        check_shopify=check_shopify,
        force=force,
    )
    print(
        json.dumps(
            {
                "event": "collector_vault_readiness",
                **readiness,
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
    return readiness


DELIVERY_QUERY = """
query CollectorVaultOrderDelivery($ids: [ID!]!) {
  nodes(ids: $ids) {
    ... on Order {
      id
      displayFulfillmentStatus
      customer { id }
      fulfillments {
        id
        status
        events(first: 20, reverse: true) {
          nodes { status happenedAt }
        }
      }
    }
  }
}
"""


def _is_delivered_order(order, expected_customer_id):
    if _canonical_gid("Customer", (order.get("customer") or {}).get("id")) != _canonical_gid(
        "Customer", expected_customer_id
    ):
        return False
    if str(order.get("displayFulfillmentStatus") or "").upper() != "FULFILLED":
        return False
    raw_fulfillments = order.get("fulfillments") or []
    fulfillments = (
        (raw_fulfillments.get("nodes") or [])
        if isinstance(raw_fulfillments, dict)
        else raw_fulfillments
    )
    successful = [
        fulfillment
        for fulfillment in fulfillments
        if str(fulfillment.get("status") or "").upper() == "SUCCESS"
    ]
    if not successful:
        return False
    return all(
        any(
            str(event.get("status") or "").upper() == "DELIVERED"
            for event in ((fulfillment.get("events") or {}).get("nodes") or [])
        )
        for fulfillment in successful
    )


def delivery_statuses(order_ids, shopify_customer_id, *, force=False):
    gids = sorted({_canonical_gid("Order", value) for value in order_ids if value})
    if not gids:
        return {}
    cache_key = (customer_hash(shopify_customer_id), tuple(gids))
    now_value = time.time()
    with _CACHE_LOCK:
        cached = _DELIVERY_CACHE.get(cache_key)
        if not force and cached and cached["expires_at"] > now_value:
            return dict(cached["value"])
    try:
        data, _served_version = shopify_sync.graphql_request(
            DELIVERY_QUERY,
            variables={"ids": gids},
        )
    except Exception:
        statuses = {}
    else:
        statuses = {
            str(order.get("id") or ""): _is_delivered_order(order, shopify_customer_id)
            for order in (data.get("nodes") or [])
            if order
        }
    with _CACHE_LOCK:
        _DELIVERY_CACHE[cache_key] = {
            "value": dict(statuses),
            "expires_at": now_value + DELIVERY_CACHE_TTL_SECONDS,
        }
    return statuses


def _judgeme_configured():
    return bool(
        str(os.getenv("JUDGEME_PRIVATE_API_TOKEN") or "").strip()
        and str(os.getenv("JUDGEME_PUBLIC_API_TOKEN") or "").strip()
        and _judgeme_shop_domain()
    )


def _judgeme_base_url():
    return str(os.getenv("JUDGEME_API_BASE_URL") or "https://judge.me/api/v1").strip().rstrip("/")


def _judgeme_shop_domain():
    return _clean_shop_domain(os.getenv("JUDGEME_SHOP_DOMAIN") or shopify_sync.get_config().get("store_domain"))


def _numeric_shopify_id(value):
    candidate = str(value or "").strip().rsplit("/", 1)[-1]
    return candidate if candidate.isdigit() else ""


def lookup_judgeme_product(shopify_product_id, *, force=False, request_get=None):
    external_id = _numeric_shopify_id(shopify_product_id)
    if not external_id or not _judgeme_configured():
        return {}
    now_value = time.time()
    with _CACHE_LOCK:
        cached = _JUDGEME_PRODUCT_CACHE.get(external_id)
        if not force and cached and cached["expires_at"] > now_value:
            return dict(cached["value"])
    getter = request_get or requests.get
    try:
        response = getter(
            f"{_judgeme_base_url()}/products/-1",
            params={
                "shop_domain": _judgeme_shop_domain(),
                "api_token": str(os.getenv("JUDGEME_PRIVATE_API_TOKEN") or "").strip(),
                "external_id": external_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        product = payload.get("product") or payload
        value = {
            "id": str(product.get("id") or ""),
            "external_id": str(product.get("external_id") or external_id),
        }
        if not value["id"]:
            value = {}
    except Exception:
        value = {}
    with _CACHE_LOCK:
        _JUDGEME_PRODUCT_CACHE[external_id] = {
            "value": dict(value),
            "expires_at": now_value + JUDGEME_PRODUCT_CACHE_TTL_SECONDS,
        }
    return value


def _reviewed_keys(owner_hash):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT shopify_order_id, shopify_product_id, status
                FROM collector_reviews
                WHERE customer_hash=%s
                  AND status IN ('submitting', 'submitted')
                """,
                (owner_hash,),
            )
            return {
                (
                    _canonical_gid("Order", row.get("shopify_order_id")),
                    _canonical_gid("Product", row.get("shopify_product_id")),
                )
                for row in (cur.fetchall() or [])
            }


def review_prompt(rows, shopify_customer_id):
    if not rows or not _judgeme_configured():
        return None
    try:
        reviewed = _reviewed_keys(customer_hash(shopify_customer_id))
    except Exception as error:
        _log_optional_feature_unavailable("reviews", error)
        return None
    statuses = delivery_statuses(
        [row.get("shopify_order_id") for row in rows],
        shopify_customer_id,
    )
    for row in rows:
        order_id = _canonical_gid("Order", row.get("shopify_order_id"))
        product_id = _canonical_gid("Product", row.get("shopify_product_id"))
        if not order_id or not product_id or not statuses.get(order_id):
            continue
        if (order_id, product_id) in reviewed:
            continue
        judge_product = lookup_judgeme_product(product_id)
        if not judge_product:
            return None
        try:
            public = _certificate_public_row(row)
        except Exception as error:
            LOGGER.warning(
                "Collector Vault review candidate was malformed error_type=%s",
                type(error).__name__,
            )
            continue
        review_ref = _signed_token(
            {
                "purpose": "review",
                "certificate_row_id": int(row.get("certificate_row_id") or 0),
                "customer_hash": customer_hash(shopify_customer_id),
                "shopify_order_id": order_id,
                "shopify_product_id": product_id,
            },
            ttl_seconds=REVIEW_REFERENCE_TTL_SECONDS,
        )
        return {
            "reference": review_ref,
            "product_title": public["product_title"],
            "shopify_product_id": product_id,
            "thumbnail_url": public["preview_url"],
        }
    return None


def _public_certificate_rows(rows, *, include_secure_assets=True):
    certificates = []
    skipped = 0
    for row in rows:
        try:
            certificates.append(
                _certificate_public_row(
                    row,
                    include_secure_assets=include_secure_assets,
                )
            )
        except Exception as error:
            skipped += 1
            LOGGER.error(
                "Collector Vault certificate serialization failed error_type=%s",
                type(error).__name__,
                exc_info=True,
            )
    if rows and not certificates:
        raise CollectorVaultDataError("No certificate rows could be serialized.")
    if skipped:
        LOGGER.warning(
            "Collector Vault omitted malformed certificate rows count=%s",
            skipped,
        )
    return certificates


def build_vault_payload(shopify_customer_id):
    rows, capabilities = _list_owned_certificates_with_capabilities(
        shopify_customer_id
    )
    secure_assets_available = bool(capabilities.get("secure_assets"))
    frame_product = (
        get_frame_product()
        if secure_assets_available and capabilities.get("frame_requests")
        else {"available": False}
    )
    return {
        "certificates": _public_certificate_rows(
            rows,
            include_secure_assets=secure_assets_available,
        ),
        "review_prompt": (
            review_prompt(rows, shopify_customer_id)
            if secure_assets_available
            else None
        ),
        "frame_product": {
            "available": bool(frame_product.get("available")),
            "product_id": frame_product.get("product_id") or "",
            "handle": frame_product.get("handle") or _frame_product_handle(),
            "variant_id": frame_product.get("variant_id") or "",
        },
    }


def _safe_idempotency_key(value):
    cleaned = str(value or "").strip()
    if not _IDEMPOTENCY_KEY.match(cleaned):
        raise CollectorVaultError("A valid idempotency key is required.")
    return cleaned


def _secure_asset_fulfilment_reference(row):
    reference = _asset_reference(row, "pdf")
    if reference.get("storage") == "r2":
        return {
            "certificate_row_id": int(row.get("certificate_row_id") or 0),
            "storage": "r2",
            "bucket": reference.get("bucket"),
            "key": reference.get("key"),
        }
    return {
        "certificate_row_id": int(row.get("certificate_row_id") or 0),
        "storage": "certificate_record",
    }


def create_frame_request(
    shopify_customer_id,
    *,
    certificate_reference,
    frame_variant_id,
    idempotency_key,
    allow_repeat=False,
):
    row = _resolve_certificate_reference(certificate_reference, shopify_customer_id)
    frame_product = get_frame_product(force=True)
    requested_variant = _canonical_gid("ProductVariant", frame_variant_id)
    if not frame_product.get("available") or requested_variant != frame_product.get("variant_id"):
        raise CollectorVaultUnavailableError("The framed certificate is currently unavailable.")
    owner_hash = customer_hash(shopify_customer_id)
    key = _safe_idempotency_key(idempotency_key)
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            if not allow_repeat:
                cur.execute(
                    """
                    SELECT request_reference, status, storefront_cart_id, checkout_url,
                           framed_shopify_order_id, framed_shopify_order_name
                    FROM collector_frame_requests
                    WHERE customer_hash=%s
                      AND certificate_row_id=%s
                      AND status IN ('pending', 'cart_created', 'ordered')
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (owner_hash, int(row.get("certificate_row_id") or 0)),
                )
                existing = cur.fetchone()
                if existing:
                    return dict(existing)
            cur.execute(
                """
                INSERT INTO collector_frame_requests (
                    customer_hash, shopify_customer_id, certificate_row_id, certificate_id,
                    original_shopify_order_id, original_shopify_order_name,
                    shopify_product_id, shopify_variant_id, artwork_title,
                    edition_number, edition_limit, certificate_asset_reference,
                    frame_product_id, frame_variant_id, idempotency_key
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s::jsonb, %s, %s, %s
                )
                ON CONFLICT (customer_hash, certificate_row_id, idempotency_key)
                DO UPDATE SET updated_at=now()
                RETURNING request_reference, status, storefront_cart_id, checkout_url,
                          framed_shopify_order_id, framed_shopify_order_name
                """,
                (
                    owner_hash,
                    shopify_customer_id,
                    int(row.get("certificate_row_id") or 0),
                    row.get("certificate_id"),
                    _canonical_gid("Order", row.get("shopify_order_id")),
                    row.get("shopify_order_name"),
                    _canonical_gid("Product", row.get("shopify_product_id")),
                    _canonical_gid("ProductVariant", row.get("shopify_variant_id")),
                    row.get("product_title") or "Sports Cave limited edition",
                    int(row.get("edition_number") or 0),
                    int(row.get("edition_limit") or row.get("edition_total") or 100),
                    json.dumps(_secure_asset_fulfilment_reference(row), separators=(",", ":")),
                    frame_product.get("product_id"),
                    requested_variant,
                    key,
                ),
            )
            created = cur.fetchone() or {}
        conn.commit()
    record_event(
        "frame_offer_clicked",
        shopify_customer_id,
        certificate_row_id=row.get("certificate_row_id"),
        event_key=f"frame-request:{created.get('request_reference')}",
    )
    return dict(created)


def _safe_checkout_url(value):
    raw = str(value or "").strip()
    try:
        parsed = urlparse(raw)
    except ValueError:
        return ""
    expected_shop = _clean_shop_domain(shopify_sync.get_config().get("store_domain"))
    allowed = {
        expected_shop,
        "www.sportscaveshop.com",
        "sportscaveshop.com",
        "account.sportscaveshop.com",
    }
    return raw if parsed.scheme == "https" and _clean_shop_domain(parsed.hostname) in allowed else ""


def mark_frame_cart_created(shopify_customer_id, *, request_reference, cart_id, checkout_url):
    reference = str(request_reference or "").strip()
    if not _UUID.match(reference):
        raise CollectorVaultError("Frame request reference is invalid.")
    safe_url = _safe_checkout_url(checkout_url)
    if not safe_url:
        raise CollectorVaultError("Shopify checkout URL is invalid.")
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collector_frame_requests
                SET storefront_cart_id=%s,
                    checkout_url=%s,
                    status=CASE WHEN status='ordered' THEN status ELSE 'cart_created' END,
                    updated_at=now()
                WHERE request_reference=%s
                  AND customer_hash=%s
                RETURNING request_reference, status, checkout_url
                """,
                (str(cart_id or "").strip()[:300], safe_url, reference, customer_hash(shopify_customer_id)),
            )
            row = cur.fetchone()
        conn.commit()
    if not row:
        raise CollectorVaultAuthorizationError("Frame request was not found for this customer.")
    record_event(
        "frame_checkout_created",
        shopify_customer_id,
        event_key=f"frame-checkout:{reference}",
    )
    return dict(row)


def _line_item_properties(line_item):
    properties = line_item.get("properties") or line_item.get("custom_attributes") or []
    if isinstance(properties, dict):
        return {str(key): str(value or "") for key, value in properties.items()}
    result = {}
    for item in properties:
        key = str(item.get("name") or item.get("key") or "").strip()
        if key:
            result[key] = str(item.get("value") or "").strip()
    return result


def _line_item_variant_id(line_item):
    return _canonical_gid(
        "ProductVariant",
        line_item.get("variant_id")
        or line_item.get("variant_admin_graphql_api_id")
        or ((line_item.get("variant") or {}).get("id")),
    )


def process_framed_order_paid(order_payload):
    payload = dict(order_payload or {})
    configured_variant_id = _configured_frame_variant_id()
    if not configured_variant_id:
        return {"updated": 0}
    request_references = {
        _line_item_properties(line_item).get("_sports_cave_frame_request", "")
        for line_item in (payload.get("line_items") or [])
        if _line_item_variant_id(line_item) == configured_variant_id
    }
    request_references = {value for value in request_references if _UUID.match(str(value or ""))}
    if not request_references:
        return {"updated": 0}
    customer_id = _canonical_gid("Customer", (payload.get("customer") or {}).get("id"))
    order_id = _canonical_gid("Order", payload.get("admin_graphql_api_id") or payload.get("id"))
    if not customer_id or not order_id:
        return {"updated": 0}
    updated = []
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collector_frame_requests
                SET status='ordered',
                    framed_shopify_order_id=%s,
                    framed_shopify_order_name=%s,
                    ordered_at=COALESCE(ordered_at, now()),
                    updated_at=now()
                WHERE request_reference = ANY(%s)
                  AND shopify_customer_id = ANY(%s)
                  AND frame_variant_id=%s
                  AND status <> 'ordered'
                RETURNING request_reference, customer_hash
                """,
                (
                    order_id,
                    str(payload.get("name") or "").strip(),
                    list(request_references),
                    customer_id_candidates(customer_id),
                    configured_variant_id,
                ),
            )
            updated = cur.fetchall() or []
        conn.commit()
    for row in updated:
        _record_hashed_event(
            "frame_order_completed",
            row.get("customer_hash"),
            event_key=f"frame-order:{order_id}:{row.get('request_reference')}",
        )
    return {"updated": len(updated), "request_references": [str(row.get("request_reference")) for row in updated]}


def _clean_review_text(value, *, maximum):
    text = _CONTROL_CHARACTERS.sub("", str(value or "")).strip()
    return html.escape(text[:maximum], quote=False)


def validate_review_photo(photo):
    if not photo:
        return None
    mime_type = str(photo.get("mime_type") or "").strip().lower()
    if mime_type not in SAFE_REVIEW_MIME_TYPES:
        raise CollectorVaultError("Photo must be a JPG, PNG or WebP image.")
    try:
        raw = base64.b64decode(str(photo.get("base64") or ""), validate=True)
    except Exception as error:
        raise CollectorVaultError("Photo data is invalid.") from error
    max_bytes = int(os.getenv("COLLECTOR_VAULT_REVIEW_PHOTO_MAX_BYTES") or REVIEW_PHOTO_MAX_BYTES)
    if not raw or len(raw) > max_bytes:
        raise CollectorVaultError(f"Photo must be smaller than {max_bytes // (1024 * 1024)} MB.")
    expected_format, extension = SAFE_REVIEW_MIME_TYPES[mime_type]
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            if image.format != expected_format:
                raise CollectorVaultError("Photo content does not match its file type.")
            max_pixels = int(
                os.getenv("COLLECTOR_VAULT_REVIEW_PHOTO_MAX_PIXELS")
                or REVIEW_PHOTO_MAX_PIXELS
            )
            if int(image.width) * int(image.height) > max_pixels:
                raise CollectorVaultError("Photo dimensions are too large.")
            cleaned = image.convert("RGB") if expected_format in {"JPEG", "WEBP"} else image.copy()
            output = io.BytesIO()
            save_options = {"quality": 88, "optimize": True} if expected_format in {"JPEG", "WEBP"} else {"optimize": True}
            cleaned.save(output, expected_format, **save_options)
            cleaned.close()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise CollectorVaultError("Photo could not be validated.") from error
    return {
        "bytes": output.getvalue(),
        "mime_type": mime_type,
        "extension": extension,
    }


def _resolve_review_reference(reference, shopify_customer_id):
    payload = _verify_signed_token(reference, expected_purpose="review")
    expected_hash = customer_hash(shopify_customer_id)
    if not hmac.compare_digest(str(payload.get("customer_hash") or ""), expected_hash):
        raise CollectorVaultAuthorizationError("Review request belongs to another customer.")
    row = _resolve_certificate_reference(
        _signed_token(
            {
                "purpose": "certificate",
                "certificate_row_id": payload.get("certificate_row_id"),
                "customer_hash": expected_hash,
            },
            ttl_seconds=60,
        ),
        shopify_customer_id,
    )
    if _canonical_gid("Order", row.get("shopify_order_id")) != payload.get("shopify_order_id"):
        raise CollectorVaultAuthorizationError("Review order does not match the certificate.")
    if _canonical_gid("Product", row.get("shopify_product_id")) != payload.get("shopify_product_id"):
        raise CollectorVaultAuthorizationError("Review product does not match the certificate.")
    statuses = delivery_statuses([row.get("shopify_order_id")], shopify_customer_id, force=True)
    if not statuses.get(_canonical_gid("Order", row.get("shopify_order_id"))):
        raise CollectorVaultAuthorizationError("Reviews are available after confirmed delivery.")
    return row


def _reviewer_details(row):
    name = str(row.get("customer_name") or "").strip() or "Sports Cave collector"
    email = str(row.get("customer_email") or "").strip()
    if not email or "@" not in email:
        raise CollectorVaultUnavailableError("The order does not contain a review email.")
    return name[:120], email[:320]


def _reserve_review_submission(owner_hash, row, rating):
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS attempts
                FROM collector_reviews
                WHERE customer_hash=%s
                  AND created_at > now() - interval '10 minutes'
                """,
                (owner_hash,),
            )
            if int((cur.fetchone() or {}).get("attempts") or 0) >= 3:
                raise CollectorVaultConflictError("Please wait before submitting another review.")
            cur.execute(
                """
                SELECT *
                FROM collector_reviews
                WHERE customer_hash=%s
                  AND shopify_order_id=%s
                  AND shopify_product_id=%s
                LIMIT 1
                """,
                (
                    owner_hash,
                    _canonical_gid("Order", row.get("shopify_order_id")),
                    _canonical_gid("Product", row.get("shopify_product_id")),
                ),
            )
            existing = cur.fetchone()
            if existing and existing.get("status") in {"submitting", "submitted"}:
                raise CollectorVaultConflictError("A review has already been submitted for this purchase.")
            if existing:
                cur.execute(
                    """
                    UPDATE collector_reviews
                    SET rating=%s, review_title=NULL, review_body='',
                        status='submitting', last_error=NULL, updated_at=now()
                    WHERE id=%s
                    RETURNING *
                    """,
                    (rating, existing.get("id")),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO collector_reviews (
                        customer_hash, shopify_customer_id, certificate_row_id,
                        shopify_order_id, shopify_product_id, rating,
                        review_title, review_body
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NULL, '')
                    RETURNING *
                    """,
                    (
                        owner_hash,
                        row.get("order_customer_id") or row.get("certificate_customer_id"),
                        int(row.get("certificate_row_id") or 0),
                        _canonical_gid("Order", row.get("shopify_order_id")),
                        _canonical_gid("Product", row.get("shopify_product_id")),
                        rating,
                    ),
                )
            submission = cur.fetchone() or {}
        conn.commit()
    return submission


def _upload_review_photo(submission, photo):
    if not photo:
        return {}
    if not r2_storage.safe_r2_enabled():
        raise CollectorVaultUnavailableError("Photo uploads are temporarily unavailable.")
    bucket = r2_storage.get_bucket_name("assets")
    if not bucket:
        raise CollectorVaultUnavailableError("Photo storage is not configured.")
    key = (
        f"collector-reviews/{datetime.now(timezone.utc):%Y/%m}/"
        f"{submission.get('submission_reference')}{photo.get('extension')}"
    )
    result = r2_storage.upload_bytes(
        bucket,
        key,
        photo.get("bytes") or b"",
        content_type=photo.get("mime_type"),
    )
    if not result.get("ok"):
        raise CollectorVaultUnavailableError("Photo could not be uploaded.")
    return {
        "bucket": bucket,
        "key": key,
        "mime_type": photo.get("mime_type"),
        "url": r2_storage.generate_presigned_download_url(bucket, key, expires_seconds=3600),
    }


def _submit_judgeme_review(row, submission, *, name, email, photo_upload, request_post=None):
    judge_product = lookup_judgeme_product(row.get("shopify_product_id"), force=True)
    if not judge_product:
        raise CollectorVaultUnavailableError("This artwork is not mapped in Judge.me.")
    post = request_post or requests.post
    payload = {
        "api_token": str(os.getenv("JUDGEME_PRIVATE_API_TOKEN") or "").strip(),
        "shop_domain": _judgeme_shop_domain(),
        "platform": "shopify",
        "name": name,
        "email": email,
        "rating": int(submission.get("rating") or 0),
        "body": submission.get("review_body") or "",
        "id": _numeric_shopify_id(row.get("shopify_product_id")),
    }
    if submission.get("review_title"):
        payload["title"] = submission.get("review_title")
    if photo_upload.get("url"):
        payload["picture_urls"] = [photo_upload["url"]]
    response = post(
        f"{_judgeme_base_url()}/reviews",
        json=payload,
        timeout=20,
    )
    if response.status_code >= 400:
        raise CollectorVaultUnavailableError("Judge.me did not accept the review.")
    result = response.json() if response.content else {}
    review = result.get("review") or result
    verification_status = str(
        review.get("verification_status") or review.get("source") or ""
    )
    if "verified" in review:
        verification_status = (
            "verified" if review.get("verified") is True else "unverified"
        )
    return {
        "review_id": str(review.get("id") or ""),
        "verification_status": verification_status,
        "judge_product_id": judge_product.get("id") or "",
    }


def submit_review(
    shopify_customer_id,
    *,
    review_reference,
    rating,
    body,
    title="",
    photo=None,
    request_post=None,
):
    try:
        rating_value = int(rating)
    except (TypeError, ValueError) as error:
        raise CollectorVaultError("Choose a star rating from 1 to 5.") from error
    if rating_value not in range(1, 6):
        raise CollectorVaultError("Choose a star rating from 1 to 5.")
    body_value = _clean_review_text(body, maximum=REVIEW_BODY_MAX_LENGTH)
    title_value = _clean_review_text(title, maximum=REVIEW_TITLE_MAX_LENGTH)
    if len(body_value) < REVIEW_BODY_MIN_LENGTH:
        raise CollectorVaultError("Review text must be at least 10 characters.")
    row = _resolve_review_reference(review_reference, shopify_customer_id)
    owner_hash = customer_hash(shopify_customer_id)
    cleaned_photo = validate_review_photo(photo)
    submission = _reserve_review_submission(owner_hash, row, rating_value)
    judge_submission = {
        **submission,
        "rating": rating_value,
        "review_title": title_value,
        "review_body": body_value,
    }
    photo_upload = {}
    try:
        photo_upload = _upload_review_photo(submission, cleaned_photo)
        name, email = _reviewer_details(row)
        judge_result = _submit_judgeme_review(
            row,
            judge_submission,
            name=name,
            email=email,
            photo_upload=photo_upload,
            request_post=request_post,
        )
    except Exception as error:
        with supabase_backend.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE collector_reviews
                    SET status='failed', last_error=%s, updated_at=now()
                    WHERE id=%s
                    """,
                    (str(error)[:500], submission.get("id")),
                )
            conn.commit()
        record_event(
            "review_submission_failed",
            shopify_customer_id,
            certificate_row_id=row.get("certificate_row_id"),
            event_key=f"review-failed:{submission.get('submission_reference')}:{int(time.time() // 60)}",
        )
        raise
    with supabase_backend.connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collector_reviews
                SET status='submitted',
                    judge_me_product_id=%s,
                    judge_me_review_id=%s,
                    judge_me_verification_status=%s,
                    photo_bucket=%s,
                    photo_object_key=%s,
                    photo_mime_type=%s,
                    last_error=NULL,
                    submitted_at=now(),
                    updated_at=now()
                WHERE id=%s
                RETURNING submission_reference, status, submitted_at
                """,
                (
                    judge_result.get("judge_product_id"),
                    judge_result.get("review_id"),
                    judge_result.get("verification_status"),
                    photo_upload.get("bucket"),
                    photo_upload.get("key"),
                    photo_upload.get("mime_type"),
                    submission.get("id"),
                ),
            )
            result = cur.fetchone() or {}
        conn.commit()
    record_event(
        "review_submitted",
        shopify_customer_id,
        certificate_row_id=row.get("certificate_row_id"),
        event_key=f"review-submitted:{result.get('submission_reference')}",
    )
    return {
        "status": "submitted",
        "submission_reference": str(result.get("submission_reference") or ""),
        "message": "Review submitted \u2713",
    }


def _record_hashed_event(event_name, owner_hash, *, certificate_row_id=None, event_key=""):
    if event_name not in COLLECTOR_EVENTS or not owner_hash:
        return None
    try:
        return supabase_backend.record_activity_log(
            action_type=event_name,
            page="Collector Vault",
            message=event_name.replace("_", " "),
            entity_type="shopify_customer_hash",
            entity_id=str(owner_hash),
            metadata={
                "event": event_name,
                "certificate_row_id": int(certificate_row_id or 0) or None,
            },
            event_key=str(event_key or "").strip()[:200],
            actor="customer_account",
        )
    except Exception:
        return None


def record_event(event_name, shopify_customer_id, *, certificate_row_id=None, event_key=""):
    return _record_hashed_event(
        str(event_name or "").strip(),
        customer_hash(shopify_customer_id),
        certificate_row_id=certificate_row_id,
        event_key=event_key,
    )
