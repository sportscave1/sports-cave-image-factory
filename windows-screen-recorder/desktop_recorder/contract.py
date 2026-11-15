"""Data-only desktop format; browser version 1 remains owned by its adapter."""
from copy import deepcopy
import json
import math
import re
import uuid
from urllib.parse import urlsplit, parse_qsl

FORMAT = "sports-cave.desktop"
CAPABILITIES = {
    "local_upload": "local.upload.v3",
    "chat_download": "chat.download.v3",
    "chat_wait": "chat.wait.v3",
    "chat_submit": "chat.submit.v3",
    "taskbar_activate": "windows.taskbar.v3",
    "browser_download": "edge.download.v3",
    "transfer_copy": "transfer.editor-copy.v3",
    "transfer_copy_button": "transfer.prompt-copy.v3",
    "transfer_paste": "transfer.paste.v3",
    "image_paste": "image.paste.v3",
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


def chromium_app(app):
    return isinstance(app, str) and re.split(r"[\\/]", app)[-1].lower() in {"msedge.exe", "chrome.exe"}


def permitted_origin(uri, *, chatgpt=False):
    try:
        return ((uri.scheme == 'http' and uri.hostname == '127.0.0.1' and uri.port in {18962,18963}) or
                (uri.scheme == 'https' and (uri.hostname == 'sports-cave-image-factory.onrender.com' or chatgpt and uri.hostname == 'chatgpt.com') and uri.port in {None,443}))
    except ValueError:
        return False


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
    if (not permitted_origin(parsed,chatgpt=True) or parsed.username or parsed.password or parsed.fragment or
            any(key not in {"page", "upload", "sync_map"} for key, _ in parse_qsl(parsed.query))):
        raise Invalid("Browser page is outside the configured recorder origins or identity fields.")
    for key in ("frame", "control"):
        text(value[key])
        if PRIVATE.search(value[key]):
            raise Invalid("Protected browser identity excluded.")
    return value


def identity(target):
    # No persistent HWND, process ID, UIA runtime ID or screen coordinates.
    fields(target, ("app", "window_key", "control_type", "automation_id", "name"), ("scope", "postcondition", "selector", "browser", "source_browser", "prompt_proof", "download"))
    if 'download' in target:
        if re.split(r"[\\/]", target["app"])[-1].lower() != "msedge.exe":
            raise Invalid("Download receipts require the configured Edge bridge.")
        value=target['download']
        fields(value,('url','filename','save_as'))
        uri=urlsplit(text(value['url'],1000))
        query=dict(parse_qsl(uri.query))
        try: nonce=str(uuid.UUID(query.get('sc_download','')))
        except (ValueError,TypeError,AttributeError): raise Invalid('Missing download correlation nonce.') from None
        if (not permitted_origin(uri) or
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
                target["name"] != "Copy Black Frame Prompt" or not chromium_app(target["app"])):
            raise Invalid("Invalid complete product prompt proof.")
    for key in ("browser", "source_browser"):
        if key in target:
            browser_identity(target[key])
            if not chromium_app(target["app"]):
                raise Invalid("Browser identity requires Chrome or Edge.")
    if "source_browser" in target and ("browser" not in target or target["control_type"] != "TabItem"):
        raise Invalid("Source browser identity is restricted to tab transitions.")
    scoped_scroll = "selector" in target
    if scoped_scroll and (target["selector"] != "uia.unique-scoped-scroll.v1" or
                          target["control_type"] not in {"Group", "Pane", "Custom"} or
                          target["automation_id"] or target["name"] or not target.get("scope")):
        raise Invalid("Anonymous scroll controls require a unique named ancestor scope.")
    if "postcondition" in target:
        image = (target["postcondition"] == "sports-cave.product-image-copy.v1" and target["name"] == "Copy black frame" and
                 target["automation_id"] == "copyImage" and target.get("browser", {}).get("product") and
                 isinstance(target.get("scope"), list) and len(target["scope"]) >= 3 and
                 target["scope"][0] == {"control_type":"Group", "automation_id":"root", "name":""} and
                 target["scope"][1] == {"control_type":"Document", "automation_id":"RootWebArea", "name":""} and
                 target["scope"][2].get("control_type") == "Document" and
                 target["scope"][2].get("name") == "product_upload_gallery.product_upload_gallery" and
                 target["scope"][2].get("automation_id") in {"", "sc-product-upload-copy"})
        generation = target["postcondition"] == "sports-cave.product-generation.v1" and target["name"] == "Generate mockups"
        picker = (target["postcondition"] == "sports-cave.product-psd-picker.v1" and target["name"] == "Choose PSD" and target["automation_id"] == "choose" and
                  isinstance(target.get("scope"), list) and any(isinstance(a, dict) and a.get("control_type") == "Document" and a.get("automation_id") == "RootWebArea" and a.get("name") == "Product Uploads" for a in target["scope"]))
        dialog = (target["postcondition"] == "uia.dialog-dismissed.v1" and isinstance(target.get("scope"), list) and
                  any(isinstance(a, dict) and a.get("control_type") == "Window" and (a.get("automation_id") or a.get("name")) for a in target["scope"]))
        local_save = (target["postcondition"] == "sports-cave.local-save.v1" and target["name"] == "Save all" and target["window_key"] == "Sports Cave recorder save test - Google Chrome")
        if (not (generation or picker or dialog or image or local_save) or
                target["control_type"] != "Button" or
                not isinstance(target["app"], str) or
                (not dialog and not chromium_app(target["app"])) or "scope" not in target):
            raise Invalid("Unsupported application result contract.")
    for key, value in target.items():
        if key in {"browser", "source_browser", "prompt_proof", "download"}:
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
    image_owned = False
    for action in task["actions"]:
        fields(action, ("version", "kind", "requires", "target", "timeout_ms"), ("value", "observed_ms"))
        if "observed_ms" in action and (type(action["observed_ms"]) is not int or action["observed_ms"] < 0):
            raise Invalid("Invalid observation time.")
        kind = action["kind"]
        if type(action["version"]) is not int or action["version"] not in {1, 2, 3} or kind not in CAPABILITIES:
            raise Invalid("Unsupported desktop action.")
        transfer = kind.startswith("transfer_")
        if (transfer or kind in {'local_upload','chat_download','chat_wait','chat_submit','browser_download','browser_navigation','taskbar_activate','image_paste'}) != (action["version"] == 3):
            raise Invalid("Run-local transfers require version 3; old actions retain their semantics.")
        expected = CAPABILITIES[kind] if action["version"] == 1 else CAPABILITIES[kind].replace(".v1", ".v2")
        required = [expected]
        route = action.get('value')
        if (kind == 'taskbar_activate' and isinstance(route, dict)
                and isinstance(route.get('thumbnail'), dict)
                and route['thumbnail'].get('class_name') == 'SC.LocalCaption.v1'):
            required.append('windows.taskbar.caption.v1')
        if action["requires"] != required:
            raise Invalid("Action capability contract does not match.")
        identity(action["target"])
        if kind == 'invoke' and action['target'].get('postcondition') == 'sports-cave.product-image-copy.v1':
            image_owned = True
            last_transfer = None
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
        if type(action["timeout_ms"]) is not int or not 100 <= action["timeout_ms"] <= (900000 if kind == 'chat_wait' else 300000 if kind in {'local_upload','chat_download'} else 30000):
            raise Invalid("Readiness timeout must be bounded.")
        if kind == 'taskbar_activate':
            target = action['target']
            if target['control_type'] != 'Window' or target['automation_id'] != 'window' or target['scope'] != []:
                raise Invalid('Taskbar activation requires a separately verified destination window.')
            value = action.get('value')
            fields(value, ('button',), ('thumbnail',))
            for part, selector in value.items():
                fields(selector, ('surface', 'control_type', 'class_name', 'automation_id', 'name'))
                surfaces = {'TaskListThumbnailWnd', 'XamlExplorerHostIslandWindow'} if part == 'thumbnail' else {'Shell_TrayWnd', 'Shell_SecondaryTrayWnd'}
                if selector['surface'] not in surfaces or selector['control_type'] not in {'Button', 'ListItem'}:
                    raise Invalid('Invalid taskbar surface or control.')
                for key, label in selector.items():
                    if label == '' and key in {'class_name', 'automation_id', 'name'}:
                        continue
                    text(label)
                    if PRIVATE.search(label):
                        raise Invalid('Protected shell identity excluded.')
                if part == 'button' and (selector['control_type'] != 'Button' or
                        selector['class_name'] != 'Taskbar.TaskListButtonAutomationPeer' or
                        not selector['automation_id'].lower().startswith('appid:') or
                        not re.search(r' - [1-9][0-9]* running window', selector['name'])):
                    raise Invalid('Taskbar route must identify a running application; no launch or system control.')
                if part == 'thumbnail' and selector['name'] != target['window_key']:
                    raise Invalid('Thumbnail caption must identify its destination window.')
                if selector['class_name'] == 'SC.LocalCaption.v1' and (
                    part != 'thumbnail' or selector['surface'] != 'XamlExplorerHostIslandWindow'
                    or selector['control_type'] != 'ListItem' or selector['automation_id'] != 'exact-caption'
                ):
                    raise Invalid('Invalid local thumbnail caption selector.')
                if not selector['name'] and not selector['automation_id']:
                    raise Invalid('Taskbar control needs a durable identity.')
        elif kind=='browser_download':
            fields(action.get('value'),('directory',))
            directory=text(action['value']['directory'],500)
            if not re.match(r'^[A-Za-z]:[\\/]',directory) or '..' in re.split(r'[\\/]',directory):
                raise Invalid('Download destination must be an absolute local folder.')
        elif kind == 'local_upload':
            value = action.get('value'); fields(value, ('images',))
            if not chromium_app(action['target']['app']) or action['target']['control_type'] != 'Window':
                raise Invalid('Local uploads require a Chromium window.')
            if not isinstance(value['images'], list) or len(value['images']) != 3:
                raise Invalid('Three upload originals required.')
            roles, paths, hashes = set(), set(), set()
            for row in value['images']:
                fields(row, ('role', 'path', 'sha256'))
                path = text(row['path'],500)
                if (row['role'] not in {'Man Cave','Office','Living Room'} or row['role'] in roles
                    or not re.match(r'^[A-Za-z]:[\\/]',path) or '..' in re.split(r'[\\/]',path)
                    or not path.lower().endswith('.png') or path.casefold() in paths
                    or not isinstance(row['sha256'],str) or not re.fullmatch('[a-f0-9]{64}',row['sha256'])
                    or row['sha256'] in hashes):
                    raise Invalid('Ambiguous or unsafe upload original.')
                roles.add(row['role']);paths.add(path.casefold());hashes.add(row['sha256'])
        elif kind in {'chat_wait', 'chat_download'}:
            target = action['target']
            value = action.get('value')
            fields(value, ('request_id', 'conversation') if kind == 'chat_wait' else ('request_id', 'conversation', 'directory', 'images', 'csv_sha256'))
            try:
                valid_id = str(uuid.UUID(value['request_id'])) == value['request_id']
            except (ValueError, TypeError, AttributeError):
                valid_id = False
            if (not valid_id or not isinstance(value['conversation'], str)
                    or not re.fullmatch(r'https://chatgpt\.com/(?:g/g-p-6a387a17627081918e1700ec2783a12b(?:-sc-mockups-uploads)?/)?c/[a-f0-9-]{36}', value['conversation'])
                    or not chromium_app(target['app']) or target['control_type'] != 'Window'
                    or target['automation_id'] != 'window' or target['scope'] != []
                    or target.get('browser', {}).get('page') != value['conversation']):
                raise Invalid('Output wait requires the acknowledged request and exact conversation window.')
            if kind == 'chat_download':
                directory=text(value['directory'],500)
                if not re.match(r'^[A-Za-z]:[\\/]',directory) or '..' in re.split(r'[\\/]',directory):
                    raise Invalid('Downloads require an explicit absolute directory.')
                if not isinstance(value['csv_sha256'],str) or not re.fullmatch('[a-f0-9]{64}',value['csv_sha256']):
                    raise Invalid('Original CSV digest required.')
                if not isinstance(value['images'],list) or len(value['images']) != 3:
                    raise Invalid('Exactly three image bindings required.')
                roles=set(); indexes=set(); hashes=set(); titles=set(); names=set()
                for item in value['images']:
                    fields(item, ('role','index','title','filename','sha256'))
                    name=text(item['filename'],180); title=text(item['title'],180)
                    if (item['role'] not in {'Man Cave','Office','Living Room'} or item['role'] in roles
                            or type(item['index']) is not int or item['index'] not in {1,2,3} or item['index'] in indexes
                            or not re.fullmatch('[a-f0-9]{64}',str(item['sha256'])) or item['sha256'] in hashes
                            or title in titles or name.casefold() in names or re.search(r'[\\/<>:"|?*]',name)
                            or not name.lower().endswith('.png') or PRIVATE.search(title)):
                        raise Invalid('Image bindings must be unique and contain safe original identities.')
                    roles.add(item['role']);indexes.add(item['index']);hashes.add(item['sha256']);titles.add(title);names.add(name.casefold())
        elif kind == 'chat_submit':
            target = action['target']
            browser = target.get('browser', {})
            value = action.get('value')
            fields(value, ('request_id', 'sha256', 'characters'))
            try:
                valid_id = str(uuid.UUID(value['request_id'])) == value['request_id']
            except (ValueError, TypeError, AttributeError):
                valid_id = False
            if (not valid_id or not isinstance(value['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', value['sha256'])
                    or type(value['characters']) is not int or not 1 <= value['characters'] <= 1048576
                    or not chromium_app(target['app']) or target['control_type'] != 'Button' or target['name'] != 'Send'
                    or browser.get('page') != 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'
                    or browser.get('frame') != 'top' or browser.get('control') != 'label:button:Send'):
                raise Invalid('Submission requires an immutable request and the exact prepared project Send control.')
        elif kind == 'image_paste':
            target = action['target']
            browser = target.get('browser', {})
            if (not image_owned or 'value' in action or not chromium_app(target['app'])
                    or target['control_type'] != 'Edit' or target['name'] != 'New chat in SC Mockups/Uploads'
                    or browser.get('page') != 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project'
                    or browser.get('frame') != 'top'):
                raise Invalid('Image Paste requires this recording’s verified Copy and exact project composer.')
            image_owned = False
        elif transfer:
            image_owned = False
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
            image_owned = False
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
