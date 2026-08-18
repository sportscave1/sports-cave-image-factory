"""Stable registration and rendering for the Files sidebar launcher."""

from __future__ import annotations

import html
import json
import logging
from pathlib import Path
from threading import Lock
from urllib.parse import quote


LOGGER = logging.getLogger(__name__)
COMPONENT_NAME = "files_window_launcher"
COMPONENT_KEY = "files-window-launcher"
COMPONENT_DIR = Path(__file__).resolve().parent / "components" / COMPONENT_NAME
COMPONENT_ENTRYPOINT = COMPONENT_DIR / "index.html"
FILES_WINDOW_NAME = "sports-cave-files-window"

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


def validate_relative_folder_path(relative_path: str) -> str:
    """Return a root-relative Files folder path without permitting traversal."""

    raw = str(relative_path or "")
    if (
        not raw
        or raw != raw.strip()
        or raw.startswith(("/", "\\"))
        or "\\" in raw
        or ":" in raw
        or "\x00" in raw
    ):
        raise ValueError("A valid Files folder path is required.")
    parts = raw.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise ValueError("The Files folder path must remain inside the configured root.")
    return "/".join(parts)


def files_window_href(relative_path: str) -> str:
    """Build a same-origin Files URL resolved against the configured root server-side."""

    clean_path = validate_relative_folder_path(relative_path)
    return f"/files-window?relative_path={quote(clean_path, safe='/')}"


def table_click_handler_html(*, relative_path: str) -> str:
    """Intercept Orders File links and reuse the named Sports Cave Files window."""

    clean_path = validate_relative_folder_path(relative_path)
    href = files_window_href(clean_path)
    return f"""
<script>
(() => {{
  const parentWindow = window.parent || window;
  const doc = parentWindow.document;
  const relativePath = {json.dumps(clean_path)};
  const href = {json.dumps(href)};
  const windowName = {json.dumps(FILES_WINDOW_NAME)};
  const features = [
    "popup=yes", "width=1280", "height=860", "left=80", "top=40",
    "resizable=yes", "scrollbars=yes", "noopener=no"
  ].join(",");
  const controller = new parentWindow.AbortController();

  function openFiles() {{
    const sharedLauncher = parentWindow.SportsCaveFilesWindow;
    if (sharedLauncher && typeof sharedLauncher.open === "function") {{
      sharedLauncher.open(relativePath);
      return;
    }}
    const popup = parentWindow.open(href, windowName, features);
    if (popup) {{
      popup.focus();
      return;
    }}
    parentWindow.open(href, "_blank");
  }}

  function click(event) {{
    const target = event.target;
    const link = target && target.closest
      ? target.closest('a[href*="/files-window?relative_path="]')
      : null;
    if (!link || String(link.textContent || "").trim() !== "Open") return;
    event.preventDefault();
    event.stopPropagation();
    openFiles();
  }}

  const lifecycle = {{destroy: () => controller.abort()}};
  parentWindow.SportsCaveOrdersFilesLauncher?.destroy?.();
  parentWindow.SportsCaveOrdersFilesLauncher = lifecycle;
  doc.addEventListener("click", click, {{capture: true, signal: controller.signal}});
  window.addEventListener("pagehide", () => {{
    if (parentWindow.SportsCaveOrdersFilesLauncher === lifecycle) lifecycle.destroy();
  }}, {{once: true}});
}})();
</script>
"""


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
