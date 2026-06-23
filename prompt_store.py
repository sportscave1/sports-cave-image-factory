from datetime import datetime, timezone
import json
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROMPT_OVERRIDES_PATH = BASE_DIR / "output" / "_cache" / "prompt_overrides.json"
PROMPT_STORE_VERSION = 1


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_prompt_store():
    payload = {"version": PROMPT_STORE_VERSION, "prompts": {}}
    if PROMPT_OVERRIDES_PATH.exists():
        try:
            loaded = json.loads(PROMPT_OVERRIDES_PATH.read_text(encoding="utf-8"))
        except Exception:
            loaded = {}
        if isinstance(loaded, dict):
            payload.update(loaded)
    if not isinstance(payload.get("prompts"), dict):
        payload["prompts"] = {}
    payload["version"] = PROMPT_STORE_VERSION
    return payload


def save_prompt_store(payload):
    store = {"version": PROMPT_STORE_VERSION, "prompts": {}}
    if isinstance(payload, dict):
        store.update(payload)
    if not isinstance(store.get("prompts"), dict):
        store["prompts"] = {}
    store["version"] = PROMPT_STORE_VERSION
    store["updated_at"] = now_iso()
    PROMPT_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROMPT_OVERRIDES_PATH.write_text(json.dumps(store, indent=2, sort_keys=True), encoding="utf-8")
    return store


def get_prompt_record(prompt_id):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        return {}
    return dict((load_prompt_store().get("prompts") or {}).get(prompt_id) or {})


def get_prompt(prompt_id, default_text):
    record = get_prompt_record(prompt_id)
    override = record.get("text")
    if isinstance(override, str) and override.strip():
        return override
    return str(default_text or "")


def save_prompt(prompt_id, title, text):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        raise ValueError("Prompt ID is missing.")
    store = load_prompt_store()
    prompts = dict(store.get("prompts") or {})
    prompts[prompt_id] = {
        "title": str(title or prompt_id),
        "text": str(text or ""),
        "updated_at": now_iso(),
    }
    store["prompts"] = prompts
    return save_prompt_store(store)["prompts"][prompt_id]
