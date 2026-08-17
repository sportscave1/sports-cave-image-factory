import contextvars
import logging


class ActivityLogError(RuntimeError):
    pass


_ACTIVITY_ACTOR = contextvars.ContextVar(
    "sports_cave_activity_actor",
    default="sports_cave_os",
)
_ACTIVITY_ACTOR_METADATA = contextvars.ContextVar(
    "sports_cave_activity_actor_metadata",
    default={},
)


def set_activity_actor(actor, metadata=None):
    clean_actor = str(actor or "").strip() or "sports_cave_os"
    _ACTIVITY_ACTOR.set(clean_actor[:200])
    safe_metadata = {}
    for key in ("actor_id", "actor_email", "actor_role", "actor_country", "actor_timezone"):
        value = (metadata or {}).get(key)
        if value not in (None, ""):
            safe_metadata[key] = str(value)[:250]
    _ACTIVITY_ACTOR_METADATA.set(safe_metadata)


def clear_activity_actor():
    _ACTIVITY_ACTOR.set("sports_cave_os")
    _ACTIVITY_ACTOR_METADATA.set({})


def get_activity_actor():
    return _ACTIVITY_ACTOR.get()


def get_activity_actor_metadata():
    return dict(_ACTIVITY_ACTOR_METADATA.get() or {})


def _safe_activity_metadata(metadata, *, page, action_type, actor):
    clean = {
        key: value
        for key, value in dict(metadata or {}).items()
        if key not in {"password", "password_hash", "token", "access_token", "refresh_token", "secret"}
    }
    actor_metadata = dict(_ACTIVITY_ACTOR_METADATA.get() or {})
    for key, value in actor_metadata.items():
        clean.setdefault(key, value)
    clean.setdefault("actor_display", str(actor or "").strip() or "sports_cave_os")
    clean.setdefault("page_area", str(page or "").strip() or "Sports Cave")
    clean.setdefault("action_key", str(action_type or "").strip() or "activity")
    clean.setdefault("source_user_initiated", True)
    clean.setdefault("status", "success")
    if clean.get("actor_id"):
        clean.setdefault("origin", "human")
    return clean


def record_activity_log(
    action_type,
    page,
    message,
    *,
    entity_type="",
    entity_id="",
    metadata=None,
    event_key="",
    actor="",
    raise_errors=False,
):
    try:
        import supabase_backend

        clean_actor = str(actor or "").strip() or _ACTIVITY_ACTOR.get()
        clean_metadata = _safe_activity_metadata(
            metadata,
            page=page,
            action_type=action_type,
            actor=clean_actor,
        )
        row = supabase_backend.record_activity_log(
            action_type=action_type,
            page=page,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=clean_metadata,
            event_key=event_key,
            actor=clean_actor,
        )
        try:
            import sports_cave_dashboard

            sports_cave_dashboard.clear_activity_cache()
        except Exception:
            pass
        return row
    except Exception as error:
        logging.info("Activity log write skipped: %s", error)
        if raise_errors:
            raise ActivityLogError(str(error)) from error
    return None
