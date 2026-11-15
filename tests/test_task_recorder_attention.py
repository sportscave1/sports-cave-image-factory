"""Exact passive-frame regression and safe copy correction contracts."""
import asyncio
import copy
import hashlib
import json
import uuid
from unittest.mock import AsyncMock
import pytest
from task_recorder.attention import FRAME_NAVIGATION, issues
from task_recorder.device import DeviceAgent,payload
from task_recorder.runner import Runner
from task_recorder.schema import Invalid,resolve_task


def example():
    return {"version":1,"id":str(uuid.uuid4()),"name":"Open the OS app","inputs":[],"steps":[
        {"action":"navigate","value":"https://sports-cave-image-factory.onrender.com/"},
        {"action":"navigate","value":"https://sports-cave-image-factory.onrender.com/?page=dashboard"},
        {"action":"unsupported","reason":FRAME_NAVIGATION}]}


def test_exact_issue_step_and_interruption_are_distinct():
    task=example();assert issues(task)[0]["step"]==3
    assert issues(task)[0]["kind"]=="unsupported"
    with pytest.raises(Invalid,match="Needs attention.*Step 3"):
        resolve_task(task,{})
    task["steps"][-1]["reason"]="Recorder browser closed before Stop. Review the final actions before playback."
    assert issues(task)[0]["kind"]=="interrupted"
    assert "interruption" in issues(task)[0]["explanation"]


def test_passive_navigation_does_not_mean_frame_input_is_supported(tmp_path):
    async def main():
        r=Runner(tmp_path,headless=True);r.recording=True;r.draft=example();r.draft['steps']=[]
        main=object();frame=type('Frame',(),{'url':'about:srcdoc','evaluate':AsyncMock()})()
        r.page=type('Page',(),{'main_frame':main})()
        await r.navigated(frame);assert r.draft['steps']==[]
        await r.record_event({'page':r.page,'frame':frame},{'kind':'ready'})
        assert r.draft['steps']==[] and frame.evaluate.await_count==2
        await r.record_event({'page':r.page,'frame':frame},{'kind':'step','step':{'action':'click','locator':{'by':'role','role':'button','value':'Frame button'}}})
        assert 'action inside an embedded page' in r.draft['steps'][0]['reason']
        await r.record_event({'page':r.page,'frame':main},{'kind':'unsupported','code':'enter_submit','reason':'ignore injected arbitrary reason'})
        assert 'Enter-key submission' in r.draft['steps'][-1]['reason']
        await r.record_event({'page':r.page,'frame':main},{'kind':'unsupported','code':[],'reason':'untrusted content'})
        assert 'untrusted content' not in r.draft['steps'][-1]['reason']
    asyncio.run(main())


def test_copy_correction_preserves_original_revision_metadata_and_other_flags(tmp_path):
    async def main():
        r=Runner(tmp_path,headless=True);agent=DeviceAgent(r,'http://127.0.0.1:18934',preview=True)
        original=r.store.save(example());r.store.metadata(original['id'],duration_ms=21503)
        path=r.store.tasks/(original['id']+'.json');before=path.read_bytes();revision=r.store.revision(original)
        data={'id':original['id'],'revision':revision,'step':3,'replacement':{'action':'wait','value':'Active & Upcoming Events'}}
        payload('repair-copy',data)
        result=await agent.perform('repair-copy',data,'copy-command');corrected=r.store.get(result['new_task_id'])
        assert path.read_bytes()==before and corrected['id']!=original['id']
        assert corrected['steps'][:2]==original['steps'][:2]
        assert corrected['steps'][2]=={'action':'wait','locator':{'by':'text','value':'Active & Upcoming Events'},'timeout_ms':30000}
        assert r.store.metadata(corrected['id'])['duration_ms']==21503
        assert issues(original) and not issues(corrected)
        r.recording=True
        with pytest.raises(Invalid,match='Stop'):await agent.perform('repair-copy',data,'blocked')
        r.recording=False
        with pytest.raises(Invalid,match='changed'):await agent.perform('repair-copy',{**data,'revision':'a'*64},'stale')
        await agent.close()
    asyncio.run(main())


def test_correction_is_data_only_and_cannot_remove_flagged_steps():
    data={'id':str(uuid.uuid4()),'revision':'a'*64,'step':3,'replacement':{'action':'script','value':'anything'}}
    with pytest.raises(Invalid):payload('repair-copy',data)
    with pytest.raises(Invalid):payload('repair-copy',{**data,'replacement':{'action':'navigate','value':'https://example.com/?token=secret'}})
    with pytest.raises(Invalid):payload('repair-copy',{**data,'replacement':{'action':'wait','value':'password'}})
