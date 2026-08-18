"""Stable registration and rendering for the Files sidebar launcher."""

from __future__ import annotations

import html
import logging
from pathlib import Path
from threading import Lock


LOGGER = logging.getLogger(__name__)
COMPONENT_NAME = "files_window_launcher"
COMPONENT_KEY = "files-window-launcher"
COMPONENT_DIR = Path(__file__).resolve().parent / "components" / COMPONENT_NAME
COMPONENT_ENTRYPOINT = COMPONENT_DIR / "index.html"

_REGISTRATION_LOCK = Lock()
_COMPONENT = None


def validate_component_assets() -> Path:
    """Return the packaged component directory or fail before mounting it."""

    if not COMPONENT_DIR.is_dir():
        raise FileNotFoundError(f"Files launcher component directory is missing: {COMPONENT_DIR}")
    if not COMPONENT_ENTRYPOINT.is_file():
        raise FileNotFoundError(f"Files launcher entrypoint is missing: {COMPONENT_ENTRYPOINT}")
    return COMPONENT_DIR


def get_component(components_module):
    """Declare the component once per process, outside the rerun-executed app module."""

    global _COMPONENT
    if _COMPONENT is not None:
        return _COMPONENT
    with _REGISTRATION_LOCK:
        if _COMPONENT is None:
            component_dir = validate_component_assets()
            _COMPONENT = components_module.declare_component(
                COMPONENT_NAME,
                path=str(component_dir),
            )
    return _COMPONENT


def fallback_link_html(*, label="Files", href="/files-window"):
    """Provide a same-origin Files entry point if Python registration fails."""

    return (
        '<a class="sc-files-window-launcher-fallback" '
        f'href="{html.escape(str(href), quote=True)}" target="_blank" rel="noopener">'
        f'{html.escape(str(label))}</a>'
    )


def render(st_module, components_module, *, key=COMPONENT_KEY):
    """Render the launcher with a compact, usable fallback on registration errors."""

    try:
        get_component(components_module)(key=key, default=None)
        return True
    except Exception as error:
        LOGGER.error(
            "Files launcher registration failed component=%s asset_dir=%s error_type=%s",
            COMPONENT_NAME,
            COMPONENT_DIR,
            type(error).__name__,
        )
        st_module.markdown(fallback_link_html(), unsafe_allow_html=True)
        return False
