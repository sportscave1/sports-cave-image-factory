"""Local-only readiness-route fixture. Email/SQL are replaced by the preview."""
from starlette.routing import Route
from streamlit.web.server.starlette import App
from support_email_completion import PATH, read_ready

app = App('tests/fixtures/email_v2c_preview.py', routes=[Route(PATH, read_ready, methods=['GET'])])
