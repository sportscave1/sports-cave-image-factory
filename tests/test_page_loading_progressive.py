"""Completion, isolation and cancellation contracts; synthetic reads only."""
import ast
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import nullcontext
from datetime import date
from pathlib import Path
from threading import Event, Timer
from time import monotonic
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from display_snapshot import Snapshots
import home_fast
import orders_page as orders
from workspace_display_cache import user_scope

ROOT=Path(__file__).resolve().parents[1]
USER=dict(id="synthetic",session_version=1,role="worker",page_permissions=["orders"],is_active=True)


def fake_home():
    target=SimpleNamespace(container=nullcontext,empty=Mock(),caption=Mock())
    st=SimpleNamespace(session_state={"current_page":"Dashboard","sports_cave_current_user":dict(USER)},
        empty=lambda:target,caption=Mock(),button=Mock(return_value=False),rerun=Mock())
    def fragment(**kwargs):
        st.fragment_options=kwargs
        return lambda fn:fn
    st.fragment=fragment
    return st


@pytest.mark.parametrize("change",["route","account","revision","permissions","logout","removed"])
def test_home_late_read_never_renders_into_changed_route_or_scope(change):
    st=fake_home()
    cache=Mock()
    cache.read.return_value=dict(value=None,state="loading",checked_at=None)
    def wait(*args):
        if change=="route":st.session_state["current_page"]="Orders"
        if change=="account":st.session_state["sports_cave_current_user"]["id"]="someone-else"
        if change=="revision":st.session_state["sports_cave_current_user"]["session_version"]=2
        if change=="permissions":st.session_state["sports_cave_current_user"]["page_permissions"]=[]
        if change=="logout":st.session_state["sports_cave_authenticated"]=False
        if change=="removed":st.session_state.pop("sports_cave_current_user")
    cache.wait.side_effect=wait
    render=Mock()
    with patch.object(home_fast,"SNAPSHOTS",cache):
        home_fast.panel(st,dict(USER),date(2026,11,24),"Synthetic panel",Mock(),render)
    render.assert_not_called()
    assert cache.wait.call_count==1
    st.rerun.assert_not_called()


def test_home_completion_and_stale_values_render_once_without_full_app_rerun():
    for stale in (False,True):
        st=fake_home()
        cache=Mock()
        ready=dict(value={"text":"Saved"},state="stale" if stale else "ready",checked_at=1)
        cache.read.side_effect=[ready] if stale else [dict(value=None,state="loading",checked_at=None),ready]
        render=Mock()
        with patch.object(home_fast,"SNAPSHOTS",cache):
            home_fast.panel(st,dict(USER),date(2026,11,24),"Synthetic panel",Mock(),render)
        render.assert_called_once_with({"text":"Saved"})
        st.rerun.assert_not_called()
        assert st.fragment_options==dict(run_every=30,parallel=True)
        assert cache.wait.call_count==int(not stale)


def test_home_failure_retry_invalidates_only_display_key_and_reruns_fragment():
    st=fake_home()
    st.button.return_value=True
    cache=Mock()
    cache.read.return_value=dict(value=None,state="unavailable",checked_at=None)
    render=Mock()
    with patch.object(home_fast,"SNAPSHOTS",cache):
        home_fast.panel(st,dict(USER),date(2026,11,24),"Synthetic panel",Mock(),render)
    cache.invalidate.assert_called_once_with((user_scope(USER),"2026-11-24","Synthetic panel"))
    st.rerun.assert_called_once_with(scope="fragment")
    render.assert_not_called()


def test_snapshot_completion_wait_has_no_read_or_lock_side_effects():
    release=Event()
    entered=Event()
    cache=Snapshots(workers=1)
    calls=[]
    def load():
        calls.append(True)
        entered.set()
        assert release.wait(2)
        return {"saved":True}
    try:
        cache.read("key",load)
        assert entered.wait(1)
        with ThreadPoolExecutor(max_workers=1) as waiter:
            future=waiter.submit(cache.wait,"key",1)
            assert cache.lock.acquire(timeout=.1),"Wait held the cache lock"
            cache.lock.release()
            release.set()
            assert future.result(2)
        assert len(calls)==1
        assert cache.read("key",load)["value"]=={"saved":True}
        assert cache.wait("missing",.01) is False
    finally:
        release.set()
        cache.close()


def order_state(future):
    return {"current_page":"Orders","sports_cave_current_user":dict(USER),
        orders.LOAD_SCOPE_KEY:user_scope(USER),orders.LOAD_FUTURE_KEY:future,
        orders.LOAD_STARTED_KEY:monotonic(),orders.ROWS_KEY:[]}


def test_orders_completion_is_consumed_without_a_timer_or_app_rerun():
    future=Future()
    state=order_state(future)
    timer=Timer(.06,lambda:future.set_result({"rows":[{"order":"Synthetic"}]}))
    timer.start()
    try:
        def apply(payload):state[orders.ROWS_KEY]=payload["rows"]
        with patch.object(orders,"st",SimpleNamespace(session_state=state)), \
                patch.object(orders,"_apply_snapshot_payload",side_effect=apply):
            assert orders._wait_for_snapshot_load()=="ready"
        assert state[orders.LOAD_FUTURE_KEY] is None
        assert len(state[orders.ROWS_KEY])==1
    finally:
        timer.join()


@pytest.mark.parametrize("change",["permissions","role","inactive","logout","removed"])
def test_orders_completed_future_rechecks_scope_after_result(change):
    state={}
    class Race(Future):
        def result(self,*args,**kwargs):
            if change=="permissions":state["sports_cave_current_user"]["page_permissions"]=[]
            if change=="role":state["sports_cave_current_user"]["role"]="admin"
            if change=="inactive":state["sports_cave_current_user"]["is_active"]=False
            if change=="logout":state["sports_cave_authenticated"]=False
            if change=="removed":state.pop("sports_cave_current_user")
            return {"rows":[{"order":"must-not-render"}]}
    future=Race()
    future.set_result(None)
    state.update(order_state(future))
    with patch.object(orders,"st",SimpleNamespace(session_state=state)), \
            patch.object(orders,"_apply_snapshot_payload") as apply:
        assert orders._consume_snapshot_load()=="superseded"
    apply.assert_not_called()


def test_orders_wait_keeps_original_deadline_and_error_path():
    future=Future()
    state=order_state(future)
    state[orders.LOAD_STARTED_KEY]=monotonic()-orders.ORDERS_PAGE_LOAD_TIMEOUT_SECONDS-1
    with patch.object(orders,"st",SimpleNamespace(session_state=state)), \
            patch.object(orders,"_record_snapshot_load_error") as error:
        assert orders._wait_for_snapshot_load()=="error"
    error.assert_called_once()
    assert future.cancelled()


@pytest.mark.parametrize("change",["route","permissions","logout"])
def test_orders_workspace_never_acknowledges_a_stale_completion(change):
    node=next(n for n in ast.parse((ROOT/"app.py").read_text(encoding="utf-8")).body
              if isinstance(n,ast.FunctionDef) and n.name=="_render_orders_workspace")
    node.decorator_list=[]
    state={"current_page":"Orders","sports_cave_current_user":dict(USER)}
    def render(**kwargs):
        if change=="route":state["current_page"]="Dashboard"
        if change=="permissions":state["sports_cave_current_user"]["page_permissions"]=[]
        if change=="logout":state["sports_cave_authenticated"]=False
    ns=dict(st=SimpleNamespace(session_state=state,rerun=Mock()),current_os_user=lambda:state["sports_cave_current_user"],
        is_app_authenticated=lambda:True,ensure_current_page_access=lambda page:True,
        get_orders_page=lambda:SimpleNamespace(render_page=render),_orders_selection_access_allowed=Mock(),
        _navigation_page_status=lambda page:"ready",_finish_navigation_transition=Mock(),
        top_bar=Mock(),get_components_module=Mock(),NAVIGATION_EPOCH_STATE_KEY="epoch",
        logging=Mock(),_render_navigation_failure=Mock(),os_accounts=Mock())
    exec(compile(ast.Module(body=[node],type_ignores=[]),"<workspace guards>","exec"),ns)
    ns["_render_orders_workspace"]()
    ns["_finish_navigation_transition"].assert_not_called()
    ns["top_bar"].render_navigation_complete.assert_not_called()
