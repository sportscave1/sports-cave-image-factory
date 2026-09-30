"""Shared write-path rules for Ads packages. Historical read paths are untouched."""
from collections import Counter
from pathlib import PurePosixPath
import dropbox_integration as dropbox


def campaign_folder(destination, name, *, saved_folder=""):
    destination = dropbox.normalize_dropbox_path(destination)
    if saved_folder:
        return dropbox.normalize_dropbox_path(saved_folder)
    if PurePosixPath(destination).name.casefold() == name.casefold():
        return destination
    return dropbox.join_upload_path(destination, name)


def flat_items(items):
    """Keep leaf names; qualify colliding text assets with their existing route names."""
    items = [dict(item) for item in items]
    paths = [str(item['relative_path']).replace('\\', '/') for item in items]
    for path in paths:
        if not path or path.startswith('/') or any(p in {'.', '..'} for p in path.split('/')):
            raise ValueError('Invalid Ads package path.')
    counts = Counter(PurePosixPath(path).name.casefold() for path in paths)
    used = set()
    for item, path in zip(items, paths):
        name = PurePosixPath(path).name
        if counts[name.casefold()] > 1:
            name = path.replace('/', '--')
        if name.casefold() in used:
            raise ValueError(f'Ads package filename collision: {name}')
        used.add(name.casefold())
        item.update(relative_path=name, filename=name)
    return items


def saved_files_are_flat(workflow):
    root = workflow.get("saved_folder_path")
    if not root:
        return True
    root = dropbox.normalize_dropbox_path(root).casefold()
    return all(
        str(PurePosixPath(str(receipt["path"])).parent).casefold() == root
        for receipt in (workflow.get("outcomes") or {}).values()
        if receipt.get("status") == "saved" and receipt.get("path")
        and receipt.get("asset_type") != "meta_ads_package"
    )
