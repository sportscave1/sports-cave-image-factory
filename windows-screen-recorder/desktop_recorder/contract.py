"""Data-only desktop format; browser version 1 remains owned by its adapter."""
from copy import deepcopy
import json
import math
import re
import uuid

FORMAT = "sports-cave.desktop"
CAPABILITIES = {
    "invoke": "uia.invoke.v1",
    "set_text": "uia.value.v1",
    "select": "uia.selection.v1",
    "toggle": "uia.toggle.v1",
    "focus_window": "windows.focus.v1",
    "wait_ready": "uia.readiness.v1",
    "expand": "uia.expand.v1",
    "scroll": "uia.scroll.v1",
}
PRIVATE = re.compile(r"password|passwd|credential|secret|token|authorization|one.?time|otp|api.?key", re.I)
TOKEN = re.compile(r"Bearer\s+\S+|eyJ[\w-]{12,}\.[\w-]+|(?:sk-|ghp_|xoxb-)[\w-]{10,}", re.I)


class Invalid(ValueError):
    pass


def fields(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise Invalid("Missing or unknown fields.")


def text(value, limit=180):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or TOKEN.search(value):
        raise Invalid("Expected bounded, non-credential text.")
    return value


def identity(target):
    # No persistent HWND, process ID, UIA runtime ID or screen coordinates.
    fields(target, ("app", "window_key", "control_type", "automation_id", "name"), ("scope",))
    for key, value in target.items():
        if key == "scope":
            if not isinstance(value, list) or len(value) > 16:
                raise Invalid("Invalid ancestor scope.")
            for ancestor in value:
                fields(ancestor, ("control_type", "automation_id", "name"))
                for label, part in ancestor.items():
                    if label != "control_type" and part == "":
                        continue
                    text(part)
                    if PRIVATE.search(part):
                        raise Invalid("Sensitive ancestor identity is excluded.")
                if not ancestor["automation_id"] and not ancestor["name"]:
                    raise Invalid("Ancestor must have an identity.")
            continue
        if key in {"automation_id", "name"} and value == "":
            continue
        text(value)
        if PRIVATE.search(value):
            raise Invalid("Sensitive control identity is excluded.")
    if not target["automation_id"] and not target["name"]:
        raise Invalid("Control needs a stable identity; ambiguity must block execution.")
    return target


def validate(raw):
    task = deepcopy(raw)
    fields(task, ("format", "version", "id", "name", "starting_context", "actions"))
    if task["format"] != FORMAT or type(task["version"]) is not int or task["version"] != 1:
        raise Invalid("Unsupported desktop format. Browser tasks require the browser adapter.")
    try:
        if str(uuid.UUID(task["id"])) != task["id"]:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Invalid("Invalid task ID.") from None
    text(task["name"], 100)
    context = task["starting_context"]
    fields(context, ("mode", "binding"), ("window",))
    if "window" in context:
        identity(context["window"])
    if context["mode"] not in {"prepared", "specific_product", "per_run_product"}:
        raise Invalid("Unknown starting context mode.")
    if context["mode"] == "prepared":
        if context["binding"] is not None:
            raise Invalid("Prepared context has no product binding.")
    else:
        # Opaque local binding reference, never paths, credentials or workflow URLs.
        try:
            if str(uuid.UUID(context["binding"])) != context["binding"]:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise Invalid("Context requires an opaque local binding.") from None
    if not isinstance(task["actions"], list) or len(task["actions"]) > 500:
        raise Invalid("At most 500 actions.")
    for action in task["actions"]:
        fields(action, ("version", "kind", "requires", "target", "timeout_ms"), ("value", "observed_ms"))
        if "observed_ms" in action and (type(action["observed_ms"]) is not int or action["observed_ms"] < 0):
            raise Invalid("Invalid observation time.")
        kind = action["kind"]
        if type(action["version"]) is not int or action["version"] not in {1, 2} or kind not in CAPABILITIES:
            raise Invalid("Unsupported desktop action.")
        expected = CAPABILITIES[kind] if action["version"] == 1 else CAPABILITIES[kind].replace(".v1", ".v2")
        if action["requires"] != [expected]:
            raise Invalid("Action capability contract does not match.")
        identity(action["target"])
        if action["version"] == 2 and "scope" not in action["target"]:
            raise Invalid("Scoped desktop actions require ancestor identity.")
        if type(action["timeout_ms"]) is not int or not 100 <= action["timeout_ms"] <= 30000:
            raise Invalid("Readiness timeout must be bounded.")
        if kind in {"set_text", "select"}:
            if not (kind == "set_text" and action.get("value") == ""):
                text(action.get("value"), 2000)
        elif kind in {"toggle", "expand"}:
            if type(action.get("value")) is not bool:
                raise Invalid("Toggle and expansion require an explicit boolean.")
        elif kind == "scroll":
            if action["version"] != 2:
                raise Invalid("Scrolling requires a scoped version-2 action.")
            position = action.get("value")
            fields(position, ("horizontal", "vertical"))
            for percent in position.values():
                if (type(percent) not in {int, float} or not math.isfinite(percent) or
                    not (percent == -1 or 0 <= percent <= 100)):
                    raise Invalid("Scroll percentages must be finite, -1 or between 0 and 100.")
            if all(percent == -1 for percent in position.values()):
                raise Invalid("At least one axis must be scrollable.")
        elif "value" in action:
            raise Invalid("This action has no value.")
    if len(json.dumps(task).encode()) > 1_000_000:
        raise Invalid("Task is too large.")
    return task


def requirements(task):
    return frozenset(c for a in validate(task)["actions"] for c in a["requires"])


def route(raw):
    if isinstance(raw, dict) and raw.get("format") == FORMAT:
        validate(raw)
        return "desktop"
    if isinstance(raw, dict) and "format" not in raw and raw.get("version") == 1:
        return "browser"  # The original validator still MUST validate this payload.
    raise Invalid("Unknown recording format.")
