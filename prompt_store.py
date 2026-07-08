from datetime import datetime, timezone
import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PROMPT_OVERRIDES_PATH = BASE_DIR / "output" / "_cache" / "prompt_overrides.json"
PROMPT_STORE_VERSION = 2
ENABLE_LOCAL_PROMPT_FILE_WRITES = (
    os.getenv("ENABLE_LOCAL_PROMPT_FILE_WRITES", "").strip().casefold() == "true"
)

SOURCE_SUPABASE = "supabase_saved"
SOURCE_DEFAULT = "default_fallback"
SOURCE_UNAVAILABLE = "supabase_unavailable"

LIFESTYLE_PROMPT_PREFIX = "lifestyle::"
ENABLE_LIFESTYLE_SUPABASE_READS_ENV = "ENABLE_LIFESTYLE_PROMPT_SUPABASE_READS"
_RUNTIME_PROMPT_CACHE = {}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _local_file_enabled():
    return os.getenv("ENABLE_LOCAL_PROMPT_FILE_WRITES", "").strip().casefold() == "true"


def _is_lifestyle_prompt(prompt_id):
    return str(prompt_id or "").strip().startswith(LIFESTYLE_PROMPT_PREFIX)


def _lifestyle_supabase_reads_enabled():
    return os.getenv(ENABLE_LIFESTYLE_SUPABASE_READS_ENV, "").strip().casefold() == "true"


def clear_prompt_cache(prompt_id=None):
    try:
        _load_prompt_from_supabase.cache_clear()
    except AttributeError:
        pass
    if prompt_id is None:
        _RUNTIME_PROMPT_CACHE.clear()
        return
    _RUNTIME_PROMPT_CACHE.pop(str(prompt_id or "").strip(), None)


def source_label(source):
    if source == SOURCE_SUPABASE:
        return "Source: Supabase saved"
    if source == SOURCE_DEFAULT:
        return "Source: Default file fallback"
    return "Not persisted — Supabase unavailable"


def _default_record(prompt_id, default_text, *, warning=""):
    return {
        "prompt_key": str(prompt_id or "").strip(),
        "prompt_name": "",
        "module": "",
        "text": str(default_text or ""),
        "prompt_text": str(default_text or ""),
        "source": SOURCE_UNAVAILABLE if warning else SOURCE_DEFAULT,
        "source_label": source_label(SOURCE_UNAVAILABLE if warning else SOURCE_DEFAULT),
        "persisted": False,
        "warning": warning,
    }


def _runtime_saved_record(prompt_id):
    record = _RUNTIME_PROMPT_CACHE.get(str(prompt_id or "").strip())
    if not isinstance(record, dict):
        return None
    prompt_text = record.get("prompt_text") or record.get("text") or ""
    if not str(prompt_text).strip():
        return None
    return {
        **record,
        "text": prompt_text,
        "prompt_text": prompt_text,
        "source": SOURCE_SUPABASE,
        "source_label": source_label(SOURCE_SUPABASE),
        "persisted": True,
        "warning": "",
    }


def _cache_runtime_record(prompt_id, record, fallback_text=""):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        return
    if not isinstance(record, dict):
        record = {}
    prompt_text = record.get("prompt_text") or record.get("text") or fallback_text or ""
    _RUNTIME_PROMPT_CACHE[prompt_id] = {
        **record,
        "prompt_key": record.get("prompt_key") or prompt_id,
        "text": prompt_text,
        "prompt_text": prompt_text,
        "source": SOURCE_SUPABASE,
        "source_label": source_label(SOURCE_SUPABASE),
        "persisted": True,
        "warning": "",
    }


def _supabase_backend():
    import supabase_backend

    return supabase_backend


def _load_prompt_from_supabase(prompt_id):
    backend = _supabase_backend()
    if not backend.is_configured():
        raise backend.SupabaseNotConfigured("Supabase/Postgres is not configured.")
    backend.ensure_prompt_template_schema()
    return backend.get_prompt_template(prompt_id)


try:
    from functools import lru_cache

    _load_prompt_from_supabase = lru_cache(maxsize=512)(_load_prompt_from_supabase)
except Exception:
    pass


def _upsert_prompt_to_supabase(prompt_id, title, text, *, module="", updated_by="sports_cave_os", source="supabase"):
    backend = _supabase_backend()
    if not backend.is_configured():
        raise backend.SupabaseNotConfigured("Supabase/Postgres is not configured.")
    backend.ensure_prompt_template_schema()
    clear_prompt_cache(prompt_id)
    record = backend.upsert_prompt_template(
        prompt_id,
        prompt_name=title,
        module=module,
        prompt_text=text,
        updated_by=updated_by,
        source=source,
    )
    clear_prompt_cache(prompt_id)
    _cache_runtime_record(prompt_id, record, fallback_text=text)
    return record


def load_prompt(prompt_id, default_text="", *, prompt_name="", module="", seed_default=True, force_supabase=False):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        return _default_record(prompt_id, default_text, warning="Prompt key is missing.")

    runtime_record = _runtime_saved_record(prompt_id)
    if runtime_record:
        return runtime_record

    # Mockup/lifestyle pages render many prompt cards at once. Hitting Supabase for every
    # card made the Mockups page slow after prompt persistence was added. Keep the old
    # fast path by default: use the local generated prompt text for lifestyle prompt grids,
    # and only persist edits on explicit Save. Set ENABLE_LIFESTYLE_PROMPT_SUPABASE_READS=true
    # if a deployment intentionally wants to read saved lifestyle prompts on every render.
    if _is_lifestyle_prompt(prompt_id) and not force_supabase and not _lifestyle_supabase_reads_enabled():
        return _default_record(prompt_id, default_text)

    try:
        record = _load_prompt_from_supabase(prompt_id) or {}
        prompt_text = record.get("prompt_text")
        if isinstance(prompt_text, str) and prompt_text.strip():
            loaded_record = {
                **record,
                "text": prompt_text,
                "source": SOURCE_SUPABASE,
                "source_label": source_label(SOURCE_SUPABASE),
                "persisted": True,
                "warning": "",
            }
            _cache_runtime_record(prompt_id, loaded_record, fallback_text=prompt_text)
            return loaded_record
        if seed_default and str(default_text or "").strip():
            seeded = _upsert_prompt_to_supabase(
                prompt_id,
                prompt_name or prompt_id,
                str(default_text or ""),
                module=module,
                updated_by="system_seed",
                source="default_seed",
            )
            prompt_text = seeded.get("prompt_text") or str(default_text or "")
            seeded_record = {
                **seeded,
                "text": prompt_text,
                "source": SOURCE_SUPABASE,
                "source_label": source_label(SOURCE_SUPABASE),
                "persisted": True,
                "warning": "",
            }
            _cache_runtime_record(prompt_id, seeded_record, fallback_text=prompt_text)
            return seeded_record
    except Exception:
        return _default_record(
            prompt_id,
            default_text,
            warning=(
                "Supabase prompt storage is unavailable. This prompt is using the default "
                "fallback and edits will not persist permanently."
            ),
        )

    return _default_record(prompt_id, default_text)


def get_prompt_record(prompt_id, default_text="", **kwargs):
    return load_prompt(prompt_id, default_text, **kwargs)


def get_prompt(prompt_id, default_text, **kwargs):
    return load_prompt(prompt_id, default_text, **kwargs).get("text") or ""


def get_prompt_source(prompt_id, default_text="", **kwargs):
    return load_prompt(prompt_id, default_text, **kwargs)


def save_prompt(prompt_id, title, text, *, module="", updated_by="sports_cave_os"):
    prompt_id = str(prompt_id or "").strip()
    if not prompt_id:
        raise ValueError("Prompt ID is missing.")
    edited_text = str(text or "")
    if not edited_text.strip():
        raise ValueError("Prompt text is empty.")
    try:
        record = _upsert_prompt_to_supabase(
            prompt_id,
            str(title or prompt_id),
            edited_text,
            module=module,
            updated_by=updated_by,
            source="supabase",
        )
        saved_record = {
            **record,
            "text": record.get("prompt_text") or edited_text,
            "source": SOURCE_SUPABASE,
            "source_label": source_label(SOURCE_SUPABASE),
            "persisted": True,
            "warning": "",
        }
        _cache_runtime_record(prompt_id, saved_record, fallback_text=edited_text)
        return saved_record
    except Exception:
        if _local_file_enabled():
            return _save_prompt_local_dev_only(prompt_id, title, edited_text)
        raise RuntimeError(
            "Prompt was not saved. Supabase prompt storage is unavailable, so this edit "
            "would not persist after Render restart or redeploy."
        )


def reset_prompt_to_default(prompt_id, title, default_text, *, module="", updated_by="sports_cave_os"):
    return save_prompt(
        prompt_id,
        title,
        str(default_text or ""),
        module=module,
        updated_by=updated_by,
    )


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


def _atomic_write_text(path, text):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    os.replace(tmp_path, path)


def save_prompt_store(payload):
    if not _local_file_enabled():
        raise RuntimeError(
            "Local prompt file writes are disabled. Set ENABLE_LOCAL_PROMPT_FILE_WRITES=true "
            "for local development only."
        )
    store = {"version": PROMPT_STORE_VERSION, "prompts": {}}
    if isinstance(payload, dict):
        store.update(payload)
    if not isinstance(store.get("prompts"), dict):
        store["prompts"] = {}
    store["version"] = PROMPT_STORE_VERSION
    store["updated_at"] = now_iso()
    _atomic_write_text(PROMPT_OVERRIDES_PATH, json.dumps(store, indent=2, sort_keys=True))
    return store


def _save_prompt_local_dev_only(prompt_id, title, text):
    store = load_prompt_store()
    prompts = dict(store.get("prompts") or {})
    prompts[prompt_id] = {
        "title": str(title or prompt_id),
        "text": str(text or ""),
        "updated_at": now_iso(),
    }
    store["prompts"] = prompts
    saved = save_prompt_store(store)["prompts"][prompt_id]
    local_record = {
        **saved,
        "prompt_key": prompt_id,
        "prompt_name": saved.get("title") or prompt_id,
        "prompt_text": saved.get("text") or "",
        "source": SOURCE_UNAVAILABLE,
        "source_label": "Not persisted — Supabase unavailable",
        "persisted": False,
        "warning": "Saved to local development file only. Render will not persist this change.",
    }
    _cache_runtime_record(prompt_id, local_record, fallback_text=text)
    return local_record
