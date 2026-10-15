"""Actual Settings renderers with synthetic, memory-only accounts. No app startup."""
import ast
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import streamlit as st
import os_accounts
import shared_credentials
import html
import json
import hashlib
import time
import base64
import streamlit.components.v1 as components
import top_bar
from tests.test_os_accounts import FakeAccountStore
from sidebar_theme import SIDEBAR_CSS
from settings_workspace import render_account_footer
from page_presentation import inject_compact_page

st.set_page_config(layout="wide", initial_sidebar_state="expanded")

if "fixture-store" not in st.session_state:
    store = FakeAccountStore()
    for role, name, country in (("admin", "Local Admin", "Australia"),
                                ("worker", "Local Worker", "Philippines")):
        store.create_user(username=role, email=f"{role}@example.test", display_name=name,
                          password_hash=os_accounts.hash_password("Local password 26!"),
                          role=role, country=country, page_keys=("dashboard", "orders"))
    st.session_state["fixture-store"] = store
store = st.session_state["fixture-store"]
role = st.session_state.get("fixture-role", st.query_params.get("role", "admin"))
user = store.get_user("user-1" if role == "admin" else "user-2")
st.session_state["fixture-user"] = user

tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
names = {"render_accounts_access_page", "render_settings_users_section", "render_settings_security_section",
         "render_my_profile_section", "render_reporting_permission_section", "render_passwords_section",
         "_sidebar_route_button", "_sidebar_route_clicked", "logout_app", "inject_styles"}
start = next(n.lineno for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_account_permission_fields")
end = next(n.lineno for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "render_settings_page")
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and (start <= n.lineno < end or n.name in names)]
for node in nodes:
    if node.name == "render_accounts_access_page":
        node.decorator_list = []
namespace = dict(globals())
namespace['__file__'] = str(ROOT / 'app.py')
namespace.update(
    current_os_user=lambda: st.session_state["fixture-user"],
    _refresh_session_account_if_due=lambda user: store.get_user(user["id"]),
    alphabetize_options=lambda values, **kwargs: sorted(values, key=kwargs.get("label", str)),
    selected_option_index=lambda options, selected: list(options).index(selected),
    format_dashboard_timestamp=lambda value: str(value),
    record_activity_log=lambda *a, **k: None,
    _record_credential_permission_changes=lambda *a: None,
    _set_authenticated_user=lambda value, **kwargs: st.session_state.update({"fixture-user": value}),
    _clear_authenticated_session_state=lambda: st.session_state.update({"fixture-logged-out": True}),
    clear_auth_cookie=lambda: st.session_state.update({"fixture-cookie-cleared": True}),
    set_current_page=lambda *a, **k: None,
    SIDEBAR_NAV_LABELS={}, SIDEBAR_ICON_BY_ROUTE={},
    ACCOUNT_ACCESS_DIALOG_KEY="account_access_dialog",
)
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "app.py"), "exec"), namespace)
namespace["_record_credential_permission_changes"] = lambda *a: None

with patch("top_bar_security.create_top_bar_token", return_value="offline-settings"):
    bar = top_bar.top_bar_config(user, current_route="Accounts & Access",
        logo_src="data:image/webp;base64," + base64.b64encode(
            (ROOT / "assets/sports-cave-os-app-icon.webp").read_bytes()).decode())
bar.update(dailyPlannerEnabled=False, dailyPlannerStatusUrl="", notificationsUrl="",
           orderStatusUrl="", emailStatusUrl="", searchUrl="", repairRequestsUrl="", emailEventsUrl="")
components.html(top_bar.component_html(bar), height=0)
namespace["inject_styles"]()
inject_compact_page(st)
st.sidebar.markdown("**Sports Cave OS**")
st.sidebar.button("Home", icon=":material/home:")
st.sidebar.button("Orders", icon=":material/shopping_bag:")
render_account_footer(st, user, "Accounts & Access", namespace["_sidebar_route_button"],
                      ("Accounts & Access",), namespace["logout_app"])

# A browser or AppTest may mutate only the in-memory store. External I/O fails closed.
@st.fragment
def preview_settings():
    with patch.object(os_accounts, "DEFAULT_STORE", store), \
         patch("requests.sessions.Session.request", side_effect=AssertionError("External I/O forbidden")), \
         patch("supabase_backend.connect", side_effect=AssertionError("External SQL forbidden")):
        namespace["render_accounts_access_page"]()


preview_settings()
