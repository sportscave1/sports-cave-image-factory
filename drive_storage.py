import base64
import json
import mimetypes
import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

try:
    from google.oauth2.service_account import Credentials as ServiceAccountCredentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
except ModuleNotFoundError:
    ServiceAccountCredentials = None
    build = None
    MediaFileUpload = None


load_dotenv()


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
MOCKUPS_FOLDER_NAME = "Mockups"


class DriveStorageError(RuntimeError):
    pass


def _require_google_client():
    if (
        ServiceAccountCredentials is None
        or build is None
        or MediaFileUpload is None
    ):
        raise DriveStorageError(
            "Google Drive libraries are not installed. Run `pip install -r requirements.txt`."
        )


def _load_service_account_info():
    base64_value = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64", "").strip()
    raw_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()

    if base64_value:
        try:
            raw_json = base64.b64decode(base64_value).decode("utf-8")
        except Exception as error:
            raise DriveStorageError(
                "GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 could not be decoded."
            ) from error

    if not raw_json:
        return None

    try:
        return json.loads(raw_json)
    except json.JSONDecodeError as error:
        raise DriveStorageError(
            "Google service account JSON is not valid JSON."
        ) from error


def is_drive_configured():
    try:
        return bool(get_root_folder_id() and _load_service_account_info())
    except DriveStorageError:
        return False


def get_root_folder_id():
    root_folder_id = os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID", "").strip()
    return root_folder_id or None


@lru_cache(maxsize=1)
def get_drive_service():
    _require_google_client()

    service_account_info = _load_service_account_info()
    root_folder_id = get_root_folder_id()

    if service_account_info is None or not root_folder_id:
        raise DriveStorageError(
            "Google Drive is not configured. Add GOOGLE_DRIVE_ROOT_FOLDER_ID and a service account JSON env var."
        )

    credentials = ServiceAccountCredentials.from_service_account_info(
        service_account_info,
        scopes=[DRIVE_SCOPE],
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _escape_query_value(value):
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _find_child(name, parent_folder_id, folder_only):
    service = get_drive_service()
    escaped_name = _escape_query_value(name)
    query_parts = [
        f"name = '{escaped_name}'",
        f"'{parent_folder_id}' in parents",
        "trashed = false",
    ]

    if folder_only is True:
        query_parts.append(f"mimeType = '{FOLDER_MIME_TYPE}'")
    elif folder_only is False:
        query_parts.append(f"mimeType != '{FOLDER_MIME_TYPE}'")

    response = (
        service.files()
        .list(
            q=" and ".join(query_parts),
            fields="files(id,name,webViewLink)",
            pageSize=1,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )

    files = response.get("files", [])
    if not files:
        return None

    return files[0]


def get_drive_folder_link(folder_id):
    return f"https://drive.google.com/drive/folders/{folder_id}"


def get_drive_file_link(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"


def ensure_drive_folder(parent_id, folder_name):
    existing_folder = _find_child(folder_name, parent_id, folder_only=True)
    if existing_folder:
        return existing_folder["id"]

    service = get_drive_service()
    created = (
        service.files()
        .create(
            body={
                "name": folder_name,
                "mimeType": FOLDER_MIME_TYPE,
                "parents": [parent_id],
            },
            fields="id,name",
            supportsAllDrives=True,
        )
        .execute()
    )
    return created["id"]


def upload_file_to_drive(local_path, parent_folder_id, mime_type=None):
    local_path = Path(local_path)
    service = get_drive_service()
    existing_file = _find_child(local_path.name, parent_folder_id, folder_only=False)
    resolved_mime_type = mime_type or mimetypes.guess_type(local_path.name)[0] or "application/octet-stream"
    media = MediaFileUpload(str(local_path), mimetype=resolved_mime_type, resumable=False)

    if existing_file:
        file_info = (
            service.files()
            .update(
                fileId=existing_file["id"],
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )
    else:
        file_info = (
            service.files()
            .create(
                body={"name": local_path.name, "parents": [parent_folder_id]},
                media_body=media,
                fields="id,name,webViewLink",
                supportsAllDrives=True,
            )
            .execute()
        )

    return {
        "file_name": local_path.name,
        "local_path": str(local_path.resolve()),
        "drive_file_id": file_info["id"],
        "drive_link": file_info.get("webViewLink") or get_drive_file_link(file_info["id"]),
    }


def upload_folder_to_drive(local_folder_path, parent_folder_id):
    local_folder_path = Path(local_folder_path)
    drive_folder_id = ensure_drive_folder(parent_folder_id, local_folder_path.name)
    uploaded_files = []

    for child_path in sorted(local_folder_path.iterdir(), key=lambda path: path.name.lower()):
        if child_path.is_dir():
            nested_upload = upload_folder_to_drive(child_path, drive_folder_id)
            uploaded_files.extend(nested_upload["uploaded_files"])
            continue

        uploaded_files.append(upload_file_to_drive(child_path, drive_folder_id))

    return {
        "folder_id": drive_folder_id,
        "folder_link": get_drive_folder_link(drive_folder_id),
        "uploaded_files": uploaded_files,
    }


def create_or_update_manifest(run_folder, drive_run_folder_id, uploaded_files):
    run_folder = Path(run_folder)
    manifest_path = run_folder / "manifest.json"
    manifest_data = {}

    if manifest_path.exists():
        with manifest_path.open("r", encoding="utf-8") as file_handle:
            manifest_data = json.load(file_handle)

    manifest_data["local_run_path"] = str(run_folder.resolve())
    manifest_data["drive_folder_id"] = drive_run_folder_id
    manifest_data["drive_folder_link"] = get_drive_folder_link(drive_run_folder_id)
    manifest_data["uploaded_files"] = uploaded_files

    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    manifest_upload = upload_file_to_drive(
        manifest_path,
        drive_run_folder_id,
        mime_type="application/json",
    )
    manifest_data["manifest_drive_file_id"] = manifest_upload["drive_file_id"]
    manifest_data["manifest_drive_link"] = manifest_upload["drive_link"]
    manifest_path.write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")
    upload_file_to_drive(manifest_path, drive_run_folder_id, mime_type="application/json")
    return manifest_data


def list_recent_drive_runs(limit=20):
    mockups_folder_id = ensure_drive_folder(get_root_folder_id(), MOCKUPS_FOLDER_NAME)
    service = get_drive_service()
    response = (
        service.files()
        .list(
            q=(
                f"'{mockups_folder_id}' in parents and "
                f"mimeType = '{FOLDER_MIME_TYPE}' and trashed = false"
            ),
            fields="files(id,name,modifiedTime,webViewLink)",
            orderBy="modifiedTime desc",
            pageSize=limit,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True,
        )
        .execute()
    )

    return [
        {
            "id": file_info["id"],
            "name": file_info["name"],
            "modified_time": file_info.get("modifiedTime"),
            "url": file_info.get("webViewLink") or get_drive_folder_link(file_info["id"]),
            "source": "google_drive",
        }
        for file_info in response.get("files", [])
    ]
