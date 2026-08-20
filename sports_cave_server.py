import logging
import os

from starlette.routing import Route
from streamlit.web.server.starlette import App

import app_branding
import collector_vault
from collector_vault_api import COLLECTOR_VAULT_ROUTES
from daily_planner import DAILY_PLANNER_ROUTE_HANDLERS
from files_upload_api import FILES_UPLOAD_ROUTES
import google_seo
from google_seo_api import GOOGLE_SEO_ROUTE_HANDLERS
import run_migrations
from top_bar_api import TOP_BAR_ROUTE_HANDLERS


routes = [
    Route(path, endpoint, methods=list(methods))
    for path, endpoint, methods in (
        *FILES_UPLOAD_ROUTES,
        *COLLECTOR_VAULT_ROUTES,
        *DAILY_PLANNER_ROUTE_HANDLERS,
        *TOP_BAR_ROUTE_HANDLERS,
        *GOOGLE_SEO_ROUTE_HANDLERS,
    )
]
routes.extend(app_branding.public_branding_routes())


MAIN_HEALTH_PATHS = frozenset({"/_stcore/health", "/healthz"})


class ConstantTimeHealthMiddleware:
    """Answer Render liveness checks without consulting Streamlit or storage.

    Render currently checks Streamlit's ``/_stcore/health`` path.  Keep that
    public contract, but make liveness independent of Streamlit runtime state,
    sessions, database locks, and external services.  ``/healthz`` is exposed
    as the explicit equivalent for local verification and any future Render
    configuration change.
    """

    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path") in MAIN_HEALTH_PATHS:
            method = str(scope.get("method") or "GET").upper()
            status = 204 if method == "OPTIONS" else 200
            body = b"" if method in {"HEAD", "OPTIONS"} else b"ok\n"
            await send(
                {
                    "type": "http.response.start",
                    "status": status,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"cache-control", b"no-store"),
                        (b"content-length", str(len(body)).encode("ascii")),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
            return
        await self.application(scope, receive, send)


class _GoogleOAuthAccessLogFilter(logging.Filter):
    def filter(self, record):
        return google_seo.GOOGLE_OAUTH_CALLBACK_PATH not in record.getMessage()

logging.getLogger("uvicorn.access").addFilter(_GoogleOAuthAccessLogFilter())
streamlit_app = App("app.py", routes=routes)
app = ConstantTimeHealthMiddleware(
    app_branding.InitialDocumentBrandingMiddleware(streamlit_app)
)


def prepare_google_seo_storage():
    database_url, _source = run_migrations.get_database_url()
    if not database_url:
        return False
    for filename in google_seo.GOOGLE_SEO_PIPELINE_MIGRATIONS:
        run_migrations.run_migrations(only=filename)
    try:
        import google_seo_phase4

        repair = google_seo_phase4.ensure_initial_gsc_reporting_repair(
            schema_ready=True
        )
        logging.info(
            "Initial GSC reporting repair enqueue status=%s reason=%s",
            str(repair.get("status") or "unknown"),
            str(repair.get("reason") or ""),
        )
        import google_seo_import

        totals_repair = google_seo_import.default_import_store().ensure_gsc_property_totals_repair(
            schema_ready=True
        )
        logging.info(
            "Initial GSC property totals repair enqueue status=%s reason=%s",
            str(totals_repair.get("status") or "unknown"),
            str(totals_repair.get("reason") or ""),
        )
    except Exception as error:
        # GSC imports also queue revision-triggered repairs. A transient queue
        # inspection failure must not turn an otherwise valid schema migration
        # into another web-service startup failure.
        logging.warning(
            "Initial GSC reporting repair enqueue deferred code=%s",
            str(getattr(error, "code", "enqueue_failed")),
        )
    return True


if __name__ == "__main__":
    import uvicorn

    prepare_google_seo_storage()
    # Readiness logging is diagnostic only. Never delay port binding on a
    # Shopify Admin API call during a process restart.
    collector_vault.log_collector_vault_readiness(check_shopify=False)
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8501")),
    )
