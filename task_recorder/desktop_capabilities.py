"""Explicit feature negotiation, independent of the legacy numeric protocol."""
FORMAT = "sports-cave.desktop"


def supports(state, *, playback=False):
    value = state.get("desktop_capabilities", {})
    return (isinstance(value, dict) and value.get("format") == FORMAT and
            value.get("version") == 1 and 2 in value.get("action_versions", []) and
            value.get("playback" if playback else "capture") is True)
