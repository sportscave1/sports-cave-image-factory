"""Bounded, session-owned display caches. No disk, database, sockets or credentials."""
from collections import OrderedDict
import json

BODY_LIMIT = 75
BODY_BYTES = 64 * 1024 * 1024
THREAD_LIMIT = 75
THREAD_BYTES = 8 * 1024 * 1024


class DisplayLRU:
    """Entry count and serialized data-byte budget; Python container overhead is additional."""
    def __init__(self, state, name, *, limit, byte_limit):
        self.data = state.setdefault(name, {"entries": OrderedDict(), "bytes": 0})
        self.limit, self.byte_limit = limit, byte_limit

    def get(self, key):
        entry = self.data["entries"].get(key)
        if entry is None:
            return None
        self.data["entries"].move_to_end(key)
        return entry["value"]

    def put(self, key, value):
        size = len(json.dumps(value, default=str, ensure_ascii=False).encode("utf-8"))
        self.remove(key)
        if size > self.byte_limit:
            return False
        self.data["entries"][key] = {"value": value, "size": size}
        self.data["bytes"] += size
        while len(self.data["entries"]) > self.limit or self.data["bytes"] > self.byte_limit:
            _, old = self.data["entries"].popitem(last=False)
            self.data["bytes"] -= old["size"]
        return True

    def remove(self, key):
        old = self.data["entries"].pop(key, None)
        if old:
            self.data["bytes"] -= old["size"]

    def clear(self):
        self.data["entries"].clear()
        self.data["bytes"] = 0

    def remove_where(self, predicate):
        for key in list(self.data["entries"]):
            if predicate(key):
                self.remove(key)


def ordered_folders(folders, roles):
    """Presentation order only; never infer or change the provider's folder mapping."""
    priorities = {role: i for i, role in enumerate(("inbox", "flagged", "drafts", "sent", "archive", "junk", "trash"))}
    by_name = {name: role for role, name in roles.items()}

    def key(folder):
        role = "inbox" if folder["name"].casefold() == "inbox" else by_name.get(folder["name"], folder.get("role"))
        return (priorities.get(role, 7), folder["label"].casefold(), folder["name"])

    return sorted(folders, key=key)
