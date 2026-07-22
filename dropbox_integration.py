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
DROPBOX_REFRESH_TOKEN_ENV = "DROPBOX_REFRESH_TOKEN"
DROPBOX_ROOT_PATH_ENV = "DROPBOX_ROOT_PATH"

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
        "refresh_token": str(os.getenv(DROPBOX_REFRESH_TOKEN_ENV, "") or "").strip(),
        "root_path": str(os.getenv(DROPBOX_ROOT_PATH_ENV, "") or "").strip(),
    }


def missing_config_keys(config=None, *, require_refresh=False, require_redirect=True):
    config = config or dropbox_config()
    required = {
        "DROPBOX_APP_KEY": config.get("app_key"),
        "DROPBOX_APP_SECRET": config.get("app_secret"),
    }
    if require_redirect:
        required["DROPBOX_REDIRECT_URI"] = config.get("redirect_uri")
    if require_refresh:
        required[DROPBOX_REFRESH_TOKEN_ENV] = config.get("refresh_token")
    return tuple(key for key, value in required.items() if not str(value or "").strip())


def missing_server_config_keys(config=None):
    return missing_config_keys(config, require_refresh=True, require_redirect=False)


def missing_oauth_config_keys(config=None):
    return missing_config_keys(config, require_refresh=False, require_redirect=True)


def require_config(config=None, *, require_refresh=False, require_redirect=True):
    config = config or dropbox_config()
    missing = missing_config_keys(
        config,
        require_refresh=require_refresh,
        require_redirect=require_redirect,
    )
    if missing:
        raise DropboxConfigError(f"Missing Dropbox setup: {', '.join(missing)}")
    return config


def build_authorization_url(state, config=None):
    config = require_config(config, require_redirect=True)
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
    config = require_config(config, require_redirect=False)
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


def normalize_dropbox_path(path):
    clean = str(path or "").strip().replace("\\", "/")
    if not clean or clean == "/":
        return ""
    parts = []
    for part in clean.split("/"):
        part = part.strip()
        if not part or part == ".":
            continue
        if part == "..":
            raise ValueError("Dropbox paths cannot contain '..'.")
        parts.append(part)
    return "/" + "/".join(parts) if parts else ""


def configured_root_path(config=None):
    config = config or dropbox_config()
    root = str(config.get("root_path") or "").strip() or DROPBOX_ROOT_FOLDER
    return normalize_dropbox_path(root)


def list_folder(access_token, path="", *, max_entries=2000):
    clean_path = normalize_dropbox_path(path)
    limit = max(1, min(int(max_entries or 2000), 2000))
    response = dropbox_rpc(
        access_token,
        "files/list_folder",
        {
            "path": clean_path,
            "recursive": False,
            "include_deleted": False,
            "include_media_info": False,
            "limit": limit,
        },
    )
    entries = list(response.get("entries") or [])
    while response.get("has_more") and len(entries) < limit:
        response = dropbox_rpc(
            access_token,
            "files/list_folder/continue",
            {"cursor": response.get("cursor")},
        )
        entries.extend(response.get("entries") or [])
    return entries[:limit]


def get_temporary_link(access_token, path):
    result = dropbox_rpc(
        access_token,
        "files/get_temporary_link",
        {"path": normalize_dropbox_path(path)},
    )
    link = str(result.get("link") or "").strip()
    if not link:
        raise DropboxApiError("Dropbox did not return a temporary file link.")
    return link


def get_file_metadata(access_token, path):
    return dropbox_rpc(
        access_token,
        "files/get_metadata",
        {
            "path": normalize_dropbox_path(path),
            "include_media_info": False,
            "include_deleted": False,
        },
    )


def format_file_size(size):
    value = max(0, int(size or 0))
    units = ("B", "KB", "MB", "GB", "TB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(amount)} {unit}"
            return f"{amount:.1f} {unit}" if amount < 10 else f"{amount:.0f} {unit}"
        amount /= 1024
    return f"{value} B"


def sort_folder_entries(entries):
    return sorted(
        (dict(entry or {}) for entry in entries or ()),
        key=lambda entry: (
            0 if str(entry.get(".tag") or "").casefold() == "folder" else 1,
            str(entry.get("name") or "").casefold(),
        ),
    )


def preferred_browser_root(entries):
    configured_root = configured_root_path()
    configured_name = configured_root.strip("/").split("/")[-1] if configured_root else ""
    for entry in entries or ():
        if (
            str(entry.get(".tag") or "").casefold() == "folder"
            and str(entry.get("name") or "").casefold() == configured_name.casefold()
        ):
            return normalize_dropbox_path(
                entry.get("path_display") or entry.get("path_lower") or configured_root
            )
    return configured_root


def file_open_details(access_token, path):
    clean_path = normalize_dropbox_path(path)
    metadata = get_file_metadata(access_token, clean_path)
    return {
        "metadata": metadata,
        "temporary_link": get_temporary_link(access_token, clean_path),
    }


def folder_path(folder_name=""):
    parts = [configured_root_path().strip("/") or DROPBOX_ROOT_FOLDER]
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
