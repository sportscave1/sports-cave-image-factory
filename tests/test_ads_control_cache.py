from contextlib import contextmanager
from uuid import uuid4
from types import SimpleNamespace
import pytest
import ads_companion_controls as controls

@pytest.mark.parametrize('operation', ['delete', 'cancel', 'play'])
def test_control_invalidates_both_displays_after_commit(monkeypatch, operation):
    import product_upload_staff_queue as uploads
    import companion_display
    events=[]
    class Cursor:
        def execute(self, sql, params=None):
            self.sql=sql
        def fetchone(self):
            if '10 minutes' in self.sql:return None
            return {'value': {'stage':'waiting'}}
        def __enter__(self):return self
        def __exit__(self,*args):pass
    class Connection:
        def cursor(self):return Cursor()
    @contextmanager
    def connect():
        yield Connection()
        events.append('commit')
    monkeypatch.setattr(controls.ads,'connect',connect)
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    monkeypatch.setattr(uploads,'_HEADER_DISPLAYS',SimpleNamespace(invalidate_matching=lambda _:events.append('header')))
    monkeypatch.setattr(companion_display,'invalidate',lambda:events.append('queue'))
    result=controls.action({'id':'fixture'},str(uuid4()),operation)
    assert result['action']==operation
    assert events==['commit','header','queue']


def test_failed_transaction_does_not_invalidate(monkeypatch):
    import product_upload_staff_queue as uploads
    import companion_display
    calls=[]
    @contextmanager
    def connect():
        raise RuntimeError('database unavailable')
        yield
    monkeypatch.setattr(controls.ads,'connect',connect)
    monkeypatch.setattr(uploads,'can_control_queues',lambda _:True)
    monkeypatch.setattr(companion_display,'invalidate',lambda:calls.append('invalidated'))
    with pytest.raises(RuntimeError,match='database unavailable'):
        controls.action({'id':'fixture'},str(uuid4()),'delete')
    assert not calls
