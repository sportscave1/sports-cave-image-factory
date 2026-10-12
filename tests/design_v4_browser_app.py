"""Local browser harness: real schedule + real isolated SQL; no production credentials."""
import sys
from pathlib import Path
import runpy
import time
import os
import importlib.util

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import streamlit as st
import design_studio_intelligence_store as intelligence
from tests import design_v4_fixture as fixture

st.session_state["sports_cave_authenticated"] = True
st.session_state["sports_cave_current_user"] = fixture.USER
st.session_state["sports_cave_auth_checked_at"] = time.monotonic()
st.session_state["selected_page"] = "Design Studio"

if os.environ.get("DESIGN_V4_BASELINE") == "1":
    for module in ("design_schedule", "design_studio_page"):
        spec = importlib.util.spec_from_file_location(module, Path("tmp/design-v4-baseline") / f"{module}.py")
        loaded = importlib.util.module_from_spec(spec)
        loaded.__file__ = str(Path(__file__).resolve().parents[1] / f"{module}.py")
        sys.modules[module] = loaded
        spec.loader.exec_module(loaded)

# Dialog fragments execute after the main run has returned. Keep the loopback
# adapter installed for the entire fixture process, including fragment reruns.
fixture.backend.connect = fixture.connect
fixture.backend.is_configured = lambda: True
fixture.dashboard.get_supabase_backend = lambda: fixture.backend
intelligence.load_sources = lambda *a, **kw: {"products": [], "lines": []}
if not hasattr(fixture.backend, "_v4_original_audit"):
    fixture.backend._v4_original_audit = fixture.backend._insert_audit_log


def fixture_audit(*args, **kwargs):
    if st.query_params.get("delete_failure") == "1":
        raise RuntimeError("isolated fixture audit failure")
    return fixture.backend._v4_original_audit(*args, **kwargs)


fixture.backend._insert_audit_log = fixture_audit
runpy.run_path(str(Path(__file__).resolve().parents[1] / "app.py"), run_name="__main__")
