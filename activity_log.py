import contextvars
import logging


class ActivityLogError(RuntimeError):
    pass


_ACTIVITY_ACTOR = contextvars.ContextVar(
    "sports_cave_activity_actor",
    default="sports_cave_os",
)


def set_activity_actor(actor):
    clean_actor = str(actor or "").strip() or "sports_cave_os"
    _ACTIVITY_ACTOR.set(clean_actor[:200])


def clear_activity_actor():
    _ACTIVITY_ACTOR.set("sports_cave_os")


def get_activity_actor():
    return _ACTIVITY_ACTOR.get()


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

        row = supabase_backend.record_activity_log(
            action_type=action_type,
            page=page,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata or {},
            event_key=event_key,
            actor=str(actor or "").strip() or _ACTIVITY_ACTOR.get(),
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
