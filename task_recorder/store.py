"""Atomic local storage. Run journal contains IDs/status only, never page data."""
import json
import os
import uuid
import hashlib
import contextlib
from datetime import datetime, timezone
from pathlib import Path
from .schema import Invalid, validate_task
from .attention import issues

def now():
    return datetime.now(timezone.utc).isoformat()

def atomic(path, obj):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)

class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.tasks = self.root / "tasks"
        self.tasks.mkdir(parents=True, exist_ok=True)
        self.journal = self.root / "run.json"
        self._summaries = {}
        if self.journal.exists():
            run = json.loads(self.journal.read_text(encoding="utf-8"))
            if run.get("status") in {"running", "paused", "executing"}:
                run.update(status="interrupted", at=now(), message="Runner stopped. Nothing was automatically replayed.")
                atomic(self.journal, run)
                try:
                    task_id = str(uuid.UUID(run["task_id"]))
                    atomic(self.tasks / (task_id + ".result"), run)
                except (ValueError, KeyError):
                    pass

    def save(self, raw):
        task = validate_task(raw)
        task.setdefault("id", str(uuid.uuid4()))
        if (self.tasks / (task["id"] + ".deleted")).exists():
            raise Invalid("This recording was deleted. Create a new recording.")
        atomic(self.tasks / (task["id"] + ".json"), task)
        self.metadata(task["id"], updated_at=now())
        return task

    @staticmethod
    def revision(task):
        return hashlib.sha256(json.dumps(task, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def checkpoint(self, task, active=True):
        atomic(self.root / "recording.json", {"task": validate_task(task), "active": active})

    def get(self, task_id):
        try:
            task_id = str(uuid.UUID(task_id))
            if (self.tasks / (task_id + ".deleted")).exists(): raise ValueError()
            return validate_task(json.loads((self.tasks / (task_id + ".json")).read_text(encoding="utf-8")))
        except (ValueError, OSError, TypeError):
            raise Invalid("Saved task not found or invalid.")

    def metadata(self, task_id, **updates):
        task_id = str(uuid.UUID(task_id))
        path = self.tasks / (task_id + ".meta")
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if updates:
            data.update(updates)
            atomic(path, data)
        return data

    def delete(self, task_id):
        task = self.get(task_id)  # Validated UUID and existing saved task only.
        tombstone = self.tasks / (task["id"] + ".deleted")
        atomic(tombstone, {"deleted_at": now()})
        # The tombstone commits deletion before cleanup; interrupted cleanup cannot
        # resurrect a recording. Nothing outside this task's own files is removed.
        for suffix in (".json", ".meta", ".result"):
            with contextlib.suppress(OSError):
                (self.tasks / (task["id"] + suffix)).unlink(missing_ok=True)
        checkpoint = self.root / "recording.json"
        if checkpoint.exists():
            record = json.loads(checkpoint.read_text(encoding="utf-8"))
            if record.get("task", {}).get("id") == task["id"]:
                with contextlib.suppress(OSError):checkpoint.unlink()
        if self.journal.exists():
            run = json.loads(self.journal.read_text(encoding="utf-8"))
            if run.get("task_id") == task["id"]:
                with contextlib.suppress(OSError):self.journal.unlink()
        self._summaries.pop(task["id"], None)

    def list(self):
        result = []
        for p in self.tasks.glob("*.json"):
            if p.with_suffix(".deleted").exists():
                continue
            try:
                paths = (p, p.with_suffix(".meta"), p.with_suffix(".result"))
                stamp = tuple((v.stat().st_mtime_ns, v.stat().st_size) if v.exists() else None for v in paths)
                cached = self._summaries.get(p.stem)
                if cached and cached[0] == stamp:
                    result.append(cached[1]); continue
                task = self.get(p.stem)
                meta = self.metadata(task["id"])
                history = json.loads(paths[2].read_text(encoding="utf-8")) if paths[2].exists() else {}
                problems=issues(task)
                row = {"attention":problems[:3],"issue_count":len(problems),"id": task["id"], "name": task["name"], "last_run": history.get("at"),
                       "result": history.get("status", "Never run"), "revision": self.revision(task),
                       "inputs": task["inputs"], "steps": len(task["steps"]),
                       "duration_ms": meta.get("duration_ms"), "updated_at": meta.get("updated_at")}
                self._summaries[p.stem] = (stamp, row)
                result.append(row)
            except (ValueError, OSError):
                continue
        return sorted(result, key=lambda x: (x["name"].lower(), x["id"]))

    def result(self, task_id, status, index, message):
        run = {"task_id": task_id, "status": status, "step": index, "message": message, "at": now()}
        run.update(getattr(self, "run_context", {}))
        atomic(self.journal, run)
        atomic(self.tasks / (task_id + ".result"), run)
