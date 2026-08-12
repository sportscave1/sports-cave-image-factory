"""Installed-app branding metadata for Sports Cave OS."""

from __future__ import annotations

from textwrap import dedent


APP_NAME = "Sports Cave OS"
APP_THEME_COLOR = "#171510"
APP_BACKGROUND_COLOR = "#FAF8F1"
APP_MANIFEST_URL = "/app/static/sports-cave-os-v1.webmanifest"
APP_ICON_192_URL = "/app/static/branding/sports-cave-os-icon-192-v1.png"
APP_ICON_512_URL = "/app/static/branding/sports-cave-os-icon-512-v1.png"
APP_MASKABLE_ICON_URL = (
    "/app/static/branding/sports-cave-os-icon-maskable-512-v1.png"
)
APP_APPLE_TOUCH_ICON_URL = (
    "/app/static/branding/sports-cave-os-apple-touch-icon-180-v1.png"
)


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
              element.setAttribute(name, value);
            }});
            if (!element.parentNode) doc.head.appendChild(element);

            Array.from(doc.head.querySelectorAll(selector)).forEach((duplicate) => {{
              if (duplicate !== element) duplicate.remove();
            }});
          }};

          doc.title = {APP_NAME!r};

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
            attrs: {{
              name: "msapplication-TileImage",
              content: {APP_MASKABLE_ICON_URL!r},
            }},
          }});
        }})();
        </script>
        """
    ).strip()


def render_install_metadata(components) -> None:
    """Install PWA metadata without adding visible layout height."""
    components.html(install_metadata_html(), height=0, width=0)
