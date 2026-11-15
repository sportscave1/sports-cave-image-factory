from contextlib import suppress
from pathlib import Path, PurePosixPath
import time

import dropbox_integration
import image_factory


MASTER_PATH_KEYS = ("webp_path", "jpg_path")
REVIEW_PATH_KEYS = ("review_path",)
DROPBOX_RETRY_ATTEMPTS = 3
DROPBOX_RETRY_SLEEP_SECONDS = 0.25
MOCKUP_DROPBOX_UPLOAD_CHUNK_SIZE = 1024 * 1024


class MockupDropboxUploadError(RuntimeError):
    def __init__(self, message, failures=None):
        super().__init__(message)
        self.failures = list(failures or ())


def mockup_temp_root():
    return image_factory.create_temp_run_parent()


def safe_temp_path(path):
    if not path:
        return None
    candidate = Path(path)
    if not image_factory.is_path_within_directory(candidate, mockup_temp_root()):
        return None
    return candidate


def safe_unlink_temp_file(path):
    candidate = safe_temp_path(path)
    if not candidate:
        return False
    with suppress(FileNotFoundError, PermissionError):
        candidate.unlink()
        return True
    return False


def cleanup_generated_master_dirs(run_dir):
    root = safe_temp_path(run_dir)
    if not root or not root.is_dir():
        return []
    deleted = []
    for dirname in (
        "review",
        image_factory.WEBP_CACHE_FOLDER_NAME,
        image_factory.JPG_CACHE_FOLDER_NAME,
        "uploaded",
        image_factory.SHOPIFY_UPLOADS_FOLDER_NAME,
        image_factory.SOCIALS_FOLDER_NAME,
        "zip",
    ):
        candidate = root / dirname
        if not candidate.exists():
            continue
        if not image_factory.is_path_within_directory(candidate, root):
            continue
        with suppress(FileNotFoundError, PermissionError):
            if candidate.is_dir():
                for child in candidate.iterdir():
                    if child.is_file():
                        child.unlink()
                candidate.rmdir()
                deleted.append(candidate)
            elif candidate.is_file():
                candidate.unlink()
                deleted.append(candidate)
    return deleted


def _dropbox_relative_for_path(path_key, local_path):
    filename = dropbox_integration.sanitize_path_component(Path(local_path).name)
    if path_key == "webp_path":
        return f"WEBP/{filename}"
    if path_key == "jpg_path":
        return f"jpg/{filename}"
    return filename


def _upload_local_with_retries(
    access_token,
    destination,
    relative_path,
    local_path,
    *,
    conflict,
    retries,
):
    dropbox_path = dropbox_integration.join_upload_path(destination, relative_path)
    attempts = max(1, int(retries or 1))
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            source = Path(local_path)
            with source.open("rb") as stream:
                return dropbox_integration.upload_stream(
                    access_token,
                    dropbox_path,
                    stream,
                    size=source.stat().st_size,
                    conflict=conflict,
                    simple_limit=0,
                    chunk_size=MOCKUP_DROPBOX_UPLOAD_CHUNK_SIZE,
                )
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(DROPBOX_RETRY_SLEEP_SECONDS)
    raise last_error


def upload_asset_files_to_dropbox(
    access_token,
    destination,
    asset_record,
    *,
    conflict="replace",
    retries=DROPBOX_RETRY_ATTEMPTS,
    cleanup_successful=True,
):
    asset = dict(asset_record or {})
    successes = []
    failures = []
    retry_files = []

    for path_key in MASTER_PATH_KEYS:
        local_path = asset.get(path_key)
        if not local_path:
            continue
        local_path = Path(local_path)
        relative_path = _dropbox_relative_for_path(path_key, local_path)
        if not local_path.exists():
            failures.append(
                {
                    "asset_key": asset.get("key"),
                    "relative_path": relative_path,
                    "path_key": path_key,
                    "error": "Local retry file is missing.",
                }
            )
            continue
        try:
            metadata = _upload_local_with_retries(
                access_token,
                destination,
                relative_path,
                local_path,
                conflict=conflict,
                retries=retries,
            )
        except Exception as error:
            failures.append(
                {
                    "asset_key": asset.get("key"),
                    "relative_path": relative_path,
                    "path_key": path_key,
                    "local_path": str(local_path),
                    "error": str(error)[:300],
                }
            )
            retry_files.append(
                {
                    "asset_key": asset.get("key"),
                    "path_key": path_key,
                    "relative_path": relative_path,
                    "local_path": str(local_path),
                }
            )
            continue

        dropbox_path = dropbox_integration.normalize_dropbox_path(
            metadata.get("path_display")
            or metadata.get("path_lower")
            or f"{destination}/{relative_path}"
        )
        asset[f"{path_key}_dropbox_path"] = dropbox_path
        asset[f"{path_key}_dropbox_metadata"] = dict(metadata)
        successes.append({"relative_path": relative_path, "metadata": dict(metadata)})
        if cleanup_successful:
            safe_unlink_temp_file(local_path)
            asset[path_key] = None

    for path_key in REVIEW_PATH_KEYS:
        if asset.get(path_key):
            safe_unlink_temp_file(asset[path_key])
            asset[path_key] = None

    asset["dropbox_upload_status"] = "failed" if failures else "saved"
    asset["dropbox_retry_files"] = retry_files
    asset["dropbox_upload_failures"] = failures
    return {
        "asset": asset,
        "successes": successes,
        "failures": failures,
        "retry_files": retry_files,
    }


def result_retry_files(result):
    retry_files = []
    for asset in (result or {}).get("assets") or ():
        for retry_file in (asset or {}).get("dropbox_retry_files") or ():
            retry_files.append(dict(retry_file))
        for path_key in MASTER_PATH_KEYS:
            local_path = (asset or {}).get(path_key)
            if local_path:
                retry_files.append(
                    {
                        "asset_key": (asset or {}).get("key"),
                        "path_key": path_key,
                        "relative_path": _dropbox_relative_for_path(path_key, local_path),
                        "local_path": str(local_path),
                    }
                )
    return retry_files


def retry_result_uploads(
    access_token,
    result,
    *,
    conflict="replace",
    retries=DROPBOX_RETRY_ATTEMPTS,
    cleanup_successful=True,
):
    updated = dict(result or {})
    destination = dropbox_integration.normalize_dropbox_path(updated.get("dropbox_saved_path") or "")
    if not destination:
        raise MockupDropboxUploadError("Dropbox destination is not available for retry.")

    assets = []
    all_successes = []
    all_failures = []
    for asset in updated.get("assets") or ():
        upload_result = upload_asset_files_to_dropbox(
            access_token,
            destination,
            asset,
            conflict=conflict,
            retries=retries,
            cleanup_successful=cleanup_successful,
        )
        uploaded_asset = upload_result["asset"]
        assets.append(uploaded_asset)
        all_successes.extend(upload_result["successes"])
        all_failures.extend(upload_result["failures"])

    updated["assets"] = assets
    updated["dropbox_uploaded_files"] = list(updated.get("dropbox_uploaded_files") or ()) + all_successes
    updated["dropbox_upload_failures"] = all_failures
    updated["dropbox_retry_files"] = result_retry_files(updated)
    updated["dropbox_upload_status"] = "failed" if all_failures else "saved"
    if not all_failures:
        cleanup_generated_master_dirs(updated.get("run_dir"))
    return updated


def dropbox_asset_path(asset, path_key):
    asset = asset or {}
    return asset.get(f"{path_key}_dropbox_path") or ""


def dropbox_selected_manifest(assets, selected_groups):
    selected_groups = set(selected_groups or ())
    entries = []
    for asset in sorted(
        assets or (),
        key=lambda item: (
            int(item.get("product_sort_position") or 10_000),
            str(item.get("label") or item.get("key") or "").casefold(),
        ),
    ):
        group = image_factory.get_asset_zip_group(asset)
        if selected_groups and group not in selected_groups:
            continue
        for path_key in MASTER_PATH_KEYS:
            dropbox_path = dropbox_asset_path(asset, path_key)
            if not dropbox_path:
                continue
            filename = Path(dropbox_path).name
            product_output_filename = str(asset.get("product_output_filename") or "")
            if product_output_filename:
                filename = str(Path(product_output_filename).with_suffix(Path(dropbox_path).suffix.casefold()))
            relative_path = str(PurePosixPath("WEBP" if path_key == "webp_path" else "jpg") / filename)
            entries.append(
                {
                    "asset_key": asset.get("key"),
                    "asset_label": asset.get("label"),
                    "product_slot_id": asset.get("product_slot_id"),
                    "product_sort_position": asset.get("product_sort_position"),
                    "category": group,
                    "relative_path": relative_path,
                    "dropbox_path": dropbox_path,
                    "metadata": asset.get(f"{path_key}_dropbox_metadata") or {},
                }
            )
    return entries
