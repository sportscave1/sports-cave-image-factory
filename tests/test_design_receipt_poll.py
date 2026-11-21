from concurrent.futures import Future
import morning_design_queue as queue


def test_slow_scan_does_not_block_or_queue_more_scans(monkeypatch):
    future=Future(); calls=[]
    class Pool:
        def submit(self,fn,jobs):
            calls.append(jobs);return future
    monkeypatch.setattr(queue,'_verification_pool',Pool())
    monkeypatch.setattr(queue,'_verification_future',None)
    monkeypatch.setattr(queue,'_verification_prompts',{})
    jobs=[dict(id='one',prompt='original')]
    assert queue.poll_outputs(jobs)=={}
    assert queue.poll_outputs(jobs)=={}
    assert len(calls)==1
    future.set_result({'one':{'stage':4}})
    assert queue.poll_outputs([dict(id='one',prompt='retry')])=={}


def test_finished_scan_delivers_verified_receipt(monkeypatch):
    future=Future();future.set_result({'one':{'stage':4}})
    monkeypatch.setattr(queue,'_verification_future',future)
    monkeypatch.setattr(queue,'_verification_prompts',{'one':'original'})
    class Pool:
        def submit(self,*args):return Future()
    monkeypatch.setattr(queue,'_verification_pool',Pool())
    assert queue.poll_outputs([dict(id='one',prompt='original')])=={'one':{'stage':4}}
