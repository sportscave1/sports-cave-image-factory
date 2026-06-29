import mimetypes
import os
import re
from datetime import date
from pathlib import Path


R2_ENV_KEYS = (
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_ENDPOINT",
)
R2_BUCKET_ENV_KEYS = {
    "certificates": "R2_BUCKET_CERTIFICATES",
    "assets": "R2_BUCKET_ASSETS",
    "backups": "R2_BUCKET_BACKUPS",
    "psd_archive": "R2_BUCKET_PSD_ARCHIVE",
}
DEFAULT_PRESIGNED_EXPIRY_SECONDS = 3600
TEST_BACKUP_KEY = "test/sports-cave-os-r2-test.txt"
TEST_BACKUP_BODY = b"Sports Cave OS R2 test upload"
DEFAULT_R2_CONNECT_TIMEOUT_SECONDS = 8
DEFAULT_R2_READ_TIMEOUT_SECONDS = 30
DEFAULT_R2_MAX_ATTEMPTS = 2


class R2ConfigurationError(RuntimeError):
    pass


def _clean_env(name):
    return str(os.getenv(name, "") or "").strip()


def _endpoint():
    endpoint = _clean_env("R2_ENDPOINT")
    if endpoint:
        return endpoint
    account_id = _clean_env("R2_ACCOUNT_ID")
    if account_id:
        return f"https://{account_id}.r2.cloudflarestorage.com"
    return ""


def safe_r2_enabled():
    return bool(
        _clean_env("R2_ACCESS_KEY_ID")
        and _clean_env("R2_SECRET_ACCESS_KEY")
        and _endpoint()
    )


def get_bucket_name(bucket_key):
    env_key = R2_BUCKET_ENV_KEYS.get(str(bucket_key or "").strip(), "")
    return _clean_env(env_key) if env_key else _clean_env(str(bucket_key or ""))


def get_r2_status():
    return {
        "configured": safe_r2_enabled(),
        "endpoint_configured": bool(_endpoint()),
        "certificates_bucket": get_bucket_name("certificates"),
        "assets_bucket": get_bucket_name("assets"),
        "backups_bucket": get_bucket_name("backups"),
        "psd_archive_bucket": get_bucket_name("psd_archive"),
    }


def _safe_error(message):
    return {"ok": False, "error": str(message or "R2 operation failed.")}


def _presigned_expiry(default=DEFAULT_PRESIGNED_EXPIRY_SECONDS):
    try:
        return int(_clean_env("R2_PRESIGNED_URL_EXPIRY_SECONDS") or default)
    except ValueError:
        return default


def _normalize_endpoint(endpoint):
    endpoint = str(endpoint or "").strip()
    if endpoint and not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint.rstrip("/")


def _env_int(name, default):
    try:
        return int(_clean_env(name) or default)
    except ValueError:
        return default


def _r2_log(event, **details):
    safe_details = " ".join(f"{key}={value}" for key, value in details.items() if value not in (None, ""))
    suffix = f" {safe_details}" if safe_details else ""
    print(f"CERTIFICATE ACTION: R2 {event}{suffix}", flush=True)


def get_r2_client():
    if not safe_r2_enabled():
        raise R2ConfigurationError(
            "Cloudflare R2 is not configured. Add R2 endpoint and access credentials in Render."
        )
    try:
        import boto3
        from botocore.config import Config
    except ImportError as error:
        raise RuntimeError("boto3 is not installed. Add boto3 to requirements.txt.") from error

    return boto3.client(
        "s3",
        endpoint_url=_normalize_endpoint(_endpoint()),
        aws_access_key_id=_clean_env("R2_ACCESS_KEY_ID"),
        aws_secret_access_key=_clean_env("R2_SECRET_ACCESS_KEY"),
        region_name="auto",
        config=Config(
            signature_version="s3v4",
            connect_timeout=max(_env_int("R2_CONNECT_TIMEOUT_SECONDS", DEFAULT_R2_CONNECT_TIMEOUT_SECONDS), 1),
            read_timeout=max(_env_int("R2_READ_TIMEOUT_SECONDS", DEFAULT_R2_READ_TIMEOUT_SECONDS), 1),
            retries={
                "max_attempts": max(_env_int("R2_MAX_ATTEMPTS", DEFAULT_R2_MAX_ATTEMPTS), 1),
                "mode": "standard",
            },
        ),
    )


def _require_bucket_and_key(bucket, key):
    bucket = str(bucket or "").strip()
    key = str(key or "").strip().lstrip("/")
    if not bucket:
        raise ValueError("R2 bucket name is missing.")
    if not key:
        raise ValueError("R2 object key is missing.")
    return bucket, key


def upload_bytes(bucket, key, data, content_type=None):
    try:
        bucket, key = _require_bucket_and_key(bucket, key)
        if isinstance(data, str):
            body = data.encode("utf-8")
        else:
            body = data if isinstance(data, (bytes, bytearray)) else bytes(data or b"")
        kwargs = {"Bucket": bucket, "Key": key, "Body": bytes(body)}
        if content_type:
            kwargs["ContentType"] = str(content_type)
        _r2_log("upload started", bucket=bucket, key=key, size_bytes=len(body))
        get_r2_client().put_object(**kwargs)
        _r2_log("upload completed", bucket=bucket, key=key, size_bytes=len(body))
        return {
            "ok": True,
            "bucket": bucket,
            "key": key,
            "size_bytes": len(body),
            "content_type": content_type or "",
        }
    except Exception as error:
        _r2_log("upload failed", bucket=bucket if "bucket" in locals() else "", key=key if "key" in locals() else "", error=error)
        return _safe_error(error)


def upload_file(bucket, key, local_path, content_type=None):
    try:
        path = Path(local_path)
        if not path.exists():
            raise FileNotFoundError(f"File does not exist: {path}")
        guessed_content_type = content_type or mimetypes.guess_type(path.name)[0]
        return upload_bytes(bucket, key, path.read_bytes(), guessed_content_type)
    except Exception as error:
        return _safe_error(error)


def generate_presigned_download_url(bucket, key, expires_seconds=DEFAULT_PRESIGNED_EXPIRY_SECONDS):
    try:
        bucket, key = _require_bucket_and_key(bucket, key)
        expires = int(expires_seconds or _clean_env("R2_PRESIGNED_URL_EXPIRY_SECONDS") or DEFAULT_PRESIGNED_EXPIRY_SECONDS)
        expires = max(60, min(expires, 604800))
        return get_r2_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires,
        )
    except Exception:
        return ""


def object_exists(bucket, key):
    try:
        bucket, key = _require_bucket_and_key(bucket, key)
        get_r2_client().head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def delete_object(bucket, key):
    try:
        bucket, key = _require_bucket_and_key(bucket, key)
        get_r2_client().delete_object(Bucket=bucket, Key=key)
        return {"ok": True, "bucket": bucket, "key": key}
    except Exception as error:
        return _safe_error(error)


def test_r2_connection():
    bucket = get_bucket_name("backups") or get_bucket_name("certificates") or get_bucket_name("assets")
    try:
        if not bucket:
            raise R2ConfigurationError("No R2 bucket environment variables are configured.")
        get_r2_client().head_bucket(Bucket=bucket)
        return {"ok": True, "bucket": bucket}
    except Exception as error:
        return _safe_error(error)


def test_upload_backup_file():
    bucket = get_bucket_name("backups")
    result = upload_bytes(
        bucket,
        TEST_BACKUP_KEY,
        TEST_BACKUP_BODY,
        content_type="text/plain; charset=utf-8",
    )
    if result.get("ok"):
        result["download_url"] = generate_presigned_download_url(
            bucket,
            TEST_BACKUP_KEY,
            expires_seconds=_presigned_expiry(),
        )
    return result


def safe_key_part(value):
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip().lower())
    return cleaned.strip("-") or "sports-cave"


def certificate_pdf_key(shopify_handle, shopify_order_name, edition_number):
    return (
        f"certificates/{safe_key_part(shopify_handle)}/{safe_key_part(shopify_order_name)}/"
        f"edition-{int(edition_number)}.pdf"
    )


def certificate_preview_key(shopify_handle, shopify_order_name, edition_number):
    return (
        f"certificates/{safe_key_part(shopify_handle)}/{safe_key_part(shopify_order_name)}/"
        f"edition-{int(edition_number)}-preview.png"
    )


def mockup_asset_key(shopify_handle, frame_type, filename):
    return f"mockups/{safe_key_part(shopify_handle)}/{safe_key_part(frame_type)}/{safe_key_part(filename)}"


def export_asset_key(filename, export_date=None):
    day = export_date or date.today()
    if hasattr(day, "isoformat"):
        day = day.isoformat()
    return f"exports/{safe_key_part(day)}/{safe_key_part(filename)}"


def psd_archive_key(shopify_handle, filename):
    return f"psd-archive/{safe_key_part(shopify_handle)}/{safe_key_part(filename)}"


def upload_mockup_file(local_path, *, shopify_handle, frame_type, filename=None, content_type=None):
    path = Path(local_path)
    key = mockup_asset_key(shopify_handle, frame_type, filename or path.name)
    return upload_file(get_bucket_name("assets"), key, path, content_type)


def upload_export_file(local_path, *, filename=None, export_date=None, content_type=None):
    path = Path(local_path)
    key = export_asset_key(filename or path.name, export_date=export_date)
    return upload_file(get_bucket_name("assets"), key, path, content_type)


def upload_psd_archive_file(local_path, *, shopify_handle, filename=None, content_type=None):
    path = Path(local_path)
    key = psd_archive_key(shopify_handle, filename or path.name)
    return upload_file(get_bucket_name("psd_archive"), key, path, content_type or "application/octet-stream")
