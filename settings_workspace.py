"""Settings presentation; account mutations remain in the existing services."""
from pathlib import Path

import os_accounts


SECTIONS = ("General", "Users & Access", "Reporting", "Credentials", "Security & Account")
ADMIN_SECTIONS = frozenset({"Users & Access", "Credentials"})
ICONS = ("person", "group", "assessment", "key", "shield")
CSS = Path(__file__).with_suffix(".css").read_text(encoding="utf-8")


def rerun_settings(st):
    # Initial/full runs (including AppTest) cannot request a fragment-only rerun.
    from streamlit.errors import StreamlitAPIException
    try:
        st.rerun(scope="fragment")
    except StreamlitAPIException:
        st.rerun()


def section_allowed(user, section):
    return bool(
        os_accounts.account_is_active(user)
        and section in SECTIONS
        and (section not in ADMIN_SECTIONS or os_accounts.is_admin(user))
    )


def render_account_footer(st, user, current_page, route_button, allowed_routes, logout):
    st.html("<style>" + CSS + "</style>")
    footer = st.sidebar.container(key="sidebar-profile-footer")
    with footer:
        route_button("Accounts & Access", current_page, allowed_routes,
                     label="Settings", icon=":material/settings:", root=footer)
        name = str(user.get("display_name") or user.get("username") or "Account")
        role = str(user.get("role") or "Account").title()
        with st.popover(f"{name} · {role}", icon=":material/account_circle:",
                        width="stretch", key="settings-account-menu"):
            st.markdown("**Sports Cave OS**")
            st.text(name)
            if st.button("Log out", key="sidebar-logout", icon=":material/logout:"):
                logout()


def render_workspace(st, user, *, general, users, reporting, credentials, security):
    st.html("<style>" + CSS + "</style>")
    st.title("Settings")
    if not os_accounts.account_is_active(user):
        st.error("Sign in to access Settings.")
        return
    requested = st.session_state.get("settings-section", "General")
    if not section_allowed(user, requested):
        # Fail closed before invoking a renderer or loading any administrator data.
        st.warning("This settings section is not available to your account.")
        requested = "General"
        st.session_state["settings-section"] = requested
    with st.container(key="settings-workspace"):
        nav, content = st.columns([1, 4], gap="medium")
        with nav, st.container(key="settings-navigation"):
            for section, icon in zip(SECTIONS, ICONS):
                if section_allowed(user, section):
                    if st.button(section, icon=f":material/{icon}:",
                                 key=f"settings-nav-{section}", width="stretch",
                                 type="primary" if section == requested else "secondary"):
                        st.session_state["settings-section"] = section
                        rerun_settings(st)
        with content, st.container(key="settings-content"):
            st.subheader(requested)
            notice = st.session_state.pop("settings-notice", "")
            if notice:
                st.success(notice)
            handlers = dict(zip(SECTIONS, (general, users, reporting, credentials, security)))
            # Check again at the dispatch boundary, independently of visible navigation.
            if section_allowed(user, requested):
                handlers[requested]()


def render_user_picker(st, users, format_timestamp):
    with st.container(key="settings-user-toolbar"):
        title, add = st.columns([9, 1])
        title.caption(f"{len(users)} accounts · Select a user to manage access")
        if add.button("", icon=":material/add:", help="Create worker",
                      key="settings-add-worker"):
            st.session_state["settings-create-worker"] = True
            st.session_state.pop("settings-user-id", None)
    with st.container(key="settings-user-table"):
        with st.container(key="settings-user-head"):
            for column, label in zip(st.columns([2, 1, 1, 1, 1.5, .6]),
                                     ("User", "Role", "Country", "Status", "Last login", "Actions")):
                column.caption(label)
        for account in users:
            account_id = account["id"]
            with st.container(key=f"settings-user-row-{account_id}"):
                cols = st.columns([2, 1, 1, 1, 1.5, .6], vertical_alignment="center")
                name = str(account.get("display_name") or account.get("username") or "Account")
                clicked = cols[0].button(name, key=f"settings-user-{account_id}", type="tertiary")
                cols[1].text(str(account.get("role") or "").title())
                cols[2].text(account.get("country") or "—")
                cols[3].text("Removed" if os_accounts.account_is_removed(account) else
                             "Active" if account.get("is_active") else "Inactive")
                cols[4].text(format_timestamp(account["last_login_at"]) if account.get("last_login_at") else "Never")
                opened = cols[5].button("", icon=":material/edit:", help=f"Manage {name}",
                                       key=f"settings-edit-{account_id}")
                if clicked or opened:
                    st.session_state["settings-user-id"] = account_id
                    st.session_state["settings-create-worker"] = False
    creating = st.session_state.get("settings-create-worker", False)
    selected = st.session_state.get("settings-user-id")
    if creating or selected:
        if st.button("Close editor", icon=":material/close:", key="settings-close-editor"):
            st.session_state.pop("settings-user-id", None)
            st.session_state["settings-create-worker"] = False
            return None, False
    return selected, creating
