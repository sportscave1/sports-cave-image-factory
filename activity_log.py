import logging


class ActivityLogError(RuntimeError):
    pass


def record_activity_log(
    action_type,
    page,
    message,
    *,
    entity_type="",
    entity_id="",
    metadata=None,
    event_key="",
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
