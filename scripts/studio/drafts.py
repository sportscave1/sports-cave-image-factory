"""Named draft checkpoints only. Never imports or executes application code."""
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import stat
import uuid

import studio

EXTENSIONS = {".py", ".html", ".css", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".md", ".ps1"}
DENIED = {"input", "output", "tmp", "logs", "node_modules", "venv", "secrets",
          "credentials", "runtime", "cache", "__pycache__"}
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024

def plain_path(path):
    """Reject symlinks, junctions and reparse points, including ancestors."""
    p = Path(path).absolute()
    for part in [p, *p.parents]:
        if part.exists() or part.is_symlink():
            s = part.lstat()
            if stat.S_ISLNK(s.st_mode) or getattr(s, "st_file_attributes", 0) & 0x400:
                raise ValueError("Linked/reparse paths are not permitted.")
    return p

def safe_file(root, name):
    if not isinstance(name, str) or "\\" in name or ":" in name or "\x00" in name:
        raise ValueError("Use a repository-relative forward-slash file path.")
    parts = name.split("/")
    if any(not p or p in {".", ".."} or p.startswith(".") or p.endswith((" ", ".")) for p in parts):
        raise ValueError("Hidden, traversal or ambiguous paths are forbidden.")
    rel = PurePosixPath(name)
    if rel.is_absolute() or rel.suffix.lower() not in EXTENSIONS:
        raise ValueError("Only approved source/text extensions can be checkpointed.")
    if any(p.lower() in DENIED or "secret" in p.lower() or "credential" in p.lower()
           or p.lower().startswith(("id_rsa", "id_ed25519")) for p in parts):
        raise ValueError("Sensitive/runtime path is forbidden.")
    root = plain_path(root).resolve()
    path = plain_path(root.joinpath(*parts))
    if not path.resolve().is_relative_to(root):
        raise ValueError("Path escaped assigned worktree.")
    if path.exists():
        info = path.stat()
        if not path.is_file() or info.st_nlink > 1:
            raise ValueError("Only ordinary, non-hardlinked source files are allowed.")
    return path

def read_source(root, name, allow_missing=False):
    p = safe_file(root, name)
    if not p.exists():
        if allow_missing:
            return {"path": name, "deleted": True}, None
        raise ValueError("Selected source file does not exist: " + name)
    if p.stat().st_size > MAX_FILE:
        raise ValueError("Source file exceeds 2 MiB: " + name)
    data = p.read_bytes()
    if len(data) > MAX_FILE or b"\x00" in data:
        raise ValueError("Binary/oversized source is not supported.")
    text = data.decode("utf-8-sig")
    if studio.secret_findings(text):
        raise ValueError("Potential credential found; value withheld: " + name)
    return {"path": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}, data

def assigned(registry, task_id, owner):
    if not owner:
        raise ValueError("Explicit task owner required.")
    task = studio.task_by_id(registry, task_id, owner)
    root = studio.identity(registry, task)
    original = Path(registry["original_repo"]).resolve()
    if root.resolve() == original or original in root.resolve().parents:
        raise ValueError("Drafts must be outside the original checkout.")
    return task, plain_path(root)

def state_root(home):
    return plain_path(Path(home) / ".studio" / "drafts")

def blob_path(home, digest):
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Invalid checkpoint content hash.")
    return plain_path(state_root(home) / "blobs" / digest)

def draft_by_id(registry, draft_id, owner):
    if not owner:
        raise ValueError("Owner required.")
    try:
        if str(uuid.UUID(draft_id)) != draft_id:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise ValueError("Use the exact draft UUID returned by NewDraft.")
    draft = next((d for d in registry.get("drafts", []) if d["id"] == draft_id), None)
    if not draft:
        raise ValueError("Unknown draft UUID.")
    task, root = assigned(registry, draft["task_id"], owner)
    if (draft["owner"] != owner or draft["branch"] != task["branch"]
            or Path(draft["worktree_path"]).resolve() != root.resolve()):
        raise RuntimeError("Draft/task ownership or workspace identity changed.")
    return draft, task, root

def new(home, task_id, owner, name):
    if not name or not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
        raise ValueError("Draft name requires 1-100 printable characters.")
    with studio.locked(home) as file:
        registry = studio.read(file)
        task, root = assigned(registry, task_id, owner)
        drafts = registry.setdefault("drafts", [])
        if any(d["task_id"] == task_id for d in drafts):
            raise RuntimeError("Task already has a draft. Reopen it; independent drafts need independent task worktrees.")
        if any(d["owner"] == owner and d["name"].casefold() == name.strip().casefold() for d in drafts):
            raise ValueError("Draft name already in use by this owner.")
        draft = {"id": str(uuid.uuid4()), "name": name.strip(), "task_id": task_id,
                 "category": task["category"], "branch": task["branch"], "worktree_path": str(root),
                 "owner": owner, "base_commit": task["base_commit"],
                 "current_commit": studio.git(root, "rev-parse", "HEAD"),
                 "revision": 0, "revisions": [], "created_at": studio.now(), "updated_at": studio.now(),
                 "editing_status": "Unsaved", "preview": {"enabled": False, "kind": "full-application",
                     "reason": "OS isolation runtime and safety probes not verified"},
                 "release_eligible": False}
        drafts.append(draft)
        registry["updated_at"] = studio.now()
        studio.atomic(file, registry)
        return draft

def save(home, draft_id, owner, expected_revision, files):
    """Checkpoint explicit selected files. Never changes source, index, or branch."""
    if not files or len(files) > 100:
        raise ValueError("Select 1-100 explicit source files; no recursive copies.")
    with studio.locked(home) as registry_file:
        registry = studio.read(registry_file)
        draft, task, root = draft_by_id(registry, draft_id, owner)
        if expected_revision != draft["revision"]:
            raise RuntimeError("Draft revision conflict. Reopen before saving.")
        previous = draft["revisions"][-1]["files"] if draft["revisions"] else []
        # Save is cumulative; omitted files stay selected, explicit deletion is recorded.
        names = sorted(set(files) | {f["path"] for f in previous})
        if len(names) > 100:
            raise ValueError("Draft selection exceeds 100 files.")
        if len({n.casefold() for n in names}) != len(names):
            raise ValueError("Case-aliased duplicate paths are forbidden.")
        old_names = {f["path"] for f in previous}
        before = studio.git(root, "rev-parse", "HEAD")
        captured = [read_source(root, n, n in old_names) for n in names]
        if sum(len(data or b"") for _, data in captured) > MAX_TOTAL:
            raise ValueError("Draft exceeds 20 MiB.")
        # Detect concurrent source changes without writing to the source tree.
        if before != studio.git(root, "rev-parse", "HEAD"):
            raise RuntimeError("Git revision changed while saving.")
        for meta, data in captured:
            check, again = read_source(root, meta["path"], meta["path"] in old_names)
            if check != meta or again != data:
                raise RuntimeError("Source changed during save; retry after edits settle.")
        blobs = state_root(home) / "blobs"
        blobs.mkdir(parents=True, exist_ok=True)
        for meta, data in captured:
            if data is None:
                continue
            blob = blob_path(home, meta["sha256"])
            if blob.exists():
                if hashlib.sha256(blob.read_bytes()).hexdigest() != meta["sha256"]:
                    raise RuntimeError("Checkpoint blob corruption; nothing registered.")
            else:
                # The shared lock serializes writers. A crash can leave an orphan,
                # but never publishes a partially written revision.
                with blob.open("xb") as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
        revision = {"number": draft["revision"] + 1, "commit": before, "saved_at": studio.now(),
                    "files": [m for m, _ in captured], "scope": "explicit selected files, not a complete application export"}
        draft["revisions"].append(revision)
        draft["revision"] = revision["number"]
        draft["current_commit"] = before
        draft["updated_at"] = registry["updated_at"] = studio.now()
        draft["editing_status"] = "Checkpoint Saved"
        draft["release_eligible"] = False
        studio.atomic(registry_file, registry)
        return draft

def inspect(home, draft_id, owner, revision=None, open_vscode=False):
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, task, root = draft_by_id(registry, draft_id, owner)
        number = draft["revision"] if revision is None else revision
        selected = next((r for r in draft["revisions"] if r["number"] == number), None)
        if number and not selected:
            raise ValueError("Unknown saved revision.")
        changes = []
        for meta in selected["files"] if selected else []:
            if not meta.get("deleted"):
                blob = blob_path(home, meta["sha256"])
                if not blob.is_file() or hashlib.sha256(blob.read_bytes()).hexdigest() != meta["sha256"]:
                    raise RuntimeError("Saved revision content missing/corrupt.")
            current, _ = read_source(root, meta["path"], allow_missing=True)
            if current != meta:
                changes.append(meta["path"])
        result = {**draft, "selected_revision": selected, "changed_since_checkpoint": changes,
                  "actual_commit": studio.git(root, "rev-parse", "HEAD"),
                  "source_modified_by_open": False}
        if open_vscode:
            studio.open_workspace(home, task)
        return result

def listing(home, owner):
    if not owner:
        raise ValueError("Owner required.")
    with studio.locked(home) as file:
        registry = studio.read(file)
        return [d for d in registry.get("drafts", []) if d["owner"] == owner]

def recover_copy(home, draft_id, owner, revision):
    """Export a saved checkpoint to a NEW recovery folder; never restore over source."""
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("RecoverDraft requires an explicit positive revision number.")
    saved = inspect(home, draft_id, owner, revision)
    selected = saved["selected_revision"]
    if not selected:
        raise ValueError("No saved revision.")
    with studio.locked(home):
        directory = state_root(home) / "recovery" / (draft_id + "-" + uuid.uuid4().hex)
        plain_path(directory).mkdir(parents=True, exist_ok=False)
        for meta in selected["files"]:
            if meta.get("deleted"):
                continue
            blob = blob_path(home, meta["sha256"])
            data = blob.read_bytes()
            if hashlib.sha256(data).hexdigest() != meta["sha256"]:
                raise RuntimeError("Recovery stopped: blob corruption.")
            target = safe_file(directory, meta["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as f:
                f.write(data)
        studio.atomic(directory / "recovery-manifest.json", selected)
        return {"draft_id": draft_id, "revision": revision, "recovery_path": str(directory),
                "source_modified": False, "note": "Compare manually; no application code was executed."}
