"""Production sidebar/top-bar/recovery scripts with no application data services."""
from pathlib import Path
import runpy

namespace = runpy.run_path(str(Path(__file__).with_name("home_shell_preview.py")))
st = namespace["st"]
import session_recovery
session_recovery.install(st)
st.button("Local shell rerun")
st.session_state["shell_fixture_runs"] = st.session_state.get("shell_fixture_runs", 0) + 1
st.html(f'<span id="shell-fixture-runs">{st.session_state.shell_fixture_runs}</span>')
namespace["top_bar"].render_navigation_complete(namespace["components"], current_route=namespace["get_current_page"]())
