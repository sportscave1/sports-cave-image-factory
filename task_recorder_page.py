"""Native OS dialog; all controls use same-origin, account-authenticated routes."""


def render_page(user):
    import os_accounts
    import streamlit as st
    if not os_accounts.is_admin(user):
        st.error("Task Recorder is available only to administrators.")
        return
    st.markdown("#### Task Recorder")
    from streamlit.components.v1 import iframe
    @st.dialog("Task Recorder", width="small")
    def recorder():
        iframe("/task-recorder/panel", height=480, scrolling=True)
    initial = not st.session_state.get("task_recorder_opened")
    if st.button("Open recorder", key="task_recorder_open"):
        recorder()
    elif initial:
        st.session_state["task_recorder_opened"] = True
        recorder()
