def active_disclosure_group(
    route,
    *,
    social_routes=(),
    seo_routes=(),
    reporting_routes=(),
    ads_routes=(),
    analytics_routes=(),
):
    if route in social_routes:
        return "social"
    if route in seo_routes:
        return "seo"
    if route in reporting_routes:
        return "reporting"
    if route in ads_routes:
        return "ads"
    if route in analytics_routes:
        return "analytics"
    return ""


def initial_disclosure_group(
    route,
    *,
    stored,
    social_routes=(),
    seo_routes=(),
    reporting_routes=(),
    ads_routes=(),
    analytics_routes=(),
):
    active = active_disclosure_group(
        route,
        social_routes=social_routes,
        seo_routes=seo_routes,
        reporting_routes=reporting_routes,
        ads_routes=ads_routes,
        analytics_routes=analytics_routes,
    )
    if active:
        return active
    if stored is not None:
        return str(stored or "")
    return ""


def toggle_disclosure_group(current_group, clicked_group):
    current = str(current_group or "")
    clicked = str(clicked_group or "")
    return "" if current == clicked else clicked


def disclosure_group_is_expanded(
    route,
    *,
    group,
    stored_group,
    force_open_routes=(),
):
    """Keep a route's owning disclosure visible across reruns and history changes."""
    if route in force_open_routes:
        return True
    return str(stored_group or "") == str(group or "")


def disclosure_parent_is_active(route, overview_route, *, family_routes=()):
    return (
        str(route or "") == str(overview_route or "")
        or route in tuple(family_routes or ())
    )


def disclosure_child_routes(routes, overview_route, *, include_overview=False):
    return tuple(
        route for route in routes
        if include_overview or route != overview_route
    )


def dispatch_selected(selected, handlers):
    try:
        renderer = handlers[selected]
    except KeyError as error:
        raise ValueError(f"Unknown selected view: {selected}") from error
    return renderer()


def resolve_route(
    *,
    session_route,
    query_route,
    query_value,
    last_synced_query,
    legacy_route="",
    default_route="Dashboard",
):
    """Resolve one route without allowing stale session state to undo browser history."""
    session_route = str(session_route or "")
    query_route = str(query_route or "")
    query_value = str(query_value or "")
    legacy_route = str(legacy_route or "")

    if last_synced_query is None:
        if query_route:
            return query_route, "url"
        return session_route or legacy_route or default_route, "restore"

    last_synced_query = str(last_synced_query or "")
    if query_value != last_synced_query:
        if query_route:
            return query_route, "history"
        if not query_value:
            return default_route, "history"
        return session_route or legacy_route or default_route, "invalid-url"

    return session_route or query_route or legacy_route or default_route, "session"


def route_transition(epoch, current_route, requested_route, source):
    """Create a small, display-safe route transition diagnostic payload."""
    return {
        "epoch": max(0, int(epoch or 0)) + 1,
        "from": str(current_route or ""),
        "to": str(requested_route or ""),
        "source": str(source or "user"),
        "status": "pending",
    }


def navigation_completion_is_current(
    *,
    response_route,
    response_epoch,
    current_route,
    current_epoch,
    pending_route="",
    pending_expected_epoch=0,
):
    """Pure mirror of the browser's latest-intent completion guard."""
    response_epoch = max(0, int(response_epoch or 0))
    current_epoch = max(0, int(current_epoch or 0))
    pending_expected_epoch = max(0, int(pending_expected_epoch or 0))
    response_route = str(response_route or "")
    current_route = str(current_route or "")
    pending_route = str(pending_route or "")
    if response_epoch < current_epoch:
        return False
    if pending_route and not response_route:
        return False
    if response_route and response_route != current_route:
        return False
    if pending_route and response_route and pending_route != response_route:
        return False
    if pending_expected_epoch and response_epoch < pending_expected_epoch:
        return False
    return True
