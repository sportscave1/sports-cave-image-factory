"""Framework startup fixture, NOT a production app preview.

Only fabricated Home/Orders content and deliberate synthetic auth/data latency.
No production application, API routes, database, .env or worker imports.
"""
import time
import streamlit as st

st.set_page_config(page_title="Sports Cave OS — offline startup fixture", layout="wide")
st.session_state["run"] = st.session_state.get("run", 0) + 1
script_started = time.perf_counter()
auth_started = time.perf_counter()
auth_cached = st.session_state.get("fixture_authenticated", False)
if not auth_cached:
    time.sleep(.04)  # Synthetic auth only; not an account/network measurement.
    st.session_state["fixture_authenticated"] = True
auth_ms = (time.perf_counter()-auth_started)*1000
route = st.sidebar.radio("Workspace", ["Home", "Orders"])
st.html(f'<div id="startup-shell" data-route="{route}">Offline {route}</div>')


def saved_rows(route):
    snapshots = st.session_state.setdefault("fixture_saved_rows", {})
    if route in snapshots:
        return snapshots[route]
    time.sleep(.12)  # Synthetic saved-data I/O; never used by production.
    snapshots[route] = [dict(order=f"SYNTHETIC-{i:03}", product="Fixture artwork", quantity=1) for i in range(50)]
    return snapshots[route]


data_started = time.perf_counter()
rows = saved_rows(route)
data_ms = (time.perf_counter()-data_started)*1000
if route == "Home":
    st.subheader("This Week's Work — synthetic")
    for column, label in zip(st.columns(3), ["Completed", "Remaining", "Focused time"]):
        column.metric(label, 8)
else:
    st.subheader("Orders — synthetic")
    st.dataframe(rows, hide_index=True, height=360)
st.html(f'<div id="startup-ready" data-route="{route}" data-run="{st.session_state["run"]}" '
        f'data-auth-ms="{auth_ms:.3f}" data-auth-cached="{str(auth_cached).lower()}" '
        f'data-data-ms="{data_ms:.3f}" data-script-ms="{(time.perf_counter()-script_started)*1000:.3f}">'
        'Synthetic content complete</div>')
