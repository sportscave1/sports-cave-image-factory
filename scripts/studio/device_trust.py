"""Windows user-scoped, expiring device trust. No credentials leave localhost."""
import ctypes
import hashlib
import hmac
import json
import os
import secrets
import time
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlsplit
import studio

SESSION_SECONDS = 300
TRUST_SECONDS = 30 * 86400

class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]

def protect(data, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Persistent trust requires Windows user-scoped DPAPI.")
    buf = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte)))
    out = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    fn = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    fn.restype = wintypes.BOOL
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(out)):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(out.data, out.size)
    finally:
        kernel.LocalFree(out.data)

def exact_origin(value):
    if not isinstance(value, str) or len(value) > 256:
        raise ValueError("Exact OS origin required.")
    u = urlsplit(value)
    if (u.scheme != "https" and not (u.scheme == "http" and u.hostname in {"localhost", "127.0.0.1"})) or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError("Exact HTTPS OS origin required.")
    return value

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

class Trust:
    def __init__(self, home, task, owner, clock=time.time):
        self.home, self.task, self.owner, self.clock = Path(home), task, owner, clock
        self.path = self.home / ".studio" / "devices" / (digest(task + owner) + ".json")
        self.sessions = {}

    def read(self):
        if not self.path.exists():
            return None
        obj = json.loads(protect(bytes.fromhex(json.loads(self.path.read_text())["protected"]), True))
        if obj["task"] != self.task or obj["owner"] != self.owner:
            raise ValueError("Device ownership mismatch.")
        # Preserve existing single-browser V5 enrollments without broadening origins.
        if "records" not in obj:
            obj = {"task": self.task, "owner": self.owner, "records": {"legacy": obj}}
        return obj

    def write(self, obj):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        studio.atomic(self.path, {"protected": protect(json.dumps(obj).encode()).hex()})

    def audit(self, event, origin):
        # No tokens, paths, source or provider data in audit records.
        path = self.path.with_suffix(".audit.json")
        events = json.loads(path.read_text()) if path.exists() else []
        events.append({"event": event, "origin": origin, "task": self.task, "at": self.clock()})
        studio.atomic(path, events[-200:])

    def issue(self, record):
        now = self.clock()
        self.sessions = {k:v for k,v in self.sessions.items() if v["expires"] > now}
        token = secrets.token_urlsafe(32)
        self.sessions[token] = {"expires": now + SESSION_SECONDS, "generation": record["generation"]}
        return token

    def enroll(self, origin, previous=""):
        origin = exact_origin(origin)
        store = self.read() or {"task": self.task, "owner": self.owner, "records": {}}
        now = self.clock()
        records = {k:v for k,v in store["records"].items() if v["expires"] > now}
        old_id, old_secret = self.split(previous)
        old = records.get(old_id)
        if old and old["origin"] == origin and hmac.compare_digest(old["hash"], digest(old_secret)):
            del records[old_id]
        if len(records) >= 16:
            raise ValueError("Device enrollment limit reached. Revoke this computer locally first.")
        identity = secrets.token_hex(16)
        secret = secrets.token_urlsafe(32)
        record = {"origin": origin, "task": self.task, "owner": self.owner, "expires": now+TRUST_SECONDS,
                  "hash": digest(secret), "generation": secrets.token_hex(16)}
        records[identity] = record
        store["records"] = records
        self.write(store)
        self.audit("trust", origin)
        return identity + "." + secret, self.issue(record)

    @staticmethod
    def split(cookie):
        if "." in cookie:
            return cookie.split(".", 1)
        return "legacy", cookie

    def renew(self, secret, origin):
        store = self.read()
        identity, value = self.split(secret)
        record = store["records"].get(identity) if store else None
        if not record or record["origin"] != exact_origin(origin) or record["expires"] <= self.clock() or not hmac.compare_digest(record["hash"], digest(value)):
            raise ValueError("Trust expired or revoked. Approve this computer locally again.")
        replacement = secrets.token_urlsafe(32)
        record["hash"] = digest(replacement)
        self.write(store)
        return identity + "." + replacement, self.issue(record)

    def valid(self, token):
        item = self.sessions.get(token)
        if not item or item["expires"] <= self.clock():
            return False
        store = self.read()
        return bool(store and any(record["expires"] > self.clock() and record["generation"] == item["generation"]
                                  for record in store["records"].values()))

    def revoke(self):
        store = self.read()
        self.sessions.clear()
        if store:
            for record in store["records"].values():
                record["expires"] = 0
                self.audit("revoke", record["origin"])
            self.write(store)
