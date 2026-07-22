import os

from starlette.routing import Route
from streamlit.web.server.starlette import App

from files_upload_api import FILES_UPLOAD_ROUTES


routes = [
    Route(path, endpoint, methods=list(methods))
    for path, endpoint, methods in FILES_UPLOAD_ROUTES
]
app = App("app.py", routes=routes)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8501")),
    )
