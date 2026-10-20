"""Revision-fenced, data-only edits. Source steps own their locators and warnings."""
import copy
import re
import uuid
from pathlib import Path
from .schema import Invalid, keys, text, validate_task, safe_url, validate_locator

EDIT_COMMANDS = {"edit-copy", "edit-file", "record-replacement"}


def reference(data):
    try:
        if str(uuid.UUID(data["id"])) != data["id"]: raise ValueError()
    except (KeyError, ValueError, TypeError, AttributeError):
        raise Invalid("Select a saved recording.")
    if not re.fullmatch("[a-f0-9]{64}", str(data.get("revision", ""))):
        raise Invalid("Reopen Edit to load the current recording.")


def validate_edit_payload(kind, data):
    allowed = {"id", "revision"} | ({"name", "steps"} if kind == "edit-copy" else {"step"} if kind == "record-replacement" else set())
    keys(data, allowed, allowed)
    reference(data)
    if kind == "record-replacement": number(data["step"])
    if kind != "edit-copy": return
    text(data["name"], 100)
    if not isinstance(data["steps"], list) or not 1 <= len(data["steps"]) <= 500:
        raise Invalid("Keep between 1 and 500 actions.")
    errors = {}
    for index, entry in enumerate(data["steps"]):
        try: validate_entry(entry)
        except Invalid as error: errors[str(index)] = str(error)
    if errors: raise EditInvalid(errors)


def validate_entry(entry):
    keys(entry, {"source", "recording", "check", "value"})
    if sum(k in entry for k in ("source", "recording", "check")) != 1:
        raise Invalid("Choose a recorded action or a readiness check.")
    if "source" in entry:
        number(entry["source"])
    if "recording" in entry:
        keys(entry["recording"], {"id", "revision", "step"}, {"id", "revision", "step"})
        reference(entry["recording"]); number(entry["recording"]["step"])
    if "check" in entry:
        keys(entry["check"], {"action", "value"}, {"action", "value"})
        if entry["check"]["action"] == "wait_url": safe_url(entry["check"]["value"])
        elif entry["check"]["action"] == "wait": validate_locator({"by": "text", "value": entry["check"]["value"]})
        else: raise Invalid("Choose visible text or the expected website address.")
    if "value" in entry:
        value = entry["value"]
        if isinstance(value, dict):
            keys(value, {"file"}, {"file"})
            try: uuid.UUID(value["file"])
            except (ValueError, TypeError, AttributeError): raise Invalid("Choose the file on your PC.")
        elif not isinstance(value, bool):
            text(value, empty=True)
            if value.startswith(("http://", "https://")): safe_url(value)


def number(value):
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < 500:
        raise Invalid("Choose an action in this recording.")


def source(store, data):
    original = store.get(data["id"])
    if store.revision(original) != data["revision"]:
        raise Invalid("This recording changed. Cancel and reopen Edit before saving.")
    return original


class EditInvalid(Invalid):
    def __init__(self, errors):
        super().__init__("Check the highlighted actions, then save again.")
        self.step_errors = errors


def edited_copy(store, vault, data, copy_id):
    """Construct fully validated copy without ever writing a source recording."""
    validate_edit_payload("edit-copy", data)
    original = source(store, data)
    task = {**copy.deepcopy(original), "id": copy_id, "name": data["name"].strip(), "steps": []}
    defaults = copy.deepcopy(vault.read().get("defaults", {}).get(original["id"], {}))
    fragments = {}; errors = {}
    for index, entry in enumerate(data["steps"]):
        try:
            if "check" in entry:
                check = entry["check"]
                step = {"action": check["action"], "timeout_ms": 30000}
                if check["action"] == "wait": step["locator"] = {"by": "text", "value": check["value"]}
                else: step["value"] = check["value"]
            else:
                recorded = original
                position = entry.get("source")
                if "recording" in entry:
                    ref = entry["recording"]
                    if ref["id"] not in fragments:
                        fragment = source(store, ref)
                        # Namespace reusable inputs from replacement recordings.
                        names={i['name'] for i in task['inputs']};mapping={}
                        for item in fragment['inputs']:
                            base='edit_'+str(len(fragments))+'_'+item['name'][:25];name=base;count=1
                            while name in names:
                                name=base+'_'+str(count);count+=1
                            mapping[item['name']]=name;names.add(name)
                        for item in fragment["inputs"]:
                            task["inputs"].append({**item, "name": mapping[item["name"]]})
                        saved = vault.read().get("defaults", {}).get(ref["id"], {})
                        defaults.update({mapping[k]: v for k, v in saved.items() if k in mapping})
                        fragments[ref["id"]] = (fragment, mapping)
                    fragment, mapping = fragments[ref["id"]]
                    if store.revision(fragment) != ref["revision"]: raise Invalid("The replacement changed. Record or select it again.")
                    recorded, position = fragment, ref["step"]
                if position >= len(recorded["steps"]): raise Invalid("This action no longer exists. Reopen Edit.")
                step = copy.deepcopy(recorded["steps"][position])
                if "recording" in entry and isinstance(step.get("value"), dict) and "input" in step["value"]:
                    step["value"] = {"input": mapping[step["value"]["input"]]}
            if "value" in entry:
                if "check" in entry or step["action"] not in {"navigate", "wait_url", "fill", "select", "check", "upload"}:
                    raise Invalid("This action has no editable value. Delete it or record a replacement.")
                step["value"] = copy.deepcopy(entry["value"])
                if step["action"] == "upload":
                    if not isinstance(step["value"], dict) or set(step["value"]) != {"file"}:
                        raise Invalid("Choose the replacement file on your recorder PC.")
                    if not Path(vault.file(step["value"]["file"])).is_file():
                        raise Invalid("Choose this file again on your recorder PC.")
            required=step.get('value',{}).get('input') if isinstance(step.get('value'),dict) else None
            validate_task({**task, "steps": [step], "inputs":[i for i in task['inputs'] if i['name']==required]})
            task["steps"].append(step)
        except (Invalid, IndexError) as error:
            errors[str(index)] = str(error)
    if errors: raise EditInvalid(errors)
    used = {s["value"]["input"] for s in task["steps"] if isinstance(s.get("value"), dict) and "input" in s["value"]}
    task["inputs"] = [i for i in task["inputs"] if i["name"] in used]
    defaults = {k: v for k, v in defaults.items() if k in used}
    return validate_task(task), defaults
