"""Data-only desktop format; browser version 1 remains owned by its adapter."""
from copy import deepcopy
import json
import math
import re
import uuid
from urllib.parse import urlsplit, parse_qsl

FORMAT = "sports-cave.desktop"
CAPABILITIES = {
    "browser_download": "edge.download.v3",
    "transfer_copy": "transfer.editor-copy.v3",
    "transfer_copy_button": "transfer.prompt-copy.v3",
    "transfer_paste": "transfer.paste.v3",
    "browser_tab": "edge.tab.v1",
    "browser_navigation": "edge.navigation.v3",
    "invoke": "uia.invoke.v1",
    "set_text": "uia.value.v1",
    "copy_text": "clipboard.copy-text.v1",
    "select": "uia.selection.v1",
    "toggle": "uia.toggle.v1",
    "focus_window": "windows.focus.v1",
    "window_state": "windows.state.v1",
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


def browser_identity(value):
    fields(value, ("profile", "page", "frame", "control"), ("product",))
    if "product" in value and (not isinstance(value["product"], str) or not re.fullmatch(r"[a-f0-9]{64}",value["product"])):
        raise Invalid("Invalid prepared product identity.")
    try:
        if str(uuid.UUID(value["profile"])) != value["profile"]:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise Invalid("Invalid preview browser profile.") from None
    page = text(value["page"], 500)
    parsed = urlsplit(page)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or
            parsed.port not in {18962, 18963} or parsed.username or parsed.password or parsed.fragment or
            any(key not in {"page", "upload", "sync_map"} for key, _ in parse_qsl(parsed.query))):
        raise Invalid("Browser page is outside the permitted preview origins or identity fields.")
    for key in ("frame", "control"):
        text(value[key])
        if PRIVATE.search(value[key]):
            raise Invalid("Protected browser identity excluded.")
    return value


def identity(target):
    # No persistent HWND, process ID, UIA runtime ID or screen coordinates.
    fields(target, ("app", "window_key", "control_type", "automation_id", "name"), ("scope", "postcondition", "selector", "browser", "source_browser", "prompt_proof", "download"))
    if 'download' in target:
        value=target['download']
        fields(value,('url','filename','save_as'))
        uri=urlsplit(text(value['url'],1000))
        query=dict(parse_qsl(uri.query))
        try: nonce=str(uuid.UUID(query.get('sc_download','')))
        except (ValueError,TypeError,AttributeError): raise Invalid('Missing download correlation nonce.') from None
        if (uri.scheme!='http' or uri.hostname!='127.0.0.1' or uri.port not in {18962,18963} or
            uri.username or uri.password or uri.fragment or nonce!=query['sc_download'] or
            type(value['save_as']) is not bool or not target.get('browser') or target['control_type'] not in {'Button','Hyperlink'}):
            raise Invalid('Download requires a supported preview source and browser control.')
        if any(c in text(value['filename']) for c in '\\/:*?"<>|') or PRIVATE.search(value['filename']):
            raise Invalid('Unsupported download filename.')
    if "prompt_proof" in target:
        proof = target["prompt_proof"]
        fields(proof, ("sha256", "utf16_length", "utf8_length"))
        if (not isinstance(proof["sha256"], str) or not re.fullmatch(r"[a-f0-9]{64}", proof["sha256"]) or
                any(type(proof[k]) is not int or not 1 <= proof[k] <= 1024*1024 for k in ("utf16_length", "utf8_length")) or
                target["control_type"] != "Button" or target["automation_id"] != "copyPrompt" or
                target["name"] != "Copy Black Frame Prompt" or re.split(r"[\\/]",target["app"])[-1].lower() != "msedge.exe"):
            raise Invalid("Invalid complete product prompt proof.")
    for key in ("browser", "source_browser"):
        if key in target:
            browser_identity(target[key])
            if re.split(r"[\\/]", target["app"])[-1].lower() != "msedge.exe":
                raise Invalid("Browser identity requires Edge.")
    if "source_browser" in target and ("browser" not in target or target["control_type"] != "TabItem"):
        raise Invalid("Source browser identity is restricted to tab transitions.")
    scoped_scroll = "selector" in target
    if scoped_scroll and (target["selector"] != "uia.unique-scoped-scroll.v1" or
                          target["control_type"] not in {"Group", "Pane", "Custom"} or
                          target["automation_id"] or target["name"] or not target.get("scope")):
        raise Invalid("Anonymous scroll controls require a unique named ancestor scope.")
    if "postcondition" in target:
        generation = target["postcondition"] == "sports-cave.product-generation.v1" and target["name"] == "Generate mockups"
        picker = (target["postcondition"] == "sports-cave.product-psd-picker.v1" and target["name"] == "Choose PSD" and target["automation_id"] == "choose" and
                  isinstance(target.get("scope"), list) and any(isinstance(a, dict) and a.get("control_type") == "Document" and a.get("automation_id") == "RootWebArea" and a.get("name") == "Product Uploads" for a in target["scope"]))
        dialog = (target["postcondition"] == "uia.dialog-dismissed.v1" and isinstance(target.get("scope"), list) and
                  any(isinstance(a, dict) and a.get("control_type") == "Window" and (a.get("automation_id") or a.get("name")) for a in target["scope"]))
        if (not (generation or picker or dialog) or
                target["control_type"] != "Button" or
                not isinstance(target["app"], str) or
                (not dialog and re.split(r"[\\/]", target["app"])[-1].lower() != "msedge.exe") or "scope" not in target):
            raise Invalid("Unsupported application result contract.")
    for key, value in target.items():
        if key in {"browser", "source_browser", "prompt_proof"}:
            continue
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
    if not target["automation_id"] and not target["name"] and not scoped_scroll:
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
        if "selector" in context["window"]:
            raise Invalid("Starting window cannot use a scroll selector.")
    if context["mode"] not in {"prepared", "desktop_session", "specific_product", "per_run_product"}:
        raise Invalid("Unknown starting context mode.")
    if context["mode"] in {"prepared", "desktop_session"}:
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
    transfer_slots = set()
    last_transfer = None
    for action in task["actions"]:
        fields(action, ("version", "kind", "requires", "target", "timeout_ms"), ("value", "observed_ms"))
        if "observed_ms" in action and (type(action["observed_ms"]) is not int or action["observed_ms"] < 0):
            raise Invalid("Invalid observation time.")
        kind = action["kind"]
        if type(action["version"]) is not int or action["version"] not in {1, 2, 3} or kind not in CAPABILITIES:
            raise Invalid("Unsupported desktop action.")
        transfer = kind.startswith("transfer_")
        if (transfer or kind in {'browser_download','browser_navigation'}) != (action["version"] == 3):
            raise Invalid("Run-local transfers require version 3; old actions retain their semantics.")
        expected = CAPABILITIES[kind] if action["version"] == 1 else CAPABILITIES[kind].replace(".v1", ".v2")
        if action["requires"] != [expected]:
            raise Invalid("Action capability contract does not match.")
        identity(action["target"])
        if ('download' in action['target']) != (kind=='browser_download'):
            raise Invalid('Download metadata is restricted to versioned download actions.')
        if "selector" in action["target"] and (kind != "scroll" or action["version"] != 2):
            raise Invalid("Anonymous scroll identity is restricted to scoped scrolling.")
        if "postcondition" in action["target"] and (kind != "invoke" or action["version"] != 2):
            raise Invalid("Application result verification requires scoped invoke.")
        if "prompt_proof" in action["target"] and (kind != "invoke" or action["version"] != 2):
            raise Invalid("Complete prompt verification requires scoped invoke.")
        if action["version"] >= 2 and "scope" not in action["target"]:
            raise Invalid("Scoped desktop actions require ancestor identity.")
        if type(action["timeout_ms"]) is not int or not 100 <= action["timeout_ms"] <= 30000:
            raise Invalid("Readiness timeout must be bounded.")
        if kind=='browser_download':
            fields(action.get('value'),('directory',))
            directory=text(action['value']['directory'],500)
            if not re.match(r'^[A-Za-z]:[\\/]',directory) or '..' in re.split(r'[\\/]',directory):
                raise Invalid('Download destination must be an absolute local folder.')
        elif transfer:
            target=action["target"]
            value=action.get("value")
            fields(value,("slot","mode"))
            if type(value["slot"]) is not int or not 0 <= value["slot"] <= 1000000:
                raise Invalid("Invalid automatic transfer reference.")
            if "prompt_proof" in target or "postcondition" in target:
                raise Invalid("Dynamic transfers cannot carry fixed content expectations.")
            if kind == "transfer_copy_button":
                if (value["mode"]!="application_prompt" or target["control_type"]!="Button" or
                    target["automation_id"]!="copyPrompt" or target["name"]!="Copy Black Frame Prompt" or
                    not target.get("browser",{}).get("product")):
                    raise Invalid("Copy button needs the verified application prompt source.")
            elif (target["control_type"] not in {"Edit","Document"} or target["automation_id"]=="RootWebArea" or
                  value["mode"] != ("whole_text" if kind=="transfer_copy" else "replace_all")):
                raise Invalid("Transfer requires an explicit supported text field.")
            if kind=="transfer_paste":
                if value["slot"] != last_transfer:
                    raise Invalid("Paste must consume this recording's latest verified Copy.")
            else:
                if value["slot"] in transfer_slots:raise Invalid("Transfer source reference reused.")
                transfer_slots.add(value["slot"]);last_transfer=value["slot"]
        elif kind == "browser_navigation":
            target = action["target"]
            destination = browser_identity(action.get("value"))
            source = target.get("browser", {})
            if (target["control_type"] != "Button" or not source or
                    destination["profile"] != source["profile"] or destination["page"] == source["page"] or
                    destination["frame"] != "top" or destination["control"] != "document"):
                raise Invalid("Navigation requires an identified button and a different verified destination in the same browser profile.")
        elif kind == "browser_tab":
            target = action["target"]
            if (action["version"] != 2 or target["control_type"] != "TabItem" or
                    target["scope"] != [] or target["automation_id"] or not target["name"] or
                    re.split(r"[\\/]", target["app"])[-1].lower() != "msedge.exe" or "value" in action):
                raise Invalid("Browser switching requires an explicitly named existing Edge tab.")
        elif kind == "window_state":
            if (action["version"] != 2 or context["mode"] != "desktop_session" or
                action["target"]["control_type"] != "Window" or action["target"]["scope"] != [] or
                not isinstance(action.get("value"), str) or
                action["value"] not in {"normal", "minimized", "maximized"}):
                raise Invalid("Window transitions require a desktop session and explicit supported state.")
        elif kind == "copy_text":
            if (action["version"] != 2 or action["target"]["control_type"] not in {"Edit", "Document"}
                    or action["target"]["automation_id"] == "RootWebArea"):
                raise Invalid("Copy requires a scoped text editor.")
            value = action.get("value")
            fields(value, ("text", "source_sha256"))
            text(value["text"], 2000)
            if not isinstance(value["source_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", value["source_sha256"]):
                raise Invalid("Copy requires an exact source fingerprint.")
        elif kind in {"set_text", "select"}:
            if not (kind == "set_text" and action.get("value") == ""):
                text(action.get("value"), 2000)
        elif kind in {"toggle", "expand"}:
            if type(action.get("value")) is not bool:
                raise Invalid("Toggle and expansion require an explicit boolean.")
        elif kind == "scroll":
            if action["version"] != 2:
                raise Invalid("Scrolling requires a scoped version-2 action.")
            position = action.get("value")
            fields(position, ("horizontal", "vertical"), ("horizontal_view_size", "vertical_view_size"))
            for axis in ("horizontal", "vertical"):
                percent = position[axis]
                if (type(percent) not in {int, float} or not math.isfinite(percent) or
                    not (percent == -1 or 0 <= percent <= 100)):
                    raise Invalid("Scroll percentages must be finite, -1 or between 0 and 100.")
            for axis in ("horizontal_view_size", "vertical_view_size"):
                if axis in position and (type(position[axis]) not in {int, float} or not math.isfinite(position[axis]) or not 0 < position[axis] <= 100):
                    raise Invalid("Viewport sizes must be finite percentages greater than zero.")
            if position["horizontal"] == position["vertical"] == -1:
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
