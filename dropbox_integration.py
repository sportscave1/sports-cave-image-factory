import json
import hashlib
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import PurePosixPath
from urllib.parse import urlencode


DROPBOX_AUTHORIZE_URL = "https://www.dropbox.com/oauth2/authorize"
DROPBOX_TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
DROPBOX_API_URL = "https://api.dropboxapi.com/2"
DROPBOX_CONTENT_URL = "https://content.dropboxapi.com/2"
DROPBOX_TEAM_FOLDER = "Sportscave Team Folder"
# Kept as the public root constant for older callers while the Files browser now
# points at the real shared team folder.
DROPBOX_ROOT_FOLDER = DROPBOX_TEAM_FOLDER
DROPBOX_REFRESH_TOKEN_ENV = "DROPBOX_REFRESH_TOKEN"
DROPBOX_ACCESS_TOKEN_ENV = "DROPBOX_ACCESS_TOKEN"
DROPBOX_ROOT_PATH_ENV = "DROPBOX_ROOT_PATH"
DROPBOX_CLIENT_CACHE_SECONDS = 45 * 60
DROPBOX_CLIENT_CACHE_LIMIT = 8

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


class DropboxFolderAccessError(DropboxApiError):
    """The configured shared folder is outside the app's visible Dropbox root."""

    def __init__(self, message, *, reason="not_visible"):
        super().__init__(message)
        self.reason = reason


_TEAM_SPACE_CLIENT_CACHE = {}
_TEAM_SPACE_CLIENT_LOCK = threading.Lock()


def _dropbox_sdk():
    import dropbox

    return dropbox


def _new_dropbox_client(access_token):
    return _dropbox_sdk().Dropbox(oauth2_access_token=str(access_token or "").strip())


def _account_to_dict(account):
    if isinstance(account, dict):
        return dict(account)
    name = getattr(account, "name", None)
    return {
        "account_id": str(getattr(account, "account_id", "") or ""),
        "email": str(getattr(account, "email", "") or ""),
        "display_name": str(getattr(name, "display_name", "") or ""),
        "name": {
            "display_name": str(getattr(name, "display_name", "") or ""),
            "familiar_name": str(getattr(name, "familiar_name", "") or ""),
        },
    }


def _metadata_to_dict(metadata):
    if isinstance(metadata, dict):
        return dict(metadata)
    class_name = metadata.__class__.__name__.casefold()
    tag = "folder" if "folder" in class_name else "file" if "file" in class_name else ""
    row = {".tag": tag}
    for field in (
        "id",
        "name",
        "path_display",
        "path_lower",
        "size",
        "rev",
        "content_hash",
        "client_modified",
        "server_modified",
    ):
        value = getattr(metadata, field, None)
        if isinstance(value, datetime):
            value = value.isoformat()
        if value is not None:
            row[field] = value
    return row


def _dropbox_error(error, fallback="Dropbox request failed."):
    message = str(error or "").strip() or fallback
    return DropboxApiError(message[:500])


def clear_team_space_client_cache():
    with _TEAM_SPACE_CLIENT_LOCK:
        _TEAM_SPACE_CLIENT_CACHE.clear()


def _team_space_context(access_token, *, force=False):
    """Return one Dropbox client rooted at the connected account's Team Space."""
    token = str(access_token or "").strip()
    if not token:
        raise DropboxConfigError("Dropbox access is not available.")
    cache_key = hashlib.sha256(token.encode("utf-8")).hexdigest()
    now = time.monotonic()
    with _TEAM_SPACE_CLIENT_LOCK:
        cached = _TEAM_SPACE_CLIENT_CACHE.get(cache_key) or {}
        if not force and cached.get("expires_at", 0) > now:
            return cached

    try:
        base_client = _new_dropbox_client(token)
        account = base_client.users_get_current_account()
        root_info = getattr(account, "root_info", None)
        root_namespace_id = str(getattr(root_info, "root_namespace_id", "") or "").strip()
        if not root_namespace_id:
            raise DropboxApiError("Dropbox account root namespace is unavailable.")
        path_root = _dropbox_sdk().common.PathRoot.root(root_namespace_id)
        rooted_client = base_client.with_path_root(path_root)
    except DropboxApiError:
        raise
    except Exception as error:
        raise _dropbox_error(error, "Dropbox Team Space could not be opened.") from error

    context = {
        "client": rooted_client,
        "account": _account_to_dict(account),
        "root_namespace_id": root_namespace_id,
        "expires_at": now + DROPBOX_CLIENT_CACHE_SECONDS,
    }
    with _TEAM_SPACE_CLIENT_LOCK:
        if len(_TEAM_SPACE_CLIENT_CACHE) >= DROPBOX_CLIENT_CACHE_LIMIT:
            oldest_key = min(
                _TEAM_SPACE_CLIENT_CACHE,
                key=lambda key: _TEAM_SPACE_CLIENT_CACHE[key].get("expires_at", 0),
            )
            _TEAM_SPACE_CLIENT_CACHE.pop(oldest_key, None)
        _TEAM_SPACE_CLIENT_CACHE[cache_key] = context
    return context


def team_space_client(access_token, *, force=False):
    return _team_space_context(access_token, force=force)["client"]


def dropbox_config():
    return {
        "app_key": str(os.getenv("DROPBOX_APP_KEY", "") or "").strip(),
        "app_secret": str(os.getenv("DROPBOX_APP_SECRET", "") or "").strip(),
        "redirect_uri": str(os.getenv("DROPBOX_REDIRECT_URI", "") or "").strip(),
        "refresh_token": str(os.getenv(DROPBOX_REFRESH_TOKEN_ENV, "") or "").strip(),
        "access_token": str(os.getenv(DROPBOX_ACCESS_TOKEN_ENV, "") or "").strip(),
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
    config = config or dropbox_config()
    if str(config.get("access_token") or "").strip():
        return ()
    if str(config.get("refresh_token") or "").strip():
        required = {
            "DROPBOX_APP_KEY": config.get("app_key"),
            "DROPBOX_APP_SECRET": config.get("app_secret"),
        }
        return tuple(key for key, value in required.items() if not str(value or "").strip())
    return (DROPBOX_REFRESH_TOKEN_ENV, DROPBOX_ACCESS_TOKEN_ENV)


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


def resolve_server_auth(config=None, *, validate=True):
    """Resolve Render credentials, preferring refresh-token OAuth."""
    config = config or dropbox_config()
    refresh_token = str(config.get("refresh_token") or "").strip()
    fallback_token = str(config.get("access_token") or "").strip()

    if refresh_token and config.get("app_key") and config.get("app_secret"):
        try:
            access_token = refresh_access_token(refresh_token, config)
            account = get_current_account(access_token) if validate else {}
            return {
                "access_token": access_token,
                "source": "refresh_token",
                "account": account,
            }
        except Exception:
            pass

    if fallback_token:
        try:
            account = get_current_account(fallback_token) if validate else {}
            return {
                "access_token": fallback_token,
                "source": "access_token",
                "account": account,
            }
        except Exception:
            pass

    if not refresh_token and not fallback_token:
        raise DropboxConfigError("Dropbox server credentials are not configured.")
    raise DropboxApiError("Dropbox server credentials could not be verified.")


def dropbox_rpc(access_token, endpoint, payload=None, *, timeout=12):
    context = _team_space_context(access_token)
    response = _requests().post(
        f"{DROPBOX_API_URL}/{str(endpoint).lstrip('/')}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Dropbox-API-Path-Root": json.dumps(
                {".tag": "root", "root": context["root_namespace_id"]}
            ),
        },
        data=json.dumps(payload or {}),
        timeout=timeout,
    )
    _raise_for_dropbox_response(response, "Dropbox request failed.")
    return response.json() if getattr(response, "content", b"") else {}


def get_current_account(access_token):
    return dict(_team_space_context(access_token)["account"])


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
    client = team_space_client(access_token)
    try:
        response = client.files_list_folder(
            clean_path,
            recursive=False,
            include_deleted=False,
            include_media_info=False,
            limit=limit,
        )
    except Exception as error:
        raise _dropbox_error(error) from error
    entries = list(getattr(response, "entries", ()) or ())
    seen_cursors = set()
    while bool(getattr(response, "has_more", False)) and len(entries) < limit:
        cursor = str(getattr(response, "cursor", "") or "").strip()
        if not cursor or cursor in seen_cursors:
            break
        seen_cursors.add(cursor)
        try:
            response = client.files_list_folder_continue(cursor)
        except Exception as error:
            raise _dropbox_error(error) from error
        entries.extend(getattr(response, "entries", ()) or ())
    return [_metadata_to_dict(entry) for entry in entries[:limit]]


def get_temporary_link(access_token, path):
    try:
        result = team_space_client(access_token).files_get_temporary_link(
            normalize_dropbox_path(path)
        )
    except Exception as error:
        raise _dropbox_error(error) from error
    link = str(getattr(result, "link", "") or "").strip()
    if not link:
        raise DropboxApiError("Dropbox did not return a temporary file link.")
    return link


def get_file_metadata(access_token, path):
    try:
        metadata = team_space_client(access_token).files_get_metadata(
            normalize_dropbox_path(path),
            include_media_info=False,
            include_deleted=False,
        )
    except Exception as error:
        raise _dropbox_error(error) from error
    return _metadata_to_dict(metadata)


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


def _is_missing_path_error(error):
    message = str(error or "").casefold()
    return any(
        marker in message
        for marker in (
            "not_found",
            "not found",
            "path/not_folder",
            "path/no_permission",
            "insufficient_permissions",
        )
    )


def _is_permission_error(error):
    message = str(error or "").casefold()
    return any(
        marker in message
        for marker in ("no_permission", "insufficient_permissions", "missing_scope")
    )


def find_team_folder(access_token, config=None):
    """Resolve the configured team folder to real Dropbox folder metadata."""
    configured_path = configured_root_path(config)
    configured_name = configured_path.strip("/").split("/")[-1]
    try:
        metadata = get_file_metadata(access_token, configured_path)
    except DropboxApiError as error:
        if not _is_missing_path_error(error):
            raise
        metadata = {}

    if metadata:
        if str(metadata.get(".tag") or "").casefold() != "folder":
            raise DropboxFolderAccessError(
                f"{configured_name} exists in Dropbox but is not a folder.",
                reason="not_folder",
            )
        return normalize_dropbox_path(
            metadata.get("path_display") or metadata.get("path_lower") or configured_path
        )

    # Dropbox paths are case-insensitive, but a root listing also handles older
    # folder names whose display casing differs from the configured path.
    if configured_path.count("/") == 1:
        try:
            root_entries = list_folder(access_token, "")
        except DropboxApiError as error:
            if _is_permission_error(error):
                raise DropboxFolderAccessError(
                    "The Dropbox app does not have permission to browse files.",
                    reason="permission",
                ) from error
            raise
        for entry in root_entries:
            if (
                str(entry.get(".tag") or "").casefold() == "folder"
                and str(entry.get("name") or "").casefold() == configured_name.casefold()
            ):
                return normalize_dropbox_path(
                    entry.get("path_display") or entry.get("path_lower") or configured_path
                )

    raise DropboxFolderAccessError(
        (
            f"{configured_name} is not visible to this Dropbox app. "
            "The app may be restricted to App Folder access."
        ),
        reason="not_visible",
    )


def path_is_within_root(path, root_path):
    clean_path = normalize_dropbox_path(path).casefold()
    clean_root = normalize_dropbox_path(root_path).casefold()
    return bool(clean_root and (clean_path == clean_root or clean_path.startswith(clean_root + "/")))


def breadcrumb_items(current_path, root_path):
    """Return Files plus root-relative breadcrumb labels and paths."""
    clean_current = normalize_dropbox_path(current_path)
    clean_root = normalize_dropbox_path(root_path)
    if not path_is_within_root(clean_current, clean_root):
        return (("Files", ""),)

    root_parts = [part for part in clean_root.strip("/").split("/") if part]
    current_parts = [part for part in clean_current.strip("/").split("/") if part]
    items = [("Files", "")]
    for index in range(len(root_parts) - 1, len(current_parts)):
        path = "/" + "/".join(current_parts[: index + 1])
        items.append((current_parts[index], path))
    return tuple(items)


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
    client = team_space_client(access_token)
    created = []
    for folder in [DROPBOX_ROOT_FOLDER, *[name for _, name in DROPBOX_FOLDER_OPTIONS]]:
        path = folder_path("" if folder == DROPBOX_ROOT_FOLDER else folder)
        try:
            client.files_create_folder_v2(path, autorename=False)
            created.append(path)
        except Exception as error:
            if "conflict" not in str(error).casefold():
                raise _dropbox_error(error) from error
    return created


def upload_file(access_token, dropbox_path, data, *, timeout=30):
    del timeout  # The Dropbox SDK owns transport timeouts for the shared rooted client.
    try:
        metadata = team_space_client(access_token).files_upload(
            data,
            normalize_dropbox_path(dropbox_path),
            mode=_dropbox_sdk().files.WriteMode.add,
            autorename=True,
            mute=False,
        )
    except Exception as error:
        raise _dropbox_error(error, "Dropbox upload failed.") from error
    return _metadata_to_dict(metadata)


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
