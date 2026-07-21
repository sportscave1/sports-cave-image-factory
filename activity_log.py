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
    raise_errors=False,
):
    try:
        import supabase_backend

        return supabase_backend.record_activity_log(
            action_type=action_type,
            page=page,
            message=message,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata=metadata or {},
        )
    except Exception as error:
        logging.info("Activity log write skipped: %s", error)
        if raise_errors:
            raise ActivityLogError(str(error)) from error
    return None
