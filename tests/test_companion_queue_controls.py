from streamlit.testing.v1 import AppTest
import morning_design_queue
import product_upload_staff_queue


def test_play_pause_buttons_and_waiting_status(monkeypatch):
    state = {'enabled': True}
    changes = []
    def settings(enabled=None):
        if enabled is not None:
            state['enabled'] = enabled
            changes.append(enabled)
        return dict(state)
    monkeypatch.setattr(morning_design_queue, 'settings', settings)
    monkeypatch.setattr(morning_design_queue, 'list_jobs', lambda: [])
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', lambda: {'online': True})
    app = AppTest.from_string('from upload_companion_page import render_design_queue\nrender_design_queue()').run()
    assert not app.exception
    assert app.button(key='cq-design-play').disabled
    app.button(key='cq-design-pause').click().run()
    assert not app.exception
    assert changes == [False]
    assert app.button(key='cq-design-pause').disabled
    assert not app.button(key='cq-design-play').disabled
    assert any('Queue paused. Press Play' in item.value for item in app.markdown)
    app.button(key='cq-design-play').click().run()
    assert not app.exception
    assert changes == [False, True]
    assert app.button(key='cq-design-play').disabled
