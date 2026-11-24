"""Actual Home panel and Orders loading functions, synthetic providers only.

Never imports app.py, sports_cave_server.py or production API routes. Original
sources are extracted via AST; operational table/actions are synthetic stand-ins.
"""
import ast
from concurrent.futures import TimeoutError as FutureTimeoutError
from datetime import date
from pathlib import Path
from types import SimpleNamespace, ModuleType
import sys
import time
import uuid
import subprocess

import streamlit as st

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from display_snapshot import Snapshots
from orders_read_executor import OrdersReadExecutor
from workspace_display_cache import user_scope

st.set_page_config(layout="wide")
mode=st.query_params.get("mode","after")
delay=float(st.query_params.get("delay",".3"))
fail_first=st.query_params.get("fail_first","0")=="1"
st.session_state["full_runs"]=st.session_state.get("full_runs",0)+1
st.session_state.setdefault("fixture_user",str(uuid.uuid4()))
st.session_state.setdefault("fixture_stats",dict(home=0,orders=0,auth=0))
stats=st.session_state["fixture_stats"]
user=dict(id=st.session_state["fixture_user"],session_version=1,role="worker",
          page_permissions=["orders"],is_active=True,account_status="active")
st.session_state["sports_cave_current_user"]=user
route=st.sidebar.radio("Workspace",["Other","Home","Orders"])
st.session_state["current_page"]={"Home":"Dashboard"}.get(route,route)
st.title("Local workspace shell")
st.html(f'<span id="fixture-runs">{st.session_state["full_runs"]}</span>')

def source_file(name):
    baseline=ROOT/".tmp-startup-phase3"/(Path(name).stem+"_before.py")
    if mode=="before":
        if baseline.is_file():
            return baseline.read_text(encoding="utf-8")
        return subprocess.check_output(["git","show",
            "333d9a9d481bb96c0c84fb42bbfa80a8a7f26d35:"+name],cwd=ROOT,text=True,encoding="utf-8")
    return (ROOT/name).read_text(encoding="utf-8")


@st.cache_resource
def resources(mode):
    cache=Snapshots(workers=3,limit=32,byte_limit=32_000_000)
    executor=OrdersReadExecutor()
    home_source=source_file("home_fast.py")
    module=ModuleType("phase3_home_"+mode)
    exec(compile(home_source,"<actual Home panel>","exec"),module.__dict__)
    module.SNAPSHOTS.close()
    module.SNAPSHOTS=cache
    return module,executor


home,executor=resources(mode)


def load_home():
    stats["home"]+=1
    time.sleep(delay)
    if fail_first and stats["home"]==1:
        raise RuntimeError("Synthetic first-read failure")
    return dict(text="Synthetic saved Home information")


def show_home(value):
    st.write(value["text"])
    st.html(f'<span id="home-ready" data-runs="{st.session_state["full_runs"]}">{stats["home"]}</span>')


if route=="Home":
    home.panel(st,user,date(2026,11,24),"Saved Home section",load_home,show_home)
elif route=="Orders":
    source=source_file("orders_page.py")
    ns=dict(st=st,time=time,FutureTimeoutError=FutureTimeoutError,user_scope=user_scope,
        _ORDERS_LOAD_EXECUTOR=executor,_perf_log=lambda *a,**k:None)
    tree=ast.parse(source)
    for node in tree.body:
        if isinstance(node,ast.Assign):
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            for name in node.targets:
                if isinstance(name,ast.Name):ns[name.id]=value
    names={"_start_snapshot_load","_consume_snapshot_load","_render_orders_loading_fragment",
           "_wait_for_snapshot_load","render_page","_render_orders_search_form"}
    nodes=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names]
    def ensure():
        for key,value in [(ns["ROWS_KEY"],[]),(ns["META_KEY"],{}),(ns["SNAPSHOT_LOADED_KEY"],False)]:
            st.session_state.setdefault(key,value)
    def read(search="",limit=75):
        stats["orders"]+=1
        time.sleep(delay)
        return dict(rows=[dict(order=f"SYNTHETIC-{i:03}",product=search or "Fixture artwork",
                               unit=i%2+1) for i in range(150)],search=search)
    def apply(payload):st.session_state[ns["ROWS_KEY"]]=payload["rows"]
    def error(exc,query):
        st.session_state[ns["LOAD_ERROR_KEY"]]="Synthetic database unavailable"
        st.session_state[ns["SNAPSHOT_LOADED_KEY"]]=True
    def data(selection_guard=None):
        if st.session_state.get(ns["LOAD_ERROR_KEY"]):st.error("Synthetic database unavailable")
        st.dataframe(st.session_state.get(ns["ROWS_KEY"],[]),hide_index=True,height=350)
        st.html(f'<span id="orders-ready" data-runs="{st.session_state["full_runs"]}" '
                f'data-row-count="{len(st.session_state.get(ns["ROWS_KEY"],[]))}" '
                f'data-query="{st.session_state.get(ns["LOADED_QUERY_KEY"],"")}">{stats["orders"]}</span>')
    ns.update(_ensure_state=ensure,_render_orders_styles=lambda:None,
        _async_orders_load_supported=lambda:True,_read_orders_snapshot=read,
        _apply_snapshot_payload=apply,_record_snapshot_load_error=error,
        _render_orders_data_area=data,_render_orders_supabase_live_refresh=lambda:None,
        ui_loading=SimpleNamespace(render_spinner=lambda:st.caption("Loading synthetic orders…")))
    exec(compile(ast.Module(body=nodes,type_ignores=[]),"<actual Orders loaders>","exec"),ns)
    app_source=source_file("app.py")
    workspace=next(node for node in ast.parse(app_source).body if isinstance(node,ast.FunctionDef)
                   and node.name=="_render_orders_workspace")
    def auth():
        stats["auth"]+=1
        return True
    def complete(*a,**k):st.html('<span id="orders-ack">Orders complete</span>')
    app_ns=dict(st=st,is_app_authenticated=auth,ensure_current_page_access=lambda p:True,
        get_orders_page=lambda:SimpleNamespace(render_page=ns["render_page"]),
        _orders_selection_access_allowed=lambda:True,_navigation_page_status=lambda p:"ready",
        _finish_navigation_transition=lambda *a,**k:None,
        top_bar=SimpleNamespace(render_navigation_complete=complete),
        get_components_module=lambda:None,NAVIGATION_EPOCH_STATE_KEY="epoch",
        current_os_user=lambda:st.session_state.get("sports_cave_current_user",{}),
        os_accounts=SimpleNamespace(is_admin=lambda u:False),logging=SimpleNamespace(exception=lambda *a:None),
        _render_navigation_failure=lambda p,e:st.exception(e))
    exec(compile(ast.Module(body=[workspace],type_ignores=[]),"<actual Orders workspace>","exec"),app_ns)
    app_ns["_render_orders_workspace"]()
else:
    st.html(f'<span id="other-ready" data-runs="{st.session_state["full_runs"]}">Other page ready</span>')
