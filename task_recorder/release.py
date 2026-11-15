"""Verified Windows bundles and versioned code releases; never touches recorder data."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import struct
import uuid
import zipfile

FORMAT = "sports-cave.recorder.windows"
MANIFEST = "recorder-package.json"
REQUIRED = {"task_recorder/server.py", "task_recorder/install.py", "task_recorder/release.py",
            "task_recorder/release_health.py", "task_recorder/requirements.txt",
            "task_recorder/requirements-windows.txt", "native-source/build.ps1",
            "desktop_recorder/helper.py", "desktop_recorder/bin/DesktopRecorder.exe", "Install.ps1", "Install.cmd"}
LIMIT = 128 * 1024 * 1024
REQUIRED_V2 = {"desktop_recorder/download_install.py", "desktop_recorder/bin/build-manifest.json",
               "edge-adapter/manifest.json", "edge-adapter/accessibility.js", "edge-adapter/browser-identity.js",
               "edge-adapter/downloads.js", "download-host/DownloadReceiptHost.exe"}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if (not isinstance(name, str) or not name or "\\" in name or ":" in name or
            path.is_absolute() or any(part in {"", ".", ".."} for part in name.split("/"))):
        raise ValueError("Invalid package path.")
    return path


def windows_x64(data):
    if len(data) < 64 or data[:2] != b"MZ":
        raise ValueError("Native Windows executable is missing or invalid.")
    offset = struct.unpack_from("<I", data, 60)[0]
    if offset + 26 > len(data) or data[offset:offset+4] != b"PE\0\0" or struct.unpack_from("<H", data, offset+4)[0] != 0x8664:
        raise ValueError("Expected the reviewed x64 Windows recorder executable.")


def verify_files(manifest, read):
    if set(manifest) != {"format", "version", "protocol", "files"} or manifest["format"] != FORMAT or manifest["version"] not in {1,2} or manifest["protocol"] != 4:
        raise ValueError("Unsupported Windows recorder package.")
    files = manifest["files"]
    if not isinstance(files, dict) or not REQUIRED <= files.keys() or len(files) > 300:
        raise ValueError("Windows recorder package is incomplete.")
    if manifest['version']==2 and not REQUIRED_V2 <= files.keys():
        raise ValueError('Windows recorder download integration is incomplete.')
    total = 0
    for name, record in files.items():
        safe_name(name)
        if name == MANIFEST or set(record) != {"sha256", "size"} or type(record["size"]) is not int or not 0 < record["size"] <= LIMIT:
            raise ValueError("Invalid package manifest entry.")
        total += record["size"]
        if total > LIMIT:
            raise ValueError("Package exceeds its size limit.")
        data = read(name)
        if len(data) != record["size"] or digest(data) != record["sha256"]:
            raise ValueError("Package integrity check failed: " + name)
    windows_x64(read("desktop_recorder/bin/DesktopRecorder.exe"))
    if manifest['version']==2:
        windows_x64(read('download-host/DownloadReceiptHost.exe'))
        native=json.loads(read('desktop_recorder/bin/build-manifest.json').decode('utf-8-sig'))
        if native['executable_sha256']!=digest(read('desktop_recorder/bin/DesktopRecorder.exe')):
            raise ValueError('Native build identity does not match the packaged executable.')
        adapter = json.loads(read('edge-adapter/manifest.json'))
        if adapter['version'] not in {'0.3.4', '0.3.5'}:
            raise ValueError('Package requires scoped adapter 0.3.4 or 0.3.5.')
        if adapter['version'] == '0.3.5':
            if 'edge-adapter/prepared-context.js' not in files:
                raise ValueError('Prepared-context adapter module is missing.')
            for script in adapter['content_scripts']:
                if 'https://sports-cave-image-factory.onrender.com/*' in script['matches']:
                    if script['js'].index('prepared-context.js') >= script['js'].index('browser-identity.js'):
                        raise ValueError('Prepared-context adapter must load before browser identity.')
    return digest(canonical(manifest))


def verify_archive(data):
    if len(data) > LIMIT:
        raise ValueError("Package exceeds its size limit.")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or any(item.file_size > LIMIT for item in archive.infolist()):
            raise ValueError("Invalid or oversized package entries.")
        for name in names:
            safe_name(name)
        if MANIFEST not in names or archive.getinfo(MANIFEST).file_size > 128 * 1024:
            raise ValueError("Package manifest is missing or oversized.")
        manifest = json.loads(archive.read(MANIFEST))
        if set(names) != set(manifest.get("files", {})) | {MANIFEST}:
            raise ValueError("Package has unexpected files.")
        return verify_files(manifest, archive.read)


def verify_directory(root):
    root = Path(root).resolve()
    manifest_path = root / MANIFEST
    if manifest_path.stat().st_size > 128 * 1024:
        raise ValueError("Package manifest is oversized.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    def read(name):
        path = root.joinpath(*safe_name(name).parts)
        if path.is_symlink() or root not in path.resolve().parents:
            raise ValueError("Package files must stay inside the extracted directory.")
        return path.read_bytes()
    return manifest, verify_files(manifest, read)


def build_package(repo, native):
    repo = Path(repo)
    files = {}
    for package, source in (("task_recorder", repo / "task_recorder"),
                            ("desktop_recorder", repo / "windows-screen-recorder/desktop_recorder")):
        for path in sorted(source.iterdir()):
            if path.is_file() and path.suffix in {".py", ".js", ".css", ".html", ".txt"}:
                files[package + "/" + path.name] = path.read_bytes()
    files["desktop_recorder/bin/DesktopRecorder.exe"] = Path(native).read_bytes()
    for path in sorted((repo / "windows-screen-recorder/native").iterdir()):
        if path.is_file() and path.suffix in {".cs", ".ps1"}:
            files["native-source/" + path.name] = path.read_bytes()
    # New builds must include the full installed runtime, not a valid but
    # unusable legacy v1 archive. Retain v1 reading only for old releases.
    build_path = Path(native).with_name('build-manifest.json')
    build = json.loads(build_path.read_text(encoding='utf-8-sig'))
    if build.get('executable_sha256') != digest(files['desktop_recorder/bin/DesktopRecorder.exe']):
        raise ValueError('Native build identity does not match the candidate.')
    for name, value in files.items():
        if name.startswith('native-source/') and build.get('sources', {}).get(name.split('/',1)[1]) != digest(value):
            raise ValueError('Native source changed after compilation: ' + name)
    receipt = Path(native).with_name('DownloadReceiptHost.exe').read_bytes()
    if build.get('download_executable_sha256') != digest(receipt):
        raise ValueError('Download host build identity does not match the candidate.')
    files['desktop_recorder/bin/build-manifest.json'] = build_path.read_bytes()
    files['download-host/DownloadReceiptHost.exe'] = receipt
    for path in sorted((repo / 'windows-screen-recorder/edge-adapter').iterdir()):
        if path.is_file() and path.suffix in {'.js', '.json'}:
            files['edge-adapter/' + path.name] = path.read_bytes()
    files["Install.ps1"] = (repo / "scripts/Install-TaskRecorder.ps1").read_bytes()
    files["Install.cmd"] = b'@echo off\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1"\r\nif errorlevel 1 pause\r\n'
    manifest = dict(format=FORMAT, version=2, protocol=4,
                    files={name:dict(sha256=digest(data), size=len(data)) for name, data in sorted(files.items())})
    verify_files(manifest, files.__getitem__)
    files[MANIFEST] = canonical(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    result = output.getvalue()
    verify_archive(result)
    return result


def atomic_text(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def release_path(install, release_id):
    if not re.fullmatch(r"(?:[a-f0-9]{20}|[a-f0-9]{64})", release_id):
        raise ValueError("Invalid installed release identity.")
    path = Path(install) / "releases" / release_id
    if Path(install).resolve() not in path.resolve().parents:
        raise ValueError("Release left the installer directory.")
    return path


def prepare(source, install, bootstrap, run):
    """Prepare in its final path so the virtual environment is never relocated."""
    manifest, package_id = verify_directory(source)
    install = Path(install)
    install.mkdir(parents=True, exist_ok=True)
    # Leave room for Playwright's deeply nested files on Windows without
    # requiring a machine-wide long-path policy. ready.json retains the full
    # manifest digest; the directory is only a compact, collision-checked key.
    release_id = package_id[:20]
    destination = release_path(install, release_id)
    if destination.exists():
        # Retain previous/failed preparations for rollback and diagnosis.
        release_id = digest((package_id + uuid.uuid4().hex).encode())[:20]
        destination = release_path(install, release_id)
    app = destination / "app"
    app.mkdir(parents=True)
    atomic_text(destination / "preparation.json", json.dumps(dict(package_id=package_id, state="preparing")))
    for name in manifest["files"]:
        path = app.joinpath(*safe_name(name).parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(source).joinpath(*safe_name(name).parts), path)
    shutil.copy2(Path(source) / MANIFEST, app / MANIFEST)
    verify_directory(app)
    python = destination / "venv/Scripts/python.exe"
    run([str(bootstrap), "-m", "venv", str(destination / "venv")])
    run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--no-deps", "-r", str(app / "task_recorder/requirements-windows.txt")])
    if (app / 'task_recorder/requirements-ocr.txt').is_file():
        run([str(python), '-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps',
             '--target', str(destination / 'ocr'), '-r', str(app / 'task_recorder/requirements-ocr.txt')])
    run([str(python), "-m", "playwright", "install", "chromium"])
    run([str(python), "-I", "-B", str(app / "task_recorder/release_health.py"), "--app", str(app)])
    atomic_text(destination / "ready.json", json.dumps(dict(package_id=package_id)))
    return release_id


def check_release(install, release_id):
    path = release_path(install, release_id)
    ready = json.loads((path / "ready.json").read_text())
    if verify_directory(path / "app")[1] != ready["package_id"]:
        raise ValueError("Installed release no longer matches its verified package.")
    if not (path / "venv/Scripts/python.exe").is_file():
        raise ValueError("Installed Python environment is missing.")
    return path


def activate(install, release_id, stop_idle):
    install = Path(install)
    check_release(install, release_id)
    old = (install / "active.txt").read_text().strip() if (install / "active.txt").exists() else "legacy"
    if old != "legacy":
        check_release(install, old)
    stop_idle()  # Failure leaves the previous release selected.
    atomic_text(install / "previous.txt", old + "\n")
    atomic_text(install / "active.txt", release_id + "\n")
    return old


def rollback(install, stop_idle):
    install = Path(install)
    previous = (install / "previous.txt").read_text().strip()
    if previous == "legacy":
        if not (install / "app/task_recorder/server.py").is_file() or not (install / "venv/Scripts/python.exe").is_file():
            raise ValueError("No previous legacy installation is available.")
    else:
        check_release(install, previous)
    stop_idle()
    current = (install / "active.txt").read_text().strip()
    atomic_text(install / "active.txt", previous + "\n")
    atomic_text(install / "previous.txt", current + "\n")
    return previous
