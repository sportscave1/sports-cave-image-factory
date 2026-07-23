import os

from starlette.routing import Route
from streamlit.web.server.starlette import App

import collector_vault
from collector_vault_api import COLLECTOR_VAULT_ROUTES
from files_upload_api import FILES_UPLOAD_ROUTES


routes = [
    Route(path, endpoint, methods=list(methods))
    for path, endpoint, methods in (*FILES_UPLOAD_ROUTES, *COLLECTOR_VAULT_ROUTES)
]
app = App("app.py", routes=routes)


if __name__ == "__main__":
    import uvicorn

    collector_vault.log_collector_vault_readiness(check_shopify=True)
    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8501")),
    )
