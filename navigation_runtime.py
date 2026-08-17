def active_disclosure_group(
    route,
    *,
    social_routes,
    seo_routes,
    reporting_routes=(),
    ads_routes=(),
):
    if route in social_routes:
        return "social"
    if route in seo_routes:
        return "seo"
    if route in reporting_routes:
        return "reporting"
    if route in ads_routes:
        return "ads"
    return ""


def initial_disclosure_group(
    route,
    *,
    stored,
    social_routes,
    seo_routes,
    reporting_routes=(),
    ads_routes=(),
):
    if stored is not None:
        return str(stored or "")
    return active_disclosure_group(
        route,
        social_routes=social_routes,
        seo_routes=seo_routes,
        reporting_routes=reporting_routes,
        ads_routes=ads_routes,
    )


def toggle_disclosure_group(current_group, clicked_group):
    current = str(current_group or "")
    clicked = str(clicked_group or "")
    return "" if current == clicked else clicked


def disclosure_parent_is_active(route, overview_route):
    return str(route or "") == str(overview_route or "")


def disclosure_child_routes(routes, overview_route):
    return tuple(route for route in routes if route != overview_route)


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
