from datetime import date
from threading import Event
from time import perf_counter, sleep
from streamlit.testing.v1 import AppTest
from display_snapshot import Snapshots
import home_fast


SCRIPT = '''
import streamlit as st
from datetime import date
import home_fast
st.title('Home fixture')
home_fast.panel(st, {'id':'fixture','role':'worker'}, date(2026,11,18), 'Saved brief',
                home_fast.fixture_loader, lambda data: st.write(data['text']))
st.button('Navigation remains usable')
'''


def test_home_shell_renders_while_data_waits_then_displays_snapshot(monkeypatch):
    cache = Snapshots(workers=1)
    release = Event()
    monkeypatch.setattr(home_fast, 'SNAPSHOTS', cache)
    def load():
        assert release.wait(3)
        return {'text': 'Published synthetic brief'}
    monkeypatch.setattr(home_fast, 'fixture_loader', load, raising=False)
    try:
        app = AppTest.from_string(SCRIPT).run(timeout=3)
        assert not app.exception
        assert app.button[0].label == 'Navigation remains usable'
        assert 'loading saved information' in app.caption[0].value
        release.set()
        end = perf_counter()+2
        while next(iter(cache.rows.values()))['loading'] and perf_counter() < end:
            sleep(.005)
        app.run()
        assert not app.exception
        assert 'Published synthetic brief' in [node.value for node in app.markdown]
        assert app.button[0].label == 'Navigation remains usable'
    finally:
        release.set()
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
