def active_disclosure_group(route, *, social_routes, seo_routes):
    if route in social_routes:
        return "social"
    if route in seo_routes:
        return "seo"
    return ""


def initial_disclosure_group(route, *, stored, social_routes, seo_routes):
    if stored is not None:
        return str(stored or "")
    return active_disclosure_group(
        route,
        social_routes=social_routes,
        seo_routes=seo_routes,
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
