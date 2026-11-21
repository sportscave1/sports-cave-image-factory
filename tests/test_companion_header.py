from copy import deepcopy

import companion_header
import design_publish_ad
import morning_design_queue
import product_upload_staff_queue


def test_header_preserves_real_states_and_marks_estimates(monkeypatch):
    design_jobs = [dict(id=str(stage), title='Design '+str(stage), stage=stage, label='Existing label',
                       updated_at='2026-11-18T00:00:00+00:00', created_at='2026-11-18T00:00:00+00:00')
                   for stage in (5, 4, 0, 2)]
    ad_jobs = [dict(id=stage, title='Ad '+stage, stage=stage, label='Existing '+stage, detail='')
               for stage in ('generating', 'waiting', 'failed', 'complete')]
    monkeypatch.setattr(morning_design_queue, 'list_jobs', lambda **kwargs: deepcopy(design_jobs))
    monkeypatch.setattr(design_publish_ad, 'dashboard', lambda: dict(enabled=False, online=True, jobs=deepcopy(ad_jobs)))
    queues = companion_header.enrich_queues(dict(design=dict(waiting=1, enabled=True), upload=dict(waiting=0, enabled=True)))
    assert [job['state'] for job in queues['design']['jobs']] == ['running', 'waiting', 'failed', 'complete']
    assert queues['design']['jobs'][0]['estimated']
    assert queues['design']['jobs'][0]['percent'] <= 90
    assert queues['upload']['display']
    assert not queues['ads']['enabled'] and queues['ads']['online']
    assert queues['ads']['waiting'] == 1
    assert [job['percent'] for job in queues['ads']['jobs']] == [40, 0, 0, 100]
    assert not any(job['estimated'] for job in queues['ads']['jobs'])


def test_delivered_design_review_notes_are_not_a_failed_generation(monkeypatch):
    jobs = [dict(id='giannis', stage=5, file_path='/Review/Giannis.psd',
                 label='Uploaded · needs review', detail='Check artwork and upload metadata.'),
            dict(id='oscar', stage=5, file_path='', label='Needs attention',
                 detail='Could not verify thinking level.')]
    monkeypatch.setattr(morning_design_queue, 'list_jobs', lambda **kwargs: jobs)
    monkeypatch.setattr(design_publish_ad, 'dashboard', lambda: dict(enabled=True, online=True, jobs=[]))
    result = companion_header.enrich_queues(dict(design={}, upload={}))['design']['jobs']
    assert result[0]['state'] == 'complete' and result[0]['percent'] == 100
    assert result[0]['label'] == 'Uploaded · needs review'
    assert result[0]['detail'] == jobs[0]['detail']
    assert result[1]['state'] == 'failed'


def test_header_and_ads_controls_keep_admin_and_origin_guards(monkeypatch):
    import files_upload_api
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    user = {'id': 'staff', 'role': 'worker', 'is_active': True}
    actors, controls = [], []
    monkeypatch.setattr(files_upload_api, '_request_user', lambda *_args, **_kw: user)
    monkeypatch.setattr(product_upload_staff_queue, 'list_jobs', lambda actor: actors.append(actor) or dict(jobs=[],online=False))
    monkeypatch.setattr(product_upload_staff_queue, 'header_queue_status', lambda: dict(ads=dict(enabled=True,jobs=[])))
    monkeypatch.setattr(design_publish_ad, 'settings', lambda enabled: controls.append(enabled) or dict(enabled=enabled))
    client = TestClient(Starlette(routes=[Route(path, endpoint, methods=methods)
        for path, endpoint, methods in product_upload_staff_queue.ROUTES]))
    base = '/api/staff-product-uploads'
    assert 'queues' not in client.get(base+'/status').json()
    assert actors == ['staff']
    action = dict(queue='ads', enabled=False)
    assert client.post(base+'/queue-control', json=action, headers={'Origin':'http://testserver'}).status_code == 403
    user['role'] = 'admin'
    assert 'ads' in client.get(base+'/status').json()['queues']
    assert actors[-1] is None  # Administrator sees the full companion upload queue.
    assert client.post(base+'/queue-control', json=action).status_code == 403
    assert client.post(base+'/queue-control', json=action, headers={'Origin':'https://elsewhere.test'}).status_code == 403
    assert not controls
    assert client.post(base+'/queue-control', json=action, headers={'Origin':'http://testserver'}).json() == dict(enabled=False)
    assert controls == [False]
