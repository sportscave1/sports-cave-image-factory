"""Installed-app branding metadata for Sports Cave OS."""

from __future__ import annotations

import gzip
from pathlib import Path
import re
from textwrap import dedent


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
BRANDING_ROOT = STATIC_ROOT / "branding"

APP_NAME = "Sports Cave OS"
APP_THEME_COLOR = "#171510"
APP_BACKGROUND_COLOR = "#FAF8F1"
APP_ICON_SOURCE = "assets/sports-cave-os-app-icon.webp"

# Keep the manifest URL stable while cache-busting every icon selected by a
# fresh Chromium installation.
APP_MANIFEST_URL = "/app/static/sports-cave-os-v1.webmanifest"
APP_FAVICON_ICO_URL = "/favicon.ico"
APP_FAVICON_PNG_URL = (
    "/app/static/branding/sports-cave-os-favicon-32-v2.png"
)
APP_ICON_192_URL = "/app/static/branding/sports-cave-os-icon-192-v2.png"
APP_ICON_512_URL = "/app/static/branding/sports-cave-os-icon-512-v2.png"
APP_MASKABLE_ICON_URL = (
    "/app/static/branding/sports-cave-os-icon-maskable-512-v2.png"
)
APP_APPLE_TOUCH_ICON_URL = (
    "/app/static/branding/sports-cave-os-apple-touch-icon-180-v2.png"
)
APP_MS_TILE_ICON_URL = (
    "/app/static/branding/sports-cave-os-ms-tile-144-v2.png"
)

FAVICON_ICO_PATH = BRANDING_ROOT / "sports-cave-os-favicon-v2.ico"
FAVICON_PNG_PATH = BRANDING_ROOT / "sports-cave-os-favicon-32-v2.png"
APPLE_TOUCH_ICON_PATH = (
    BRANDING_ROOT / "sports-cave-os-apple-touch-icon-180-v2.png"
)
MS_TILE_ICON_PATH = BRANDING_ROOT / "sports-cave-os-ms-tile-144-v2.png"

_INITIAL_METADATA_START = "<!-- SPORTS_CAVE_OS_INSTALL_METADATA_START -->"
_INITIAL_METADATA_END = "<!-- SPORTS_CAVE_OS_INSTALL_METADATA_END -->"
_TITLE_PATTERN = re.compile(r"<title\b[^>]*>.*?</title>", re.IGNORECASE | re.DOTALL)
_ICON_LINK_PATTERN = re.compile(
    r"\s*<link\b(?=[^>]*\brel\s*=\s*['\"](?:shortcut\s+icon|icon|apple-touch-icon)['\"])[^>]*?/?>",
    re.IGNORECASE,
)
_MANIFEST_LINK_PATTERN = re.compile(
    r"\s*<link\b(?=[^>]*\brel\s*=\s*['\"]manifest['\"])[^>]*?/?>",
    re.IGNORECASE,
)
_MANAGED_META_PATTERN = re.compile(
    r"\s*<meta\b(?=[^>]*\bname\s*=\s*['\"](?:theme-color|application-name|mobile-web-app-capable|apple-mobile-web-app-capable|apple-mobile-web-app-title|msapplication-TileColor|msapplication-TileImage|msapplication-starturl)['\"])[^>]*?/?>",
    re.IGNORECASE,
)
_MANAGED_BLOCK_PATTERN = re.compile(
    r"\s*"
    + re.escape(_INITIAL_METADATA_START)
    + r".*?"
    + re.escape(_INITIAL_METADATA_END)
    + r"\s*",
    re.DOTALL,
)


def initial_document_metadata_html() -> str:
    """Return metadata that must be present in the top-level initial HTML."""
    return dedent(
        f"""
        {_INITIAL_METADATA_START}
        <meta name="theme-color" content="{APP_THEME_COLOR}" />
        <meta name="application-name" content="{APP_NAME}" />
        <meta name="mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-capable" content="yes" />
        <meta name="apple-mobile-web-app-title" content="{APP_NAME}" />
        <meta name="msapplication-TileColor" content="{APP_THEME_COLOR}" />
        <meta name="msapplication-TileImage" content="{APP_MS_TILE_ICON_URL}" />
        <meta name="msapplication-starturl" content="/?page=dashboard" />
        <link rel="manifest" href="{APP_MANIFEST_URL}" />
        <link rel="shortcut icon" type="image/x-icon" href="{APP_FAVICON_ICO_URL}" />
        <link rel="icon" type="image/x-icon" href="{APP_FAVICON_ICO_URL}" />
        <link rel="icon" type="image/png" sizes="32x32" href="{APP_FAVICON_PNG_URL}" />
        <link rel="icon" type="image/png" sizes="192x192" href="{APP_ICON_192_URL}" />
        <link rel="icon" type="image/png" sizes="512x512" href="{APP_ICON_512_URL}" />
        <link rel="apple-touch-icon" sizes="180x180" href="{APP_APPLE_TOUCH_ICON_URL}" />
        {_INITIAL_METADATA_END}
        """
    ).strip()


def brand_initial_document(document_html: str) -> str:
    """Apply singular install metadata to the initial Streamlit document."""
    html = str(document_html or "")
    html = _MANAGED_BLOCK_PATTERN.sub("", html)
    html = _ICON_LINK_PATTERN.sub("", html)
    html = _MANIFEST_LINK_PATTERN.sub("", html)
    html = _MANAGED_META_PATTERN.sub("", html)

    title = f"<title>{APP_NAME}</title>"
    if _TITLE_PATTERN.search(html):
        html = _TITLE_PATTERN.sub(title, html, count=1)
    elif "</head>" in html:
        html = html.replace("</head>", f"  {title}\n  </head>", 1)

    metadata = initial_document_metadata_html()
    if "</head>" not in html:
        return html
    html = re.sub(r"\s*</head>", "\n</head>", html, count=1, flags=re.IGNORECASE)
    return html.replace("</head>", f"{metadata}\n</head>", 1)


def install_metadata_html() -> str:
    """Return an idempotent parent-document metadata installer."""
    return dedent(
        f"""
        <script>
        (() => {{
          const parentWindow = window.parent || window;
          const doc = parentWindow.document;

          const upsertHeadElement = ({{ id, selector, tag, attrs }}) => {{
            const matches = Array.from(doc.head.querySelectorAll(selector));
            const managed = doc.getElementById(id);
            const element = managed || matches.shift() || doc.createElement(tag);

            element.id = id;
            Object.entries(attrs).forEach(([name, value]) => {{
              if (element.getAttribute(name) !== value) {{
                element.setAttribute(name, value);
              }}
            }});
            if (!element.parentNode) doc.head.appendChild(element);

            Array.from(doc.head.querySelectorAll(selector)).forEach((duplicate) => {{
              if (duplicate !== element) duplicate.remove();
            }});
          }};

          const applyBranding = () => {{
            if (doc.title !== {APP_NAME!r}) doc.title = {APP_NAME!r};

            upsertHeadElement({{
              id: "sports-cave-os-manifest",
              selector: 'link[rel="manifest"]',
              tag: "link",
              attrs: {{ rel: "manifest", href: {APP_MANIFEST_URL!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-theme-color",
              selector: 'meta[name="theme-color"]',
              tag: "meta",
              attrs: {{ name: "theme-color", content: {APP_THEME_COLOR!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-application-name",
              selector: 'meta[name="application-name"]',
              tag: "meta",
              attrs: {{ name: "application-name", content: {APP_NAME!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-mobile-capable",
              selector: 'meta[name="mobile-web-app-capable"]',
              tag: "meta",
              attrs: {{ name: "mobile-web-app-capable", content: "yes" }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-apple-capable",
              selector: 'meta[name="apple-mobile-web-app-capable"]',
              tag: "meta",
              attrs: {{ name: "apple-mobile-web-app-capable", content: "yes" }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-apple-title",
              selector: 'meta[name="apple-mobile-web-app-title"]',
              tag: "meta",
              attrs: {{ name: "apple-mobile-web-app-title", content: {APP_NAME!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-shortcut-icon",
              selector: 'link[rel="shortcut icon"]',
              tag: "link",
              attrs: {{ rel: "shortcut icon", type: "image/x-icon", href: {APP_FAVICON_ICO_URL!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-favicon-ico",
              selector: 'link[rel="icon"][type="image/x-icon"]',
              tag: "link",
              attrs: {{ rel: "icon", type: "image/x-icon", href: {APP_FAVICON_ICO_URL!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-favicon-png",
              selector: 'link[rel="icon"][sizes="32x32"]',
              tag: "link",
              attrs: {{ rel: "icon", type: "image/png", sizes: "32x32", href: {APP_FAVICON_PNG_URL!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-apple-touch-icon",
              selector: 'link[rel="apple-touch-icon"]',
              tag: "link",
              attrs: {{
                rel: "apple-touch-icon",
                sizes: "180x180",
                href: {APP_APPLE_TOUCH_ICON_URL!r},
              }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-png-icon-192",
              selector: 'link[rel="icon"][sizes="192x192"]',
              tag: "link",
              attrs: {{
                rel: "icon",
                type: "image/png",
                sizes: "192x192",
                href: {APP_ICON_192_URL!r},
              }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-png-icon-512",
              selector: 'link[rel="icon"][sizes="512x512"]',
              tag: "link",
              attrs: {{
                rel: "icon",
                type: "image/png",
                sizes: "512x512",
                href: {APP_ICON_512_URL!r},
              }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-ms-tile-color",
              selector: 'meta[name="msapplication-TileColor"]',
              tag: "meta",
              attrs: {{ name: "msapplication-TileColor", content: {APP_THEME_COLOR!r} }},
            }});
            upsertHeadElement({{
              id: "sports-cave-os-ms-tile-image",
              selector: 'meta[name="msapplication-TileImage"]',
              tag: "meta",
              attrs: {{ name: "msapplication-TileImage", content: {APP_MS_TILE_ICON_URL!r} }},
            }});
          }};

          applyBranding();
        }})();
        </script>
        """
    ).strip()


def render_install_metadata(components) -> None:
    """Install PWA metadata without adding visible layout height."""
    components.html(install_metadata_html(), height=0, width=0)


def public_branding_routes():
    """Return unauthenticated root icon fallbacks for browser installation."""
    from starlette.responses import FileResponse
    from starlette.routing import Route

    declarations = (
        ("/favicon.ico", FAVICON_ICO_PATH, "image/x-icon"),
        ("/favicon.png", FAVICON_PNG_PATH, "image/png"),
        ("/apple-touch-icon.png", APPLE_TOUCH_ICON_PATH, "image/png"),
        ("/mstile-144x144.png", MS_TILE_ICON_PATH, "image/png"),
    )

    routes = []
    for url, path, media_type in declarations:
        async def endpoint(_request, *, asset_path=path, content_type=media_type):
            return FileResponse(
                asset_path,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )

        routes.append(Route(url, endpoint, methods=["GET", "HEAD"]))
    return routes


class InitialDocumentBrandingMiddleware:
    """Brand the production HTML shell before Chromium evaluates install data."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        app_shell_paths = {"/", "/app", "/app/"}
        if (
            scope.get("type") != "http"
            or scope.get("method") != "GET"
            or scope.get("path") not in app_shell_paths
        ):
            await self.app(scope, receive, send)
            return

        messages = []

        async def capture(message):
            messages.append(message)

        await self.app(scope, receive, capture)
        if not messages or messages[0].get("type") != "http.response.start":
            for message in messages:
                await send(message)
            return

        start = messages[0]
        headers = list(start.get("headers", []))
        header_map = {
            key.decode("latin-1").casefold(): value.decode("latin-1")
            for key, value in headers
        }
        if "text/html" not in header_map.get("content-type", "").casefold():
            for message in messages:
                await send(message)
            return

        body = b"".join(
            message.get("body", b"")
            for message in messages[1:]
            if message.get("type") == "http.response.body"
        )
        content_encoding = header_map.get("content-encoding", "").casefold()
        if content_encoding == "gzip":
            body = gzip.decompress(body)
        elif content_encoding:
            for message in messages:
                await send(message)
            return

        branded = brand_initial_document(body.decode("utf-8")).encode("utf-8")
        if content_encoding == "gzip":
            branded = gzip.compress(branded, mtime=0)

        excluded_headers = {b"content-length", b"etag", b"content-md5"}
        headers = [
            (key, value)
            for key, value in headers
            if key.lower() not in excluded_headers
        ]
        headers.append((b"content-length", str(len(branded)).encode("ascii")))
        await send({**start, "headers": headers})
        await send({"type": "http.response.body", "body": branded})
