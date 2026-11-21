from copy import deepcopy
from streamlit.testing.v1 import AppTest
import seo_companion as jobs
from tests.test_seo_companion import OWNER, audit, Crawler, pages, job


def test_results_show_evidence_and_save_a_review_without_publishing(monkeypatch):
    result = audit.audit(job(), crawler=Crawler(pages()))
    record = {**job(), 'stage': 'ready_for_review', 'finished_at': '2026-11-21T04:05:00+00:00',
              'instruction': 'Audit the retired Brock edition.', 'result': result}
    snapshot = {'settings': {'enabled': True}, 'jobs': [record], 'reviews': []}
    monkeypatch.setattr(jobs, 'snapshot', lambda: deepcopy(snapshot))
    monkeypatch.setattr(jobs, 'permitted', lambda *_: True)
    monkeypatch.setattr('os_accounts.can_access_page', lambda *_: True)
    saved = []
    monkeypatch.setattr(jobs, 'review', lambda *args: saved.append(args))
    app = AppTest.from_string('''
import seo_companion_ui
seo_companion_ui.results({'id':'owner'})
''').run()
    assert not app.exception
    assert any('0 storefront changes' in c.value for c in app.caption)
    assert any('partial' in m.value.lower() for m in app.markdown)
    assert any('source_url' in f.value.columns for f in app.dataframe)
    next(button for button in app.button if button.label == 'Save review decision').click().run()
    assert not app.exception
    assert len(saved) == 1 and saved[0][3] == 'Changes requested'
    assert saved[0][4] == jobs.revision(result)


def test_controls_are_in_companion_and_start_daily_work(monkeypatch):
    monkeypatch.setattr(jobs, 'snapshot', lambda: {'settings': {}, 'jobs': [], 'reviews': []})
    monkeypatch.setattr(jobs, 'permitted', lambda *_: True)
    calls = []
    monkeypatch.setattr(jobs, 'configure', lambda user, enabled: calls.append(enabled))
    app = AppTest.from_string('''
import seo_companion_ui
seo_companion_ui.controls({'id':'owner'})
''').run()
    assert not app.exception
    next(button for button in app.button if button.label == 'Start daily SEO plan').click().run()
    assert not app.exception and calls == [True]
