"""Strict data-only workflow format; no scripts, shell, CSS or XPath execution."""
import copy
import re
import uuid
from urllib.parse import urlsplit

ACTIONS = {"navigate", "wait_url", "click", "fill", "select", "check", "upload", "wait", "unsupported"}
LOCATORS = {"role", "label", "test_id", "id", "placeholder", "text"}
ROLES = {"button", "link", "textbox", "checkbox", "radio", "combobox", "option", "heading", "tab", "menuitem"}
PRIVATE = re.compile(r"password|passwd|secret|token|authorization|session|credential|one.?time|verification.?code|otp|csrf|api.?key", re.I)
TOKEN = re.compile(r"Bearer\s+\S+|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+|(?:sk-|ghp_|xoxb-)[A-Za-z0-9_-]{10,}|[A-Za-z0-9_+/=-]{64,}", re.I)
INPUT_NAME = re.compile(r"[a-z][a-z0-9_]{0,39}\Z")

class Invalid(ValueError):
    pass

def text(value, limit=2000, empty=False):
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise Invalid("Expected bounded text.")
    if TOKEN.search(value):
        raise Invalid("Credential-like content is not allowed.")
    return value

def safe_url(value):
    text(value)
    try:
        u = urlsplit(value)
        if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise Invalid("Use an HTTP(S) URL without credentials, query parameters or fragments in V1.")
        if PRIVATE.search(u.path):
            raise Invalid("Authentication/session URLs cannot be recorded.")
        _ = u.port
    except ValueError:
        raise Invalid("Use a valid HTTP(S) URL without credentials, query parameters or fragments.")
    return value

def keys(obj, allowed, required=()):
    if not isinstance(obj, dict) or set(obj) - set(allowed) or set(required) - set(obj):
        raise Invalid("Unknown or missing fields in workflow.")

def validate_locator(loc):
    keys(loc, {"by", "value", "role"}, {"by", "value"})
    if loc["by"] not in LOCATORS:
        raise Invalid("Unsupported locator type.")
    text(loc["value"], 180)
    if PRIVATE.search(loc["value"]):
        raise Invalid("Sensitive field locators cannot be saved.")
    if loc["by"] == "role":
        if loc.get("role") not in ROLES:
            raise Invalid("Unsupported role.")
    elif "role" in loc:
        raise Invalid("Role only applies to role locators.")
    return loc

def validate_task(raw):
    obj = copy.deepcopy(raw)
    keys(obj, {"version", "id", "name", "inputs", "steps"}, {"version", "name", "inputs", "steps"})
    if obj["version"] != 1:
        raise Invalid("Unsupported workflow version.")
    if "id" in obj:
        try:
            if str(uuid.UUID(obj["id"])) != obj["id"]: raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Invalid("Invalid task ID.")
    text(obj["name"], 100)
    if not isinstance(obj["inputs"], list) or len(obj["inputs"]) > 50:
        raise Invalid("At most 50 inputs.")
    names = set()
    for item in obj["inputs"]:
        keys(item, {"name", "required"}, {"name", "required"})
        name = item["name"]
        if not isinstance(name, str) or not INPUT_NAME.fullmatch(name) or PRIVATE.search(name) or name in names:
            raise Invalid("Inputs need unique, non-sensitive names (lowercase letters, numbers, underscore).")
        if not isinstance(item["required"], bool): raise Invalid("Required must be true or false.")
        names.add(name)
    if not isinstance(obj["steps"], list) or len(obj["steps"]) > 500:
        raise Invalid("At most 500 steps.")
    for step in obj["steps"]:
        keys(step, {"action", "locator", "value", "timeout_ms", "reason"}, {"action"})
        action = step["action"]
        if action not in ACTIONS: raise Invalid("Unsupported action.")
        allowed = {"action", "timeout_ms"}
        if action in {"click", "fill", "select", "check", "upload", "wait"}:
            validate_locator(step.get("locator"))
            allowed.add("locator")
        if action in {"navigate", "wait_url", "fill", "select", "check", "upload"}:
            allowed.add("value")
            value = step.get("value")
            if isinstance(value, dict):
                keys(value, {"input"}, {"input"})
                if value["input"] not in names: raise Invalid("Step refers to an undefined input.")
            elif action == "check":
                if not isinstance(value, bool): raise Invalid("Check requires a boolean.")
            else:
                text(value, empty=action == "fill")
                if action in {"navigate", "wait_url"}: safe_url(value)
                if action == "upload": raise Invalid("Uploads must use a local path input, never a saved literal.")
        if action == "unsupported":
            allowed.add("reason")
            text(step.get("reason"), 240)
        if set(step) - allowed: raise Invalid("Fields do not match action.")
        timeout = step.get("timeout_ms", 8000)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 500 <= timeout <= 30000:
            raise Invalid("Wait timeout must be 500–30000 milliseconds.")
    return obj

def resolve_task(task, values):
    obj = validate_task(task)
    if not obj["steps"]: raise Invalid("Add or record steps first.")
    if any(s["action"] == "unsupported" for s in obj["steps"]):
        raise Invalid("Resolve every unsupported step before playback.")
    if not isinstance(values, dict) or set(values) - {i["name"] for i in obj["inputs"]}:
        raise Invalid("Unknown input values.")
    for item in obj["inputs"]:
        if item["required"] and not str(values.get(item["name"], "")).strip():
            raise Invalid("Required input: " + item["name"])
    from pathlib import Path
    for step in obj["steps"]:
        if isinstance(step.get("value"), dict):
            name = step["value"]["input"]
            value = values.get(name, "")
            text(value, empty=step["action"] == "fill")
            if step["action"] == "check":
                if value not in {"true", "false"}: raise Invalid("Checkbox inputs must be true or false.")
                value = value == "true"
            if step["action"] in {"navigate", "wait_url"}: safe_url(value)
            if step["action"] == "upload":
                path = Path(value)
                if not path.is_absolute() or not path.is_file():
                    raise Invalid("Upload input must be an existing absolute local file path: " + name)
                if PRIVATE.search(path.name):
                    raise Invalid("Credential/session files cannot be uploaded.")
            step["value"] = value
    return obj
