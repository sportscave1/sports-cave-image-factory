"""Format-aware composition seam for the existing helper catalogue.

No HTTP server, auth, relay or database. The shared DeviceAgent/OS wiring must
adopt this adapter after the registered ownership handoff.
"""
from copy import deepcopy
import json
from .contract import FORMAT, Invalid, requirements

SUMMARY_FIELDS = {"format", "format_version", "capabilities", "playback_available"}


class Catalogue:
    def __init__(self, repository, legacy_store, *, playback_available=False):
        self.repository, self.legacy = repository, legacy_store
        self.cache = {}
        self.playback_available = playback_available

    def summaries(self):
        """Stat-sized cache; full definitions are read only when changed."""
        rows, live = [], set()
        for path, metadata in self.repository.visible():
            live.add(path.stem)
            stat = path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            cached = self.cache.get(path.stem)
            if cached is None or cached[0] != stamp:
                task = self.repository.get(path.stem)
                playable = self.playback_available and bool(task["actions"]) and all(a["version"] == 2 for a in task["actions"])
                row = dict(id=task["id"], name=task["name"], format=FORMAT,
                           format_version=1, capabilities=sorted(requirements(task)),
                           playback_available=playable, inputs=[], steps=len(task["actions"]),
                           revision=self.repository.revision(task), duration_ms=None,
                           updated_at=stat.st_mtime * 1000, result="Desktop · Prepared window" if playable else "Desktop · Playback unavailable")
                self.cache[path.stem] = stamp, row
            row = deepcopy(self.cache[path.stem][1])
            row["name"] = metadata.get("name", row["name"])
            row["updated_at"] = metadata.get("updated_at", row["updated_at"])
            rows.append(row)
        self.cache = {key: value for key, value in self.cache.items() if key in live}
        # Legacy rows retain their original schema and revision.
        return sorted(deepcopy(self.legacy.list()) + rows,
                      key=lambda row: (row["name"].casefold(), row["id"]))

    def is_desktop(self, task_id):
        from uuid import UUID
        try:
            if str(UUID(task_id)) != task_id:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Invalid("Select a valid task.") from None
        return (self.repository.root / (task_id + ".json")).exists()

    def inspect(self, task_id, helper_capabilities):
        if not self.is_desktop(task_id):
            task = self.legacy.get(task_id)
            return {"task": task, "revision": self.legacy.revision(task)}
        if not isinstance(helper_capabilities, dict) or helper_capabilities.get("format") != FORMAT or helper_capabilities.get("version") != 1:
            raise Invalid("Update the helper for desktop recording format version 1.")
        task = self.repository.get(task_id)
        return {"task": task, "revision": self.repository.revision(task),
                "playback_available": False, "capabilities": sorted(requirements(task))}

    def guard_command(self, kind, task_id):
        """Call before the legacy agent ever loads a selected task."""
        if self.is_desktop(task_id) and kind != "inspect":
            if kind == "play":
                raise Invalid("Desktop Play requires the native executor and scoped targets.")
            raise Invalid("Desktop tasks are immutable. This browser editing command is not supported.")
