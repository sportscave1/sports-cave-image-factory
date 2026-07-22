import json
import os
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlencode


DROPBOX_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_API_URL = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT_URL = "https://content.dropboxapi.com/2"
DROPBOX_ROOT_FOLDER = "Sports Cave OS Assets"

DROPBOX_FOLDER_OPTIONS = (
    ("brand_assets", "01 Brand Assets"),
    ("plaques_templates", "02 Plaques & Templates"),
    ("psd_working_files", "03 PSD Working Files"),
    ("final_artwork", "04 Final Artwork"),
    ("mockups", "05 Mockups"),
    ("product_upload_assets", "06 Product Upload Assets"),
    ("certificates", "07 Certificates"),
    ("invoices_quotes", "08 Invoices & Quotes"),
    ("research_images", "09 Research Images"),
    ("archive", "10 Archive"),
)


class DropboxConfigError(RuntimeError):
    pass


class DropboxApiError(RuntimeError):
    pass


def dropbox_config():
    return {
        "app_key": str(os.getenv("DROPBOX_APP_KEY", "") or "").strip(),
        "app_secret": str(os.getenv("DROPBOX_APP_SECRET", "") or "").strip(),
        "redirect_uri": str(os.getenv("DROPBOX_REDIRECT_URI", "") or "").strip(),
    }


def missing_config_keys(config=None):
    config = config or dropbox_config()
    required = {
        "DROPBOX_APP_KEY": config.get("app_key"),
        "DROPBOX_APP_SECRET": config.get("app_secret"),
        "DROPBOX_REDIRECT_URI": config.get("redirect_uri"),
    }
    return tuple(key for key, value in required.items() if not str(value or "").strip())


def require_config(config=None):
    config = config or dropbox_config()
    missing = missing_config_keys(config)
    if missing:
        raise DropboxConfigError(f"Missing Dropbox setup: {', '.join(missing)}")
    return config


def build_authorization_url(state, config=None):
    config = require_config(config)
    params = {
        "client_id": config["app_key"],
        "response_type": "code",
        "redirect_uri": config["redirect_uri"],
        "token_access_type": "offline",
        "state": str(state or ""),
    }
    return f"{DROPBOX_AUTHORIZE_URL}?{urlencode(params)}"


def _requests():
    import requests

    return requests


def _raise_for_dropbox_response(response, fallback):
    if 200 <= int(response.status_code) < 300:
        return
    message = fallback
    try:
        data = response.json()
        message = data.get("error_summary") or data.get("error_description") or message
    except Exception:
        text = str(getattr(response, "text", "") or "").strip()
        if text:
            message = text[:300]
    raise DropboxApiError(message)


def exchange_code_for_refresh_token(code, config=None, *, timeout=12):
    config = require_config(config)
    response = _requests().post(
        DROPBOX_TOKEN_URL,
        data={
            "code": str(code or ""),
            "grant_type": "authorization_code",
            "redirect_uri": config["redirect_uri"],
        },
        auth=(config["app_key"], config["app_secret"]),
        timeout=timeout,
    )
    _raise_for_dropbox_response(response, "Dropbox connection failed.")
    data = response.json()
    refresh_token = str(data.get("refresh_token") or "").strip()
    if not refresh_token:
        raise DropboxApiError("Dropbox did not return a refresh token. Reconnect with offline access.")
    return data


def refresh_access_token(refresh_token, config=None, *, timeout=12):
    config = require_config(config)
    response = _requests().post(
        DROPBOX_TOKEN_URL,
        data={"refresh_token": str(refresh_token or ""), "grant_type": "refresh_token"},
        auth=(config["app_key"], config["app_secret"]),
        timeout=timeout,
    )
    _raise_for_dropbox_response(response, "Dropbox refresh failed.")
    access_token = str(response.json().get("access_token") or "").strip()
    if not access_token:
        raise DropboxApiError("Dropbox did not return an access token.")
    return access_token


def dropbox_rpc(access_token, endpoint, payload=None, *, timeout=12):
    response = _requests().post(
        f"{DROPBOX_API_URL}/{str(endpoint).lstrip('/')}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload or {}),
        timeout=timeout,
    )
    _raise_for_dropbox_response(response, "Dropbox request failed.")
    return response.json() if getattr(response, "content", b"") else {}


def get_current_account(access_token):
    return dropbox_rpc(access_token, "users/get_current_account", {})


def folder_path(folder_name=""):
    parts = [DROPBOX_ROOT_FOLDER]
    clean_folder = str(folder_name or "").strip().strip("/")
    if clean_folder:
        parts.append(clean_folder)
    return "/" + str(PurePosixPath(*parts))


def folder_options():
    return DROPBOX_FOLDER_OPTIONS


def folder_name_for_asset_type(asset_type):
    clean = str(asset_type or "").strip()
    mapping = dict(DROPBOX_FOLDER_OPTIONS)
    return mapping.get(clean, DROPBOX_FOLDER_OPTIONS[0][1])


def dropbox_upload_path(asset_type, filename):
    clean_name = PurePosixPath(str(filename or "upload.bin").replace("\\", "/")).name
    clean_name = clean_name.strip() or "upload.bin"
    return f"{folder_path(folder_name_for_asset_type(asset_type))}/{clean_name}"


def ensure_folder_structure(access_token):
    created = []
    for folder in [DROPBOX_ROOT_FOLDER, *[name for _, name in DROPBOX_FOLDER_OPTIONS]]:
        path = folder_path("" if folder == DROPBOX_ROOT_FOLDER else folder)
        try:
            dropbox_rpc(access_token, "files/create_folder_v2", {"path": path, "autorename": False})
            created.append(path)
        except DropboxApiError as error:
            if "conflict" not in str(error).casefold():
                raise
    return created


def upload_file(access_token, dropbox_path, data, *, timeout=30):
    response = _requests().post(
        f"{DROPBOX_CONTENT_URL}/files/upload",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/octet-stream",
            "Dropbox-API-Arg": json.dumps(
                {"path": dropbox_path, "mode": "add", "autorename": True, "mute": False}
            ),
        },
        data=data,
        timeout=timeout,
    )
    _raise_for_dropbox_response(response, "Dropbox upload failed.")
    return response.json()


def normalise_asset_metadata(
    *,
    dropbox_file_id,
    dropbox_path,
    name,
    size=0,
    asset_type="",
    uploaded_by_user_name="",
    uploaded_by_user_email="",
):
    name = str(name or "").strip()
    extension = PurePosixPath(name).suffix.lower().lstrip(".")
    return {
        "dropbox_file_id": str(dropbox_file_id or "").strip(),
        "dropbox_path": str(dropbox_path or "").strip(),
        "name": name,
        "file_extension": extension,
        "size": int(size or 0),
        "asset_type": str(asset_type or "").strip(),
        "status": "uploaded",
        "uploaded_by_user_name": str(uploaded_by_user_name or "").strip(),
        "uploaded_by_user_email": str(uploaded_by_user_email or "").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
