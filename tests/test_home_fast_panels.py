from datetime import date
from threading import Event, Timer
from time import perf_counter, sleep
from streamlit.testing.v1 import AppTest
from display_snapshot import Snapshots
import home_fast


SCRIPT = '''
import streamlit as st
from datetime import date
import home_fast
st.title('Home fixture')
st.session_state['full_runs'] = st.session_state.get('full_runs', 0) + 1
st.session_state['sports_cave_current_user'] = {'id':'fixture','role':'worker'}
home_fast.panel(st, {'id':'fixture','role':'worker'}, date(2026,11,18), 'Saved brief',
                home_fast.fixture_loader, lambda data: st.write(data['text']))
st.button('Navigation remains usable')
'''


def test_cold_home_snapshot_is_shown_in_first_run_without_completion_rerun(monkeypatch):
    cache = Snapshots(workers=1)
    release = Event()
    monkeypatch.setattr(home_fast, 'SNAPSHOTS', cache)
    def load():
        assert release.wait(3)
        return {'text': 'Published synthetic brief'}
    monkeypatch.setattr(home_fast, 'fixture_loader', load, raising=False)
    timer = Timer(.1, release.set)
    timer.start()
    try:
        app = AppTest.from_string(SCRIPT).run(timeout=3)
        assert not app.exception
        assert app.button[0].label == 'Navigation remains usable'
        assert 'Published synthetic brief' in [node.value for node in app.markdown]
        assert app.session_state['full_runs'] == 1
        assert app.button[0].label == 'Navigation remains usable'
    finally:
        release.set()
        timer.join()
        cache.close()


def test_saved_home_renders_without_storage_calls(monkeypatch):
    cache = Snapshots(workers=1)
    monkeypatch.setattr(home_fast, 'SNAPSHOTS', cache)
    key = (home_fast.user_scope({'id':'fixture','role':'worker'}), '2026-11-18', 'Saved brief')
    try:
        cache.read(key, lambda: {'text':'Already saved'})
        end = perf_counter()+2
        while cache.rows[key]['loading'] and perf_counter() < end:
            sleep(.005)
        def forbidden():
            raise AssertionError('Warm Home must not query storage')
        monkeypatch.setattr(home_fast, 'fixture_loader', forbidden, raising=False)
        app = AppTest.from_string(SCRIPT).run(timeout=3)
        assert not app.exception
        assert 'Already saved' in [node.value for node in app.markdown]
    finally:
        cache.close()


def test_home_panel_native_widgets_belong_to_the_fragment(monkeypatch):
    cache=Snapshots(workers=1)
    monkeypatch.setattr(home_fast,'SNAPSHOTS',cache)
    key=(home_fast.user_scope({'id':'fixture','role':'worker'}),'2026-11-18','Saved brief')
    try:
        cache.read(key,lambda:{'text':'Saved'})
        assert cache.wait(key,1)
        monkeypatch.setattr(home_fast,'fixture_loader',lambda:{'text':'Saved'},raising=False)
        script=SCRIPT.replace("lambda data: st.write(data['text'])",
                              "lambda data: st.button('Panel control',key='panel-control')")
        app=AppTest.from_string(script).run(timeout=3)
        assert not app.exception
        assert {button.label for button in app.button}=={'Panel control','Navigation remains usable'}
    finally:
        cache.close()
