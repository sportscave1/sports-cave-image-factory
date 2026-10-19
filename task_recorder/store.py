"""Atomic local storage. Run journal contains IDs/status only, never page data."""
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .schema import Invalid, validate_task

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
        atomic(self.tasks / (task["id"] + ".json"), task)
        return task

    def get(self, task_id):
        try:
            task_id = str(uuid.UUID(task_id))
            return validate_task(json.loads((self.tasks / (task_id + ".json")).read_text(encoding="utf-8")))
        except (ValueError, OSError, TypeError):
            raise Invalid("Saved task not found or invalid.")

    def list(self):
        result = []
        for p in self.tasks.glob("*.json"):
            try:
                task = validate_task(json.loads(p.read_text(encoding="utf-8")))
                history_path = self.tasks / (task["id"] + ".result")
                history = json.loads(history_path.read_text(encoding="utf-8")) if history_path.exists() else {}
                result.append({"id": task["id"], "name": task["name"], "last_run": history.get("at"),
                               "result": history.get("status", "Never run")})
            except (ValueError, OSError):
                continue
        return sorted(result, key=lambda x: x["name"].lower())

    def result(self, task_id, status, index, message):
        run = {"task_id": task_id, "status": status, "step": index, "message": message, "at": now()}
        atomic(self.journal, run)
        atomic(self.tasks / (task_id + ".result"), run)

