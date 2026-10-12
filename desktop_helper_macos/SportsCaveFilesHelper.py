#!/usr/bin/env python3
import json
import hashlib
import re
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import parse_qs, urlparse


BLOCKED_EXTENSIONS = {
    ".app", ".application", ".bat", ".cmd", ".command", ".com", ".cpl",
    ".dmg", ".exe", ".hta", ".jar", ".js", ".jse", ".lnk", ".msi",
    ".pkg", ".ps1", ".py", ".pyw", ".reg", ".scr", ".sh", ".url",
    ".vbs", ".vbe", ".website", ".ws", ".wsc", ".wsf",
}
SUPPORT_DIR = Path.home() / "Library" / "Application Support" / "SportsCaveFilesHelper"


def fail(message):
    safe = str(message or "Sports Cave Files could not open this item.")
    script = (
        'on run argv\n'
        'display alert "Sports Cave Files" message (item 1 of argv)\n'
        'end run'
    )
    subprocess.run(
        ["/usr/bin/osascript", "-e", script, safe],
        check=False,
    )
    raise SystemExit(1)


def read_request(protocol_uri):
    parsed = urlparse(protocol_uri)
    if parsed.scheme != "sports-cave-files" or parsed.netloc != "open":
        fail("Unsupported request.")
    query = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    kind = query.get("kind", ["file"])[0]
    allowed = {"path", "kind", "hash", "size"} if kind == "master" else {"path", "kind"}
    if set(query) - allowed or len(query.get("path", [])) != 1:
        fail("Unsupported request.")
    if len(query.get("kind", ["file"])) != 1 or query.get("kind", ["file"])[0] not in {"file", "folder", "master"}:
        fail("Unsupported request.")
    if kind == "master":
        path = query['path'][0]
        prefix = '02_TASKS/03_DESIGNS-LIVE-ONLINE-UPLOADED/'
        if (not path.startswith(prefix) or '/' in path[len(prefix):] or not path.lower().endswith('.psd')
                or len(query.get('hash', [])) != 1 or not re.fullmatch('[a-fA-F0-9]{64}', query['hash'][0])
                or len(query.get('size', [])) != 1 or not re.fullmatch('[0-9]{1,16}', query['size'][0])):
            fail('The verified master request is invalid. Open it from Edition Ops or Orders.')
    return query["path"][0], kind


def resolve_target(relative_path):
    config_path = SUPPORT_DIR / "config.json"
    if not config_path.is_file():
        fail("The local Dropbox folder has not been configured. Run Install.command again.")
    root = Path(json.loads(config_path.read_text(encoding="utf-8"))["RootPath"]).expanduser().resolve()
    if not root.is_dir():
        fail("The configured Sportscave Team Folder is unavailable. Check Dropbox Desktop.")
    relative = str(relative_path or "")
    if not relative or relative != relative.strip() or relative.startswith(("/", "\\")) or ":" in relative or "\\" in relative:
        fail("The requested path is not allowed.")
    parts = relative.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        fail("The requested path is not allowed.")
    target = root.joinpath(*parts).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        fail("The requested path is outside the approved Dropbox folder.")
    if not target.exists():
        fail("This file is not available locally yet. Check Dropbox Desktop sync and try again.")
    if target.is_file() and target.suffix.casefold() in BLOCKED_EXTENSIONS:
        fail("This file type cannot be opened by the Sports Cave helper.")
    return target


def verify_master(target, expected_hash, size):
    """Read-only Dropbox block hash; reading allows Dropbox placeholder hydration."""
    combined = hashlib.sha256()
    with target.open('rb') as source:
        if os.fstat(source.fileno()).st_size != int(size):
            fail('The local master differs from Dropbox. Wait for sync and retry.')
        while True:
            block = source.read(4 * 1024 * 1024)
            if not block:
                break
            combined.update(hashlib.sha256(block).digest())
    if combined.hexdigest() != expected_hash.lower():
        fail('The local master differs from Dropbox. Wait for sync and retry.')


def open_target(target, prefer_adobe=True):
    if target.is_dir():
        subprocess.run(["/usr/bin/open", str(target)], check=True)
        return
    extension = target.suffix.casefold()
    if prefer_adobe and extension in {".psd", ".psb"}:
        preferred = subprocess.run(["/usr/bin/open", "-a", "Adobe Photoshop", str(target)], check=False)
        if preferred.returncode == 0:
            return
    if prefer_adobe and extension == ".ai":
        preferred = subprocess.run(["/usr/bin/open", "-a", "Adobe Illustrator", str(target)], check=False)
        if preferred.returncode == 0:
            return
    subprocess.run(["/usr/bin/open", str(target)], check=True)


def main():
    if len(sys.argv) != 2:
        fail("Unsupported request.")
    relative_path, _kind = read_request(sys.argv[1])
    target = resolve_target(relative_path)
    if _kind == 'master':
        query = parse_qs(urlparse(sys.argv[1]).query)
        verify_master(target, query['hash'][0], query['size'][0])
    open_target(target, prefer_adobe=_kind != 'master')


if __name__ == "__main__":
    try:
        main()
    except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        fail(str(error))
