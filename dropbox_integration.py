import json
import hashlib
import io
import os
from pathlib import Path
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
DROPBOX_SIMPLE_UPLOAD_LIMIT = 8 * 1024 * 1024
DROPBOX_UPLOAD_CHUNK_SIZE = 8 * 1024 * 1024
DROPBOX_MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

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


class DropboxConflictError(DropboxApiError):
    pass


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


def sanitize_path_component(value, *, fallback=""):
    """Return one Dropbox-safe filename component without changing its extension."""
    clean = str(value or "").strip()
    clean = "".join("_" if ord(char) < 32 else char for char in clean)
    for char in '<>:"/\\|?*':
        clean = clean.replace(char, "_")
    clean = re_collapse_spaces(clean).strip(" .")
    if clean in {"", ".", ".."}:
        clean = str(fallback or "").strip()
    if clean in {"", ".", ".."}:
        raise ValueError("A valid file or folder name is required.")
    return clean[:255]


def re_collapse_spaces(value):
    return " ".join(str(value or "").split())


def sanitize_relative_upload_path(relative_path):
    """Validate a browser-supplied relative path and preserve safe subfolders."""
    raw = str(relative_path or "").strip().replace("\\", "/")
    if not raw:
        raise ValueError("An upload filename is required.")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise ValueError("Upload paths must be relative to the current folder.")
    raw_parts = raw.split("/")
    if any(part.strip() == ".." for part in raw_parts):
        raise ValueError("Upload paths cannot leave the current folder.")
    parts = [
        sanitize_path_component(part)
        for part in raw_parts
        if part.strip() not in {"", "."}
    ]
    if not parts:
        raise ValueError("An upload filename is required.")
    return "/".join(parts)


def join_upload_path(current_folder, relative_path):
    clean_folder = normalize_dropbox_path(current_folder)
    if not clean_folder:
        raise ValueError("A Dropbox destination folder is required.")
    clean_relative = sanitize_relative_upload_path(relative_path)
    destination = normalize_dropbox_path(f"{clean_folder}/{clean_relative}")
    if not path_is_within_root(destination, clean_folder):
        raise ValueError("Upload paths cannot leave the current folder.")
    return destination


def get_metadata_if_exists(access_token, path):
    try:
        return get_file_metadata(access_token, path)
    except DropboxApiError as error:
        if _is_missing_path_error(error):
            return None
        raise


def path_exists(access_token, path):
    return get_metadata_if_exists(access_token, path) is not None


def numbered_path(access_token, path, *, max_attempts=999):
    clean_path = normalize_dropbox_path(path)
    parent, _, name = clean_path.rpartition("/")
    suffix = PurePosixPath(name).suffix
    stem = name[: -len(suffix)] if suffix else name
    for index in range(1, max(2, int(max_attempts or 999)) + 1):
        candidate_name = f"{stem} ({index}){suffix}"
        candidate = normalize_dropbox_path(f"{parent}/{candidate_name}")
        if not path_exists(access_token, candidate):
            return candidate
    raise DropboxConflictError("A free Dropbox filename could not be found.")


def resolve_upload_destination(access_token, path, conflict="cancel"):
    """Resolve explicit overwrite policy without silently replacing Dropbox data."""
    clean_path = normalize_dropbox_path(path)
    existing = get_metadata_if_exists(access_token, clean_path)
    if not existing:
        return {"path": clean_path, "mode": "add", "conflict": False}

    policy = str(conflict or "cancel").strip().casefold().replace(" ", "_")
    if policy in {"cancel", "skip"}:
        return None
    if policy in {"keep_both", "numbered"}:
        return {"path": numbered_path(access_token, clean_path), "mode": "add", "conflict": True}
    if policy in {"replace", "overwrite", "merge_replace"}:
        if str(existing.get(".tag") or "").casefold() == "folder":
            raise DropboxConflictError("A folder already uses this name.")
        return {"path": clean_path, "mode": "overwrite", "conflict": True}
    raise ValueError("Unknown Dropbox conflict choice.")


def _create_folder_path(access_token, path):
    clean_path = normalize_dropbox_path(path)
    if not clean_path:
        return ""
    client = team_space_client(access_token)
    built = ""
    for part in clean_path.strip("/").split("/"):
        built = normalize_dropbox_path(f"{built}/{part}")
        try:
            client.files_create_folder_v2(built, autorename=False)
        except Exception as error:
            if "conflict" not in str(error).casefold():
                raise _dropbox_error(error, "Dropbox folder could not be created.") from error
    return clean_path


def ensure_folder_path(access_token, path, *, root_path=None):
    clean_path = normalize_dropbox_path(path)
    if root_path and not path_is_within_root(clean_path, root_path):
        raise ValueError("This folder is outside the shared Files folder.")
    return _create_folder_path(access_token, clean_path)


def ensure_relative_folders(access_token, current_folder, relative_parent):
    clean_folder = normalize_dropbox_path(current_folder)
    clean_relative = str(relative_parent or "").strip().replace("\\", "/").strip("/")
    if not clean_relative:
        return clean_folder
    safe_relative = sanitize_relative_upload_path(f"{clean_relative}/placeholder.bin")
    safe_parent = str(PurePosixPath(safe_relative).parent)
    destination = join_upload_path(clean_folder, safe_parent)
    _create_folder_path(access_token, destination)
    return destination


def create_folder(access_token, current_folder, folder_name, *, conflict="cancel"):
    clean_name = sanitize_path_component(folder_name)
    destination = join_upload_path(current_folder, clean_name)
    existing = get_metadata_if_exists(access_token, destination)
    if existing:
        policy = str(conflict or "cancel").strip().casefold().replace(" ", "_")
        if policy in {"keep_both", "numbered"}:
            destination = numbered_path(access_token, destination)
        elif policy in {"cancel", "skip"}:
            return None
        else:
            raise DropboxConflictError("A file or folder already uses this name.")
    try:
        result = team_space_client(access_token).files_create_folder_v2(
            destination,
            autorename=False,
        )
    except Exception as error:
        raise _dropbox_error(error, "Dropbox folder could not be created.") from error
    metadata = getattr(result, "metadata", result)
    return _metadata_to_dict(metadata)


def _stream_size(stream, explicit_size=None):
    if explicit_size is not None:
        return max(0, int(explicit_size))
    try:
        current = stream.tell()
        stream.seek(0, os.SEEK_END)
        size = stream.tell()
        stream.seek(current)
        return max(0, int(size))
    except Exception as error:
        raise ValueError("Upload size is required for this file.") from error


def upload_stream(
    access_token,
    dropbox_path,
    stream,
    *,
    size=None,
    conflict="cancel",
    progress_callback=None,
    simple_limit=DROPBOX_SIMPLE_UPLOAD_LIMIT,
    chunk_size=DROPBOX_UPLOAD_CHUNK_SIZE,
    max_bytes=DROPBOX_MAX_UPLOAD_BYTES,
):
    """Upload one stream using explicit conflict handling and chunking when needed."""
    total_size = _stream_size(stream, size)
    if total_size > int(max_bytes):
        raise ValueError("This file is larger than the current upload limit.")
    resolved = resolve_upload_destination(access_token, dropbox_path, conflict)
    if resolved is None:
        return None
    destination = resolved["path"]
    sdk = _dropbox_sdk()
    mode = sdk.files.WriteMode.overwrite if resolved["mode"] == "overwrite" else sdk.files.WriteMode.add
    client = team_space_client(access_token)
    if hasattr(stream, "seek"):
        stream.seek(0)

    try:
        if total_size <= int(simple_limit):
            data = stream.read()
            metadata = client.files_upload(
                data,
                destination,
                mode=mode,
                autorename=False,
                mute=False,
            )
            if progress_callback:
                progress_callback(total_size, total_size)
            return _metadata_to_dict(metadata)

        first_chunk = stream.read(int(chunk_size))
        session = client.files_upload_session_start(first_chunk)
        uploaded = len(first_chunk)
        cursor = sdk.files.UploadSessionCursor(
            session_id=getattr(session, "session_id"),
            offset=uploaded,
        )
        if progress_callback:
            progress_callback(uploaded, total_size)
        remaining = total_size - uploaded
        while remaining > int(chunk_size):
            chunk = stream.read(int(chunk_size))
            if not chunk:
                raise IOError("The upload ended before the expected file size.")
            client.files_upload_session_append_v2(chunk, cursor)
            uploaded += len(chunk)
            cursor.offset = uploaded
            remaining = total_size - uploaded
            if progress_callback:
                progress_callback(uploaded, total_size)
        final_chunk = stream.read(max(0, remaining))
        commit = sdk.files.CommitInfo(
            path=destination,
            mode=mode,
            autorename=False,
            mute=False,
        )
        metadata = client.files_upload_session_finish(final_chunk, cursor, commit)
        uploaded += len(final_chunk)
        if progress_callback:
            progress_callback(uploaded, total_size)
        return _metadata_to_dict(metadata)
    except DropboxApiError:
        raise
    except Exception as error:
        raise _dropbox_error(error, "Dropbox upload failed.") from error
    finally:
        if hasattr(stream, "seek"):
            try:
                stream.seek(0)
            except Exception:
                pass


def upload_local_file(access_token, dropbox_path, local_path, *, conflict="cancel", progress_callback=None):
    source = Path(local_path)
    with source.open("rb") as stream:
        return upload_stream(
            access_token,
            dropbox_path,
            stream,
            size=source.stat().st_size,
            conflict=conflict,
            progress_callback=progress_callback,
        )


def upload_batch(access_token, current_folder, items, *, conflict="cancel", progress_callback=None):
    """Upload independent items and retain successes when another item fails."""
    clean_folder = normalize_dropbox_path(current_folder)
    successes = []
    failures = []
    rows = list(items or ())
    total = len(rows)
    for index, item in enumerate(rows, start=1):
        item = dict(item or {})
        relative_path = str(item.get("relative_path") or item.get("name") or "")
        try:
            clean_relative = sanitize_relative_upload_path(relative_path)
            parent = str(PurePosixPath(clean_relative).parent)
            if parent not in {"", "."}:
                ensure_relative_folders(access_token, clean_folder, parent)
            destination = join_upload_path(clean_folder, clean_relative)

            def on_file_progress(uploaded, file_total):
                if progress_callback:
                    progress_callback(index, total, clean_relative, uploaded, file_total)

            local_path = item.get("local_path")
            if local_path:
                metadata = upload_local_file(
                    access_token,
                    destination,
                    local_path,
                    conflict=conflict,
                    progress_callback=on_file_progress,
                )
            else:
                stream = item.get("stream")
                if stream is None and "data" in item:
                    stream = io.BytesIO(item.get("data") or b"")
                if stream is None:
                    raise ValueError("Upload data is missing.")
                metadata = upload_stream(
                    access_token,
                    destination,
                    stream,
                    size=item.get("size"),
                    conflict=conflict,
                    progress_callback=on_file_progress,
                )
            if metadata is None:
                failures.append({"relative_path": clean_relative, "error": "cancelled"})
            else:
                successes.append({"relative_path": clean_relative, "metadata": metadata})
        except Exception as error:
            failures.append({"relative_path": relative_path, "error": str(error)[:300]})
    return {"successes": successes, "failures": failures}


def rename_path(access_token, path, new_name, *, root_path=None):
    clean_path = normalize_dropbox_path(path)
    if root_path and not path_is_within_root(clean_path, root_path):
        raise ValueError("This item is outside the shared Files folder.")
    parent, _, old_name = clean_path.rpartition("/")
    if not parent or not old_name:
        raise ValueError("The shared Files folder cannot be renamed here.")
    destination = normalize_dropbox_path(f"{parent}/{sanitize_path_component(new_name)}")
    if destination.casefold() != clean_path.casefold() and path_exists(access_token, destination):
        raise DropboxConflictError("A file or folder already uses this name.")
    try:
        result = team_space_client(access_token).files_move_v2(
            clean_path,
            destination,
            autorename=False,
            allow_shared_folder=False,
        )
    except Exception as error:
        raise _dropbox_error(error, "Dropbox item could not be renamed.") from error
    metadata = getattr(result, "metadata", result)
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
