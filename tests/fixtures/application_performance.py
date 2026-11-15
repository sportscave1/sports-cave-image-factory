"""Offline production Analytics render with deterministic 60ms storage latency.

No credentials, live database, worker, email provider or Shopify calls.
"""
from pathlib import Path
import sys
import time
import json
import types
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import streamlit as st
import analytics_page

st.set_page_config(layout="wide")
if st.query_params.get("baseline") == "1":
    # Optional captured pre-change source, created by the documented benchmark command.
    baseline = Path(__file__).resolve().parents[2] / ".tmp-performance-baseline/analytics_page.py"
    analytics_page = types.ModuleType("baseline_analytics_page")
    exec(compile(baseline.read_text(encoding="utf-8-sig"), str(baseline), "exec"), analytics_page.__dict__)
st.session_state["full_runs"] = st.session_state.get("full_runs", 0) + 1
st.session_state.setdefault("queries", [])
st.sidebar.markdown("Sports Cave OS · Offline performance fixture")


class Store:
    def report_for_period(self, property_id, key, start, end):
        st.session_state.queries.append(key)
        time.sleep(.06)  # Simulated storage latency, never used by production code.
        return {"quality_status": "Complete", "fetched_at": "2026-10-08T00:00:00Z",
                "rows": [{"dimensions": {"pageTitle": "Example", "pagePathPlusQueryString": "/example",
                    "sessionDefaultChannelGroup": "Direct", "country": "Australia", "deviceCategory": "desktop"},
                    "metrics": {"activeUsers": 10, "sessions": 12, "screenPageViews": 18,
                                "engagementRate": .5, "keyEvents": 2}}]}


class OperationalReader:
    def shopify_operational_totals(self, *_):
        st.session_state.queries.append("operational")
        time.sleep(.06)
        return {"store_orders": 3}


route = st.radio("Workspace", ["Analytics", "Reporting", "Other page"], horizontal=True)
if route == "Analytics":
    analytics_page._inject_styles()
    store = Store()
    if hasattr(analytics_page, "_ReportDisplayStore"):
        from workspace_display_cache import session_cache
        store = analytics_page._ReportDisplayStore(store, session_cache(st.session_state, "fixture-cache", {"id": "offline"}))
    analytics_page._overview(store, "properties/offline", {
        "start_date": date(2026, 10, 1), "end_date": date(2026, 10, 7),
        "previous_start_date": date(2026, 9, 24), "previous_end_date": date(2026, 9, 30),
    }, {}, operational_reader=OperationalReader())
elif route == "Reporting":
    import reporting_page
    from datetime import datetime, timezone

    def archives(*args, **kwargs):
        st.session_state.queries.append("archives")
        return [{"id": "offline-report", "report_date": "2026-10-08", "status": "sent",
                 "subject": "Offline sample", "report_summary": {}}]

    def archive(*args):
        st.session_state.queries.append("archive-detail")
        return {"html_snapshot": "<p>Offline sample; no customer information.</p>"}

    def csv(*args):
        st.session_state.queries.append("archive-csv")
        return {"content": "example\n1", "filename": "offline.csv"}

    reporting_page.reporting_store.list_archives = archives
    reporting_page.reporting_store.get_archive = archive
    reporting_page.reporting_store.archive_csv = csv
    reporting_page._render_sent_reports({"id": "offline"}, True)
else:
    st.write("Other page ready")


@st.fragment
def profile():
    st.button("Read profile")
    st.session_state["profile_reads"] = st.session_state.get("profile_reads", 0) + 1
    st.html('<pre id="performance-profile">' + json.dumps({
        "full_runs": st.session_state.full_runs, "queries": st.session_state.queries,
        "profile_reads": st.session_state.profile_reads,
    }) + '</pre>')


profile()
