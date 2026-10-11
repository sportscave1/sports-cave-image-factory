"""Local-only Developer Studio; no application imports, servers, pushes or deployments."""
import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

CATEGORIES = {
    "ADS": r"\b(meta|ads?|advertising|posting|instant experience|carousel|creative refresh)\b",
    "EMAIL": r"\b(email|crm|subscribers?|campaigns?|welcome series|abandoned checkout|post purchase|win back|customer flows?|segments?|automations?)\b",
    "PRODUCTS": r"\b(products?|product uploads?|mockups?|design studio|tagging|product imagery|descriptions?)\b",
    "EDITIONS": r"\b(editions?|edition ops|certificates?|numbering|allocation|inventory|overrides)\b",
    "CORE": r"\b(core|home|navigation|sidebar|top bar|shared ui|shared components|site speed|site.wide|responsive|image protection|accounts|access|authentication|security|infrastructure)\b",
    "INTEGRATIONS": r"\b(integrations?|shared apis?|analytics|reporting|cross.module|shared backend|data sync|multi.system)\b",
    "COMMERCE": r"\b(orders?|fulfilment|fulfillment|returns?|refunds?|order management)\b",
    "GROWTH": r"\b(social media|social inbox|seo|reviews|organic)\b",
    "RELEASE": r"\b(approved integration|publishing|release candidates?|release operations|deployment readiness|publish)\b",
}
STATES = ["Planned", "In Progress", "Implemented Locally", "Tested", "Ready for Review",
          "Approved", "Integrated", "Released", "Blocked"]
DEFAULT_HOME = Path(os.environ.get("SPORTS_CAVE_STUDIO_HOME", "C:/Dev/SportsCaveWorktrees"))
TERMINAL = {"Integrated", "Released"}

def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def git(repo, *args):
    p = subprocess.run(["git", "--no-optional-locks", "-C", str(repo), *args],
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or p.stdout.strip())
    return p.stdout.rstrip("\r\n")

def sha(repo, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision or ""):
        raise ValueError("Supply an exact 40-character commit, never a moving branch.")
    return git(repo, "rev-parse", "--verify", revision + "^{commit}")

def common(repo):
    return str(Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve())

def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)

@contextlib.contextmanager
def locked(home):
    state = home / ".studio"
    state.mkdir(parents=True, exist_ok=True)
    lock = state / "registry.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError("Registry occupied. Retry later. Check lock PID/owner before any manual recovery.")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"pid": os.getpid(), "created": now()}, f)
        yield state / "registry.json"
    finally:
        lock.unlink()

def read(path):
    d = json.loads(path.read_text(encoding="utf-8"))
    if d.get("schema_version") != 1:
        raise RuntimeError("Unsupported registry schema; no changes made.")
    return d

def route(description, override=None):
    if override:
        if override.upper() not in CATEGORIES:
            raise ValueError("Unknown category")
        return [override.upper()]
    normalized = description.lower().replace("meta campaigns", "meta").replace("meta review", "meta")
    normalized = normalized.replace("approved integration", "publishing")
    return [k for k, pattern in CATEGORIES.items() if re.search(pattern, normalized)]

def identity(d, item):
    path = Path(item["worktree_path"])
    if not path.is_dir():
        raise RuntimeError("Workspace missing; preserve registry entry and investigate.")
    if common(path) != d["common_dir"] or git(path, "branch", "--show-current") != item["branch"]:
        raise RuntimeError("Workspace identity mismatch; refusing to reassign.")
    if Path(git(path, "rev-parse", "--show-toplevel")).resolve() != path.resolve():
        raise RuntimeError("Not the assigned worktree root")
    return path

def task_by_id(d, task_id, owner=None):
    task = next((t for t in d["tasks"] if t["id"] == task_id), None)
    if not task:
        raise ValueError("Unknown task ID")
    if owner and owner != task["owner"]:
        raise RuntimeError("Owned by another session. Ask its owner; do not take over.")
    return task

def workspace_file(home, item):
    path = home / ".studio" / "workspaces" / (item["id"] + ".code-workspace")
    atomic(path, {"folders": [{"name": item["id"] + " | " + item["category"], "path": item["worktree_path"]}],
        "settings": {"window.title": item["id"] + " | " + item["branch"],
                     "git.autofetch": False, "task.allowAutomaticTasks": "off"}})
    return path

def open_workspace(home, item):
    code = shutil.which("code.cmd") or shutil.which("code")
    if not code:
        raise RuntimeError("VS Code CLI unavailable. Open the reported path manually.")
    subprocess.run([code, "--new-window", str(workspace_file(home, item))], check=True)

def initialize(home, repo, base, evidence, owner):
    home, repo = home.resolve(), repo.resolve()
    if home == repo or repo in home.parents:
        raise ValueError("Worktrees must be outside the original checkout.")
    sha(repo, base)
    if not evidence.strip():
        raise ValueError("Approved base evidence required.")
    with locked(home) as registry:
        if registry.exists():
            raise RuntimeError("Already initialized. Existing work is never overwritten.")
        d = {"schema_version": 1, "original_repo": str(repo), "common_dir": common(repo),
             "approved_base": {"commit": base, "evidence": evidence, "owner": owner, "verified_at": now()},
             "base_history": [], "categories": [], "tasks": [], "created_at": now(), "updated_at": now()}
        atomic(registry, d)
    return d

def categories(home, create=False):
    with locked(home) as registry:
        d = read(registry)
        if create:
            base = sha(d["original_repo"], d["approved_base"]["commit"])
            for category in CATEGORIES:
                old = next((x for x in d["categories"] if x["category"] == category), None)
                if old:
                    identity(d, old)
                    continue
                path = home / ("sports-cave-" + category.lower())
                branch = "codex/category/" + category.lower()
                exists = subprocess.run(["git", "-C", d["original_repo"], "show-ref", "--verify",
                                         "--quiet", "refs/heads/" + branch]).returncode == 0
                if path.exists() or exists:
                    raise RuntimeError("Unregistered existing folder/branch; ask the owner: " + str(path))
                item = {"id": "category-" + category.lower(), "category": category, "worktree_path": str(path),
                        "branch": branch, "base_commit": base, "status": "Planned",
                        "purpose": "Idle entry point; create a task before editing"}
                d["categories"].append(item)
                atomic(registry, d)  # Write-ahead reservation; crashes never authorize overwrites.
                git(d["original_repo"], "worktree", "add", "-b", branch, str(path), base)
                workspace_file(home, item)
        result = []
        for item in d["categories"]:
            path = identity(d, item)
            result.append({**item, "current_commit": git(path, "rev-parse", "HEAD"),
                           "occupied": bool(git(path, "status", "--porcelain")),
                           "stale_base": item["base_commit"] != d["approved_base"]["commit"]})
        return result

def create_task(home, name, category, owner, task_id=None):
    if not owner.strip() or not name.strip():
        raise ValueError("Task name and explicit session owner required")
    candidates = route(name, category)
    if len(candidates) != 1:
        return {"needs_confirmation": True, "candidates": candidates,
                "message": "Choose -Category; no workspace allocated."}
    category = candidates[0]
    if task_id and not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,70}", task_id):
        raise ValueError("Task ID requires 3-71 lowercase letters, digits or hyphens.")
    with locked(home) as registry:
        d = read(registry)
        if task_id and any(t["id"] == task_id for t in d["tasks"]):
            raise RuntimeError("Task ID exists. Use Open with the same owner.")
        if any(t["name"].casefold() == name.casefold() and t["status"] not in TERMINAL for t in d["tasks"]):
            raise RuntimeError("Unfinished task with this name exists. Reopen by ID.")
        base = sha(d["original_repo"], d["approved_base"]["commit"])
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:42] or "task"
        task_id = task_id or dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8]
        branch = "codex/task/" + category.lower() + "-" + slug + "-" + task_id
        path = home / ("sports-cave-" + category.lower() + "-" + slug + "-" + task_id)
        if path.exists():
            raise RuntimeError("Path exists; no files changed.")
        task = {"id": task_id, "name": name, "category": category, "worktree_path": str(path),
                "branch": branch, "base_commit": base, "current_commit": base, "owner": owner,
                "status": "Planned", "last_verified_test": None, "verification": None,
                "created_at": now(), "updated_at": now(), "integration_readiness": False,
                "lease": "owned", "history": [], "dependencies": [],
                "preview": {"enabled": False, "port": 8600 + len(d["tasks"]),
                    "runtime_path": str(home / ".studio" / "runtime" / task_id),
                    "reason": "Phase 2 integration isolation required"}}
        d["tasks"].append(task)
        atomic(registry, d)
        try:
            git(d["original_repo"], "worktree", "add", "-b", branch, str(path), base)
            task["status"] = "In Progress"
            workspace_file(home, task)
        except Exception as e:
            task["status"] = "Blocked"
            task["blocker"] = str(e)
            raise
        finally:
            task["updated_at"] = d["updated_at"] = now()
            atomic(registry, d)
        return task

def snapshot(repo):
    paths = set()
    for args in [("ls-files", "-z"), ("ls-files", "--others", "--exclude-standard", "-z")]:
        paths.update(git(repo, *args).split("\0"))
    digest = hashlib.sha256()
    for name in sorted(paths - {""}):
        p = Path(repo) / name
        digest.update(name.encode())
        if p.is_file():
            digest.update(hashlib.sha256(p.read_bytes()).digest())
        else:
            digest.update(b"directory" if p.is_dir() else b"missing")
    return {"commit": git(repo, "rev-parse", "HEAD"), "files_hash": digest.hexdigest(),
            "status": git(repo, "status", "--porcelain")}

def secret_findings(text):
    patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        r"\b(?:ghp_|github_pat_|shpat_|shpca_)[A-Za-z0-9_]{20,}", r"\bAKIA[0-9A-Z]{16}\b",
        r"(?i)(?:password|secret|api_key|access_token)\s*[:=]\s*['\"][A-Za-z0-9/+_-]{24,}['\"]"]
    return any(re.search(pattern, text) for pattern in patterns)

def verify(repo, base):
    import ast
    sha(repo, base)
    before = snapshot(repo)
    changed = set(git(repo, "diff", "--name-only", base).splitlines())
    changed.update(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    failures, checked = [], []
    for name in sorted(changed):
        p = Path(repo) / name
        if not p.is_file():
            continue
        if p.suffix == ".py":
            try:
                ast.parse(p.read_bytes(), filename=name)
                checked.append("syntax:" + name)
            except (SyntaxError, ValueError) as e:
                failures.append(str(e))
        if p.name in {".env", "secrets.toml"} or p.suffix in {".pem", ".key"}:
            failures.append("Sensitive filename: " + name)
        if p.stat().st_size < 5_000_000:
            content = p.read_bytes()
            if b"\0" not in content and secret_findings(content.decode("utf-8", errors="replace")):
                failures.append("Potential secret (value withheld): " + name)
    diff = subprocess.run(["git", "-C", str(repo), "diff", "--check", base], capture_output=True, text=True)
    if diff.returncode:
        failures.append(diff.stdout)
    check = Path(repo) / "scripts" / "studio" / "test_studio.py"
    if check.exists():
        env = {k: v for k, v in os.environ.items() if k.upper() in
               {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "COMSPEC", "PATHEXT", "USERPROFILE"}}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        p = subprocess.run([sys.executable, "-B", str(check)], cwd=repo, env=env, capture_output=True, text=True)
        checked.append("studio unit tests")
        if p.returncode:
            failures.append(p.stdout + p.stderr)
    after = snapshot(repo)
    if before != after:
        failures.append("Files changed during verification; rerun against a stable revision.")
    return {"passed": not failures, "checks": checked + ["changed-file secret patterns", "git diff --check"],
            "failures": failures, "verified_at": now(), "snapshot": after,
            "scope": "Infrastructure/static only; feature tests require RecordTests."}

def update_task(home, task_id, owner, action, status=None, evidence=None, result=None):
    with locked(home) as registry:
        d = read(registry)
        task = task_by_id(d, task_id, owner)
        repo = identity(d, task)
        current = snapshot(repo)
        if action == "verify":
            task["verification"] = verify(repo, task["base_commit"])
        elif action == "record-tests":
            if not evidence or result not in {"passed", "failed"}:
                raise ValueError("Supply result and focused command/result evidence.")
            task["last_verified_test"] = {"passed": result == "passed", "evidence": evidence,
                "snapshot": current, "verified_at": now(), "owner": owner}
        elif action == "status":
            if status not in STATES:
                raise ValueError("Unknown status")
            if status in {"Tested", "Ready for Review", "Approved", "Integrated", "Released"}:
                test = task["last_verified_test"]
                if not test or not test["passed"] or test["snapshot"] != current:
                    raise RuntimeError("Passing focused test evidence for current files/commit required.")
            if status in {"Ready for Review", "Approved", "Integrated", "Released"}:
                v = task["verification"]
                if current["status"] or not v or not v["passed"] or v["snapshot"] != current:
                    raise RuntimeError("Review requires a clean committed revision and current passing Verify.")
            if status in {"Approved", "Integrated", "Released"} and not evidence:
                raise RuntimeError("Explicit approval/integration/release evidence required; no action is performed.")
            task["status"] = status
            task["history"].append({"status": status, "at": now(), "owner": owner, "evidence": evidence})
        task["current_commit"] = current["commit"]
        v, t = task.get("verification"), task.get("last_verified_test")
        task["integration_readiness"] = bool(
            task["status"] in {"Ready for Review", "Approved"} and not current["status"] and
            v and v["passed"] and v["snapshot"] == current and t and t["passed"] and t["snapshot"] == current)
        task["updated_at"] = d["updated_at"] = now()
        atomic(registry, d)
        return task

def list_tasks(home):
    with locked(home) as registry:
        d, result = read(registry), []
        for task in d["tasks"]:
            item = dict(task)
            try:
                current = snapshot(identity(d, task))
                item["current_commit"], item["dirty"] = current["commit"], bool(current["status"])
                item["evidence_current"] = bool(task["verification"] and task["verification"]["snapshot"] == current)
                if not item["evidence_current"] or item["dirty"]:
                    item["integration_readiness"] = False
            except Exception as e:
                item["workspace_error"], item["integration_readiness"] = str(e), False
            item["occupied"] = True
            result.append(item)
        return result

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["route", "init", "categories", "new", "open", "list", "where",
                                      "verify", "record-tests", "status", "approve-base", "preview"])
    p.add_argument("--home", type=Path, default=DEFAULT_HOME)
    p.add_argument("--repo", type=Path, default=Path.cwd())
    p.add_argument("--description", default="")
    p.add_argument("--category", choices=list(CATEGORIES))
    p.add_argument("--owner")
    p.add_argument("--id")
    p.add_argument("--base")
    p.add_argument("--evidence")
    p.add_argument("--result", choices=["passed", "failed"])
    p.add_argument("--status", choices=STATES)
    p.add_argument("--open", action="store_true")
    p.add_argument("--create", action="store_true")
    a = p.parse_args(argv)
    a.home = a.home.resolve()
    if a.action in {"new", "open", "init", "verify", "record-tests", "status", "approve-base"} and not a.owner:
        p.error("--owner must identify the assigned task/session")
    if a.action == "route":
        candidates = route(a.description, a.category)
        out = {"candidates": candidates, "needs_confirmation": len(candidates) != 1}
    elif a.action == "init":
        out = initialize(a.home, a.repo, a.base, a.evidence or "", a.owner)
    elif a.action == "categories":
        out = categories(a.home, a.create)
    elif a.action == "new":
        out = create_task(a.home, a.description, a.category, a.owner, a.id)
        if a.open and not out.get("needs_confirmation"):
            open_workspace(a.home, out)
    elif a.action == "list":
        out = list_tasks(a.home)
    elif a.action == "where":
        out = {"path": git(a.repo, "rev-parse", "--show-toplevel"),
               "branch": git(a.repo, "branch", "--show-current"), "commit": git(a.repo, "rev-parse", "HEAD")}
    elif a.action == "preview":
        raise RuntimeError("Preview disabled: Phase 2 must isolate data, credentials and provider transports.")
    elif a.action == "open":
        with locked(a.home) as registry:
            d = read(registry)
            out = task_by_id(d, a.id, a.owner)
            identity(d, out)
        if a.open:
            open_workspace(a.home, out)
        out = {**out, "codex_command": 'codex --cd "' + out["worktree_path"] + '"'}
    elif a.action == "approve-base":
        if not a.evidence:
            raise ValueError("Explicit owner approval and combined test evidence required.")
        with locked(a.home) as registry:
            d = read(registry)
            revision = sha(d["original_repo"], a.base)
            if not git(d["original_repo"], "ls-tree", revision, "scripts/studio/studio.py"):
                raise RuntimeError("Base lacks studio tooling; integrate infrastructure first.")
            d["base_history"].append(d["approved_base"])
            d["approved_base"] = {"commit": revision, "evidence": a.evidence, "owner": a.owner, "verified_at": now()}
            d["updated_at"] = now()
            atomic(registry, d)
            out = d["approved_base"]
    else:
        out = update_task(a.home, a.id, a.owner, a.action, a.status, a.evidence, a.result)
    print(json.dumps(out, indent=2))
    return 1 if a.action == "verify" and not out["verification"]["passed"] else 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        print("Studio: " + str(exc), file=sys.stderr)
        sys.exit(1)
