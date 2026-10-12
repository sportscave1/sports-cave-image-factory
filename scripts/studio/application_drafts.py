"""Application copies backed by existing registered, owner-scoped worktrees.

No production writes, task migration, arbitrary paths, source execution or publish.
Live receipts are installed by the local administrator, never by the OS browser.
"""
import argparse
import ast
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import uuid

import drafts
import studio

SERVICE = "srv-d8kl4on7f7vs73dvavv0"
REPOSITORY = "https://github.com/sportscave1/sports-cave-image-factory.git"
DEFAULT_NAME = "Sports Cave OS copy"


def live_path(home):
    return drafts.plain_path(Path(home) / ".studio" / "verified-live.json")


def record_live(home, github_revision, deployment, *, evidence):
    """Local administrator attestation from an authenticated Render live response."""
    sha = deployment.get("commit", {}).get("id")
    if (deployment.get("status") != "live" or sha != github_revision
            or not deployment.get("id") or not evidence):
        raise ValueError("GitHub main and the running Render deployment must match.")
    import releases
    releases.revision(sha)
    with studio.locked(home) as file:
        registry = studio.read(file)
        repo = registry["original_repo"]
        if studio.git(repo, "remote", "get-url", "origin") != REPOSITORY:
            raise ValueError("Unexpected source repository.")
        if remote_main(repo) != sha or studio.sha(repo, sha) != sha:
            raise ValueError("GitHub main changed or the exact source is unavailable.")
        receipt = {"service_id": SERVICE, "repository": REPOSITORY, "revision": sha,
                   "deployment_id": deployment["id"], "status": "live",
                   "verified_at": studio.now(), "evidence": evidence,
                   "verification": "local-administrator-provider-attestation"}
        studio.atomic(live_path(home), receipt)
        return receipt


def remote_main(repo):
    response = subprocess.run(["git", "-C", str(repo), "-c", "credential.interactive=never",
                               "ls-remote", "origin", "refs/heads/main"],
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
    if response.returncode:
        raise ValueError("GitHub main could not be verified. No copy was created.")
    result = response.stdout.split()
    if len(result) != 2 or result[1] != "refs/heads/main":
        raise ValueError("GitHub main could not be verified.")
    return result[0]


def verified_live(home, registry, fresh=False):
    path = live_path(home)
    if not path.exists():
        raise ValueError("Verify GitHub main and the running production revision locally before creating a copy.")
    receipt = json.loads(path.read_text(encoding="utf-8"))
    import releases
    sha = releases.revision(receipt.get("revision"))
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(receipt["verified_at"])).total_seconds()
    if (receipt.get("service_id") != SERVICE or receipt.get("repository") != REPOSITORY
            or receipt.get("status") != "live" or not receipt.get("deployment_id")
            or not receipt.get("evidence") or not 0 <= age <= 3600):
        raise ValueError("Production verification is missing or older than one hour. Verify Live again locally.")
    if studio.sha(registry["original_repo"], sha) != sha:
        raise ValueError("Verified production source is unavailable locally.")
    if fresh and remote_main(registry["original_repo"]) != sha:
        raise ValueError("GitHub main changed since production verification. Verify Live again.")
    return receipt


def assigned(registry, draft_id, owner):
    draft, task, root = drafts.draft_by_id(registry, draft_id, owner)
    if draft.get("kind") != "application" or draft.get("archived_at"):
        raise ValueError("Select an active OS application draft.")
    return draft, task, root


def name_for(registry, owner, name=None):
    previous = [d for d in registry.get("drafts", []) if d.get("kind") == "application" and d["owner"] == owner]
    used = {d["name"].casefold() for d in registry.get("drafts", [])
            if d.get("kind") == "application" and d["owner"] == owner and not d.get("archived_at")}
    if name is None or name == "":
        number = len(previous) + 1
        name = DEFAULT_NAME if number == 1 else DEFAULT_NAME + " " + str(number)
        while name.casefold() in used:
            number += 1
            name = DEFAULT_NAME + " " + str(number)
    if not isinstance(name, str) or not name.strip() or len(name) > 100 or any(ord(c) < 32 for c in name):
        raise ValueError("Use a name with 1–100 printable characters.")
    name = name.strip()
    if name.casefold() in used:
        raise ValueError("An active application draft already uses that name.")
    return name


def changed_source(root):
    names = set(studio.git(root, "diff", "HEAD", "--name-only", "-z").split("\0"))
    names.update(studio.git(root, "ls-files", "--others", "--exclude-standard", "-z").split("\0"))
    names.discard("")
    if len(names) > 100:
        raise ValueError("More than 100 changed files; use a separately reviewed integration.")
    captured = {}
    for name in sorted(names):
        meta, data = drafts.read_source(root, name, allow_missing=True)
        captured[name] = data
    if sum(len(data or b"") for data in captured.values()) > drafts.MAX_TOTAL:
        raise ValueError("Changed source exceeds the safe copy limit.")
    return captured


def create(home, task_id, owner, name=None, *, default=False, source_id=None, expected=None):
    """Create exactly one registered copy; failed reservations are retained for recovery."""
    with studio.locked(home) as file:
        registry = studio.read(file)
        drafts.assigned(registry, task_id, owner)
        existing = [d for d in registry.get("drafts", []) if d.get("kind") == "application" and d["owner"] == owner]
        if default and existing:
            return next((d for d in existing if not d.get("archived_at")), existing[0])
        if any(t.get("kind") == "application" and t["owner"] == owner and t.get("status") == "Blocked"
               for t in registry["tasks"]):
            raise ValueError("An application worktree reservation needs local recovery. No additional copy was created.")
        copied, source, snapshot = {}, None, None
        if source_id:
            source, _, source_root = assigned(registry, source_id, owner)
            snapshot = studio.snapshot(source_root)
            if expected != fingerprint(source, snapshot):
                raise ValueError("Source draft changed. Review the copy again.")
            copied = changed_source(source_root)
            base = snapshot["commit"]
            receipt = source["production_base"]
        else:
            receipt = verified_live(home, registry, fresh=True)
            base = receipt["revision"]
        name = name_for(registry, owner, name)
        draft_id = str(uuid.uuid4())
        internal_id = "app-" + draft_id
        branch = "codex/application/" + draft_id
        root = drafts.plain_path(Path(home) / ("sports-cave-app-" + draft_id))
        if root.exists():
            raise ValueError("Reserved application path already exists.")
        task = {"id": internal_id, "kind": "application", "name": "OS application " + draft_id,
                "category": "CORE", "owner": owner, "worktree_path": str(root),
                "branch": branch, "base_commit": base, "current_commit": base,
                "status": "Planned", "created_at": studio.now(), "updated_at": studio.now(),
                "integration_readiness": False, "last_verified_test": None, "verification": None,
                "history": [], "dependencies": [], "lease": "owned",
                "preview": {"enabled": True, "runtime_path": str(Path(home)/".studio"/"runtime"/internal_id)}}
        registry["tasks"].append(task)
        studio.atomic(file, registry)
        try:
            studio.git(registry["original_repo"], "-c", "core.longpaths=true", "-c", "core.hooksPath=NUL", "worktree", "add", "-b", branch, str(root), base)
            if source and studio.snapshot(source_root) != snapshot:
                raise ValueError("Source changed during duplication; copy kept blocked for recovery.")
            for relative, data in copied.items():
                target = drafts.safe_file(root, relative)
                if data is None:
                    if target.exists():
                        target.unlink()
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            if source and studio.snapshot(source_root) != snapshot:
                raise ValueError("Source changed during duplication; copy kept blocked for recovery.")
            draft = {"id": draft_id, "kind": "application", "name": name, "task_id": internal_id,
                     "category": "CORE", "owner": owner, "branch": branch, "worktree_path": str(root),
                     "base_commit": receipt["revision"], "production_base": copy.deepcopy(receipt),
                     "current_commit": base, "created_at": studio.now(), "updated_at": studio.now(),
                     "revision": 0, "revisions": [], "metadata_version": 1,
                     "editing_status": "Copied source" if copied else "Saved",
                     "preview": {"enabled": True, "status": "Not run"}, "release_eligible": False,
                     "release_readiness": "Preview, tests and exact-revision approval required",
                     "history": [{"event": "duplicated" if source else "created", "at": studio.now(),
                                  "source_id": source_id, "base": base, "source_snapshot": snapshot}]}
            registry.setdefault("drafts", []).append(draft)
            task["status"] = "In Progress"
            return draft
        except Exception as exc:
            task["status"] = "Blocked"
            task["blocker"] = str(exc)
            raise
        finally:
            registry["updated_at"] = task["updated_at"] = studio.now()
            studio.atomic(file, registry)


def fingerprint(draft, snapshot):
    body = {"id": draft["id"], "version": draft.get("metadata_version", 1),
            "revision": draft["revision"], "snapshot": snapshot}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()


def review(home, draft_id, owner):
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, _, root = assigned(registry, draft_id, owner)
        snapshot = studio.snapshot(root)
        return {"id": draft_id, "name": draft["name"], "fingerprint": fingerprint(draft, snapshot),
                "revision": draft["revision"], "metadata_version": draft.get("metadata_version", 1),
                "source_revision": snapshot["commit"], "has_unfinished_changes": bool(snapshot["status"]),
                "has_commits_beyond_live_base": snapshot["commit"] != draft["base_commit"],
                "changes": snapshot["status"], "production_base": draft["production_base"],
                "release_readiness": "Publishing disabled; exact-revision review required"}


def rename_or_archive(home, draft_id, owner, operation, expected, *, name=None, confirmation=None):
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, _, root = assigned(registry, draft_id, owner)
        snapshot = studio.snapshot(root)
        if fingerprint(draft, snapshot) != expected:
            raise ValueError("Draft changed since review. Refresh and review again.")
        if operation == "rename":
            if not isinstance(name, str) or not name.strip():
                raise ValueError("A draft display name cannot be empty.")
            if name == draft["name"]:
                return draft
            draft["name"] = name_for(registry, owner, name)
        elif operation == "archive":
            if confirmation != "ARCHIVE " + draft["name"]:
                raise ValueError("Review unfinished changes and confirm ARCHIVE followed by the exact name.")
            draft["archived_at"] = studio.now()
        else:
            raise ValueError("Unsupported draft operation.")
        draft["metadata_version"] = draft.get("metadata_version", 1) + 1
        draft["updated_at"] = registry["updated_at"] = studio.now()
        draft.setdefault("history", []).append({"event": operation, "at": studio.now(),
                                                 "snapshot": snapshot, "name": draft["name"]})
        studio.atomic(file, registry)
        return {"id": draft_id, "name": draft["name"], "archived": bool(draft.get("archived_at")),
                "worktree_preserved": True}


def check(home, draft_id, owner):
    """Bounded static checks only; never execute selected draft code on the host."""
    import editor
    import page_catalog
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, task, root = assigned(registry, draft_id, owner)
        before = studio.snapshot(root)
        failures = []
        paths = {"app.py"} | set(changed_source(root))
        for name in paths:
            _, data = drafts.read_source(root, name, allow_missing=True)
            if data is not None and name.endswith(".py"):
                try:
                    ast.parse(data, filename=name)
                except SyntaxError as exc:
                    failures.append(str(exc))
        try:
            pages = page_catalog.pages(root)
            editor.visual_values((root / "app.py").read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            failures.append(str(exc))
            pages = []
        if studio.snapshot(root) != before:
            raise ValueError("Source changed during tests; result discarded.")
        result = {"passed": not failures, "verified_at": studio.now(), "snapshot": before,
                  "failures": failures, "page_count": len(pages),
                  "evidence": "Source syntax, credential/path policy, OS catalog and component mappings. Docker runtime acceptance is separate.",
                  "scope": "static-only"}
        draft["test"] = result
        draft["release_eligible"] = False
        studio.atomic(file, registry)
        return result


def update_plan(home, draft_id, owner):
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, _, root = assigned(registry, draft_id, owner)
        receipt = verified_live(home, registry, fresh=True)
        snapshot = studio.snapshot(root)
        import releases
        git = releases.GitObjects(root)
        conflicts = []
        conflicting_files = []
        if snapshot["status"]:
            conflicts.append("Save/review uncommitted source before integrating Live. Nothing was changed.")
        if not git.ancestor(snapshot["commit"], receipt["revision"]):
            conflicts.append("Draft and Live diverged. A separately reviewed integration is required.")
            baseline, ours, live = (git.tree(sha) for sha in
                                    (draft["base_commit"], snapshot["commit"], receipt["revision"]))
            conflicting_files = sorted(name for name in set(baseline)|set(ours)|set(live)
                                       if ours.get(name) != baseline.get(name)
                                       and live.get(name) != baseline.get(name)
                                       and ours.get(name) != live.get(name))
        return {"draft": draft_id, "fingerprint": fingerprint(draft, snapshot),
                "from_revision": snapshot["commit"], "to_revision": receipt["revision"],
                "conflicts": conflicts, "already_current": snapshot["commit"] == receipt["revision"],
                "conflicting_files": conflicting_files, "unfinished_files": snapshot["status"].splitlines(),
                "confirmation": "UPDATE " + receipt["revision"],
                "notice": "Only a clean fast-forward is supported. Recovery branch is retained; no reset or auto-merge."}


def update_from_live(home, draft_id, owner, expected, confirmation):
    # Called only after explicit local confirmation of the reviewed exact revision.
    with studio.locked(home) as file:
        registry = studio.read(file)
        draft, task, root = assigned(registry, draft_id, owner)
        receipt = verified_live(home, registry, fresh=True)
        snapshot = studio.snapshot(root)
        if expected != fingerprint(draft, snapshot) or snapshot["status"]:
            raise ValueError("Draft changed or has unfinished source; update refused.")
        import releases
        if confirmation != "UPDATE " + receipt["revision"]:
            raise ValueError("Confirm the exact Live revision locally.")
        if not releases.GitObjects(root).ancestor(snapshot["commit"], receipt["revision"]):
            raise ValueError("Integration conflict/divergence. Use a separately reviewed integration.")
        if snapshot["commit"] == receipt["revision"]:
            return {"unchanged": True}
        recovery = "codex/recovery/" + draft_id + "-" + uuid.uuid4().hex[:8]
        studio.git(root, "branch", recovery, snapshot["commit"])
        studio.git(root, "-c", "core.hooksPath=NUL", "merge", "--ff-only", "--no-edit", receipt["revision"])
        # A revision is a real checkpoint, not just a stale-edit counter. Preserve
        # prior selections at the new source revision so state/open/recovery work.
        checkpoint = live_checkpoint(home, draft, root, receipt["revision"])
        draft["base_commit"] = draft["current_commit"] = task["current_commit"] = receipt["revision"]
        draft["production_base"] = receipt
        draft["revisions"].append(checkpoint)
        draft["revision"] = checkpoint["number"]
        draft["editing_status"] = "Saved locally"
        draft["metadata_version"] = draft.get("metadata_version", 1) + 1
        draft["updated_at"] = studio.now()
        draft["release_eligible"] = False
        draft["test"] = None
        draft.setdefault("history", []).append({"event": "updated_from_live", "at": studio.now(),
                                                "from": snapshot["commit"], "to": receipt["revision"],
                                                "recovery_branch": recovery})
        studio.atomic(file, registry)
        return {"updated": True, "revision": receipt["revision"], "recovery_branch": recovery}


def live_checkpoint(home, draft, root, revision):
    import editor
    previous = draft["revisions"][-1]["files"] if draft["revisions"] else []
    names = sorted({"app.py"} | {item["path"] for item in previous})
    captured = [drafts.read_source(root, name, allow_missing=True) for name in names]
    if sum(len(data or b"") for _, data in captured) > drafts.MAX_TOTAL:
        raise ValueError("Updated checkpoint exceeds the safe size limit.")
    for meta, data in captured:
        if drafts.read_source(root, meta["path"], allow_missing=True) != (meta, data):
            raise ValueError("Source changed while checkpointing Live. Recovery branch retained.")
        if data is not None:
            editor.blob(home, data)
    return {"number": draft["revision"] + 1, "commit": revision, "saved_at": studio.now(),
            "files": [meta for meta, _ in captured],
            "scope": "explicit selected files after verified Live update"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--task", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--record-live", type=Path, help="Authenticated Render deployment JSON, reviewed locally")
    parser.add_argument("--github-main")
    parser.add_argument("--evidence")
    parser.add_argument("--configure", action="store_true")
    args = parser.parse_args()
    if args.record_live:
        result = record_live(args.home, args.github_main,
                             json.loads(args.record_live.read_text(encoding="utf-8")), evidence=args.evidence)
    elif args.configure:
        result = create(args.home, args.task, args.owner, default=True)
    else:
        parser.error("Choose --record-live or --configure")
    print(json.dumps(result, indent=2))
