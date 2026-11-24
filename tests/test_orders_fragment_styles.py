"""Real Streamlit layout ownership; no business app or provider imports."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mobile", [False, True])
def test_actual_orders_styles_are_owned_by_parallel_fragment(mobile):
    source = '''
import ast
import builtins
from pathlib import Path
from types import SimpleNamespace
import streamlit as st

root = Path(ROOT_PATH)
tree = ast.parse((root / "orders_page.py").read_text(encoding="utf-8"))
names = {"_render_orders_styles", "_render_mobile_orders"}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
real_import = builtins.__import__
def isolated_import(name, *args, **kwargs):
    if name == "auto_editions_runtime":
        return SimpleNamespace(enabled=lambda: False)
    return real_import(name, *args, **kwargs)
ns = dict(st=st, Path=Path, __file__=str(root / "orders_page.py"),
    __builtins__={**vars(builtins), "__import__": isolated_import},
    _order_display_resources=lambda rows: ({}, {}),
    _mobile_unit_id=lambda row: "synthetic",
    _mobile_toggle=lambda *args: None,
    order_refunds=SimpleNamespace(state=lambda row: {"closed": True}),
    psd_directory=SimpleNamespace(link=lambda *args: "", product_id=lambda row: "fixture",
        render_missing_link_guard=lambda target: None),
    print_jpg=SimpleNamespace(state=lambda *args: {"label": "Synthetic", "reason": "Fixture"}),
    edition_test=SimpleNamespace(eligible=lambda *args: False),
    os_accounts=SimpleNamespace(is_admin=lambda user: False))
exec(compile(ast.Module(body=nodes, type_ignores=[]), "<actual Orders styles>", "exec"), ns)
st.session_state["full_runs"] = st.session_state.get("full_runs", 0) + 1
@st.fragment(parallel=True)
def workspace():
    if MOBILE:
        ns["_render_mobile_orders"]([dict(order="Synthetic", edition="1", product="Fixture",
            customer="Synthetic", variant_full="Black", shipping_method="Standard",
            date="2026-11-24", prodigi="Refunded")])
    else:
        ns["_render_orders_styles"]()
        st.text_input("Search orders", key="orders_search_text")
    st.button("Refresh fragment styles")
    st.caption("Orders styles ready")
workspace()
'''
    source = source.replace("ROOT_PATH", repr(str(ROOT))).replace("MOBILE", repr(mobile))
    app = AppTest.from_string(source).run(timeout=15)
    assert not app.exception
    assert any(c.value == "Orders styles ready" for c in app.caption)
    # The complete actual CSS, including the refunded-card rule, must survive.
    assert any("<style>" in m.value for m in app.markdown)
    if mobile:
        assert any("line-through" in m.value for m in app.markdown)
    app.button[0].click().run(timeout=15)
    assert not app.exception
    assert any(c.value == "Orders styles ready" for c in app.caption)
