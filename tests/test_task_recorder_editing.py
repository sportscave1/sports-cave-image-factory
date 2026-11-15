"""Focused copy editing, revision, privacy and durable command contracts."""
import asyncio
import copy
import uuid
from pathlib import Path
import pytest
from unittest.mock import AsyncMock
from task_recorder.device import DeviceAgent, payload
from task_recorder.editing import EditInvalid
from task_recorder.runner import Runner
from task_recorder.schema import Invalid, resolve_task
from tests.test_task_recorder_transport import transport


def recording():
    return {"version":1,"id":str(uuid.uuid4()),"name":"Disposable editor source","inputs":[],"steps":[
        {"action":"navigate","value":"https://example.com/products?category=art"},
        {"action":"fill","locator":{"by":"label","value":"Product name"},"value":"Old name"},
        {"action":"select","locator":{"by":"label","value":"Category"},"value":"art"},
        {"action":"check","locator":{"by":"label","value":"Approved"},"value":False},
        {"action":"unsupported","reason":"Recorder browser closed before Stop. Review the final actions before playback."}]}


def edit_data(r, task):
    return {"id":task["id"],"revision":r.store.revision(task),"name":task["name"]+" — edited",
            "steps":[{"source":i} for i in range(len(task["steps"]))]}


def test_copy_values_metadata_flags_and_durable_duplicate(tmp_path):
    async def main():
        r=Runner(tmp_path,headless=True);a=DeviceAgent(r,'http://127.0.0.1:18938',preview=True)
        original=r.store.save(recording());r.store.metadata(original['id'],duration_ms=21345)
        r.store.result(original['id'],'completed',4,'Synthetic previous result')
        r.mode='completed';r.run_id=original['id'];r.run_name=original['name'];r.total=4
        paths=[r.store.tasks/(original['id']+suffix) for suffix in ('.json','.meta','.result')]
        before=[p.read_bytes() for p in paths]
        data=edit_data(r,original);data['steps'][1]['value']='Edited name';data['steps'][2]['value']='sport';data['steps'][3]['value']=True
        data['steps'].insert(4,{'check':{'action':'wait','value':'Local demonstration'}})
        key=str(uuid.uuid4());command={'id':key,'kind':'edit-copy','payload':data,'boot_id':a.boot_id,'fence':0,'valid_for':30}
        await a.apply(command);assert a.acks[key]['status']=='applied',a.acks
        new=a.acks[key]['receipt']['new_task_id'];saved=r.store.get(new)
        assert saved['steps'][1]['value']=='Edited name' and saved['steps'][2]['value']=='sport' and saved['steps'][3]['value'] is True
        assert saved['steps'][-1]==original['steps'][-1]
        with pytest.raises(Invalid,match='Needs attention'):resolve_task(saved,{})
        row=next(t for t in r.store.list() if t['id']==new)
        assert row['result']=='Never run' and row['duration_ms'] is None and row['last_run'] is None
        assert r.mode=='idle' and r.run_id is None and r.total==0 and not r.can_resume
        assert r.store.metadata(new)['source_duration_ms']==21345
        assert [p.read_bytes() for p in paths]==before
        await a.apply(command);assert len(r.store.list())==2 and a.acks[key]['receipt']['new_task_id']==new
        await a.close()
        a=DeviceAgent(r,'http://127.0.0.1:18938',preview=True)
        await a.apply(command);assert len(r.store.list())==2 and a.acks[key]['status']=='applied'
        assert r.store.get(original['id'])==original
        await a.close()
    asyncio.run(main())


def test_stale_active_and_invalid_step_errors(tmp_path):
    async def main():
        r=Runner(tmp_path,headless=True);a=DeviceAgent(r,'http://127.0.0.1:18938',preview=True)
        original=r.store.save(recording());data=edit_data(r,original)
        for mode in ('recording','recording_paused','interrupted'):
            r.mode=mode;r.recording=mode=='recording'
            with pytest.raises(Invalid,match='Stop'):await a.perform('edit-copy',data,str(uuid.uuid4()))
            with pytest.raises(Invalid,match='Stop'):await a.perform('edit-file',{'id':data['id'],'revision':data['revision']},str(uuid.uuid4()))
        r.mode='idle';r.recording=False
        r.job=asyncio.create_task(asyncio.sleep(30));r.mode='running'
        with pytest.raises(Invalid,match='Stop'):await a.perform('edit-copy',data,str(uuid.uuid4()))
        r.job.cancel();await asyncio.gather(r.job,return_exceptions=True);r.job=None;r.mode='idle'
        bad=copy.deepcopy(data);bad['steps'][3]['value']='yes'
        with pytest.raises(EditInvalid) as error:await a.perform('edit-copy',bad,str(uuid.uuid4()))
        assert '3' in error.value.step_errors
        bad=copy.deepcopy(data);bad['steps'][-1]['value']='remove warning'
        with pytest.raises(EditInvalid) as error:await a.perform('edit-copy',bad,str(uuid.uuid4()))
        assert '4' in error.value.step_errors
        r.store.save({**original,'name':'Changed elsewhere'})
        for kind in ('edit-copy','edit-file','record-replacement'):
            request=data if kind=='edit-copy' else {'id':data['id'],'revision':data['revision']}
            if kind=='record-replacement':request['step']=1
            with pytest.raises(Invalid,match='changed'):await a.perform(kind,request,str(uuid.uuid4()))
        assert len(r.store.list())==1
        await a.close()
    asyncio.run(main())


def test_replacement_refs_file_chooser_and_inputs(tmp_path):
    async def main():
        r=Runner(tmp_path,headless=True);a=DeviceAgent(r,'http://127.0.0.1:18938',preview=True)
        raw=recording();raw['inputs']=[{'name':'edit_0_headline' if i==0 else 'unused_'+str(i),'required':True} for i in range(50)]
        original=r.store.save(raw);data=edit_data(r,original)
        fragment=r.store.save({'version':1,'name':'Replacement recording','inputs':[{'name':'headline','required':True}],
            'steps':[{'action':'fill','locator':{'by':'label','value':'Headline'},'value':{'input':'headline'}}]})
        a.vault.put('defaults',{fragment['id']:{'headline':'Replacement value'}})
        file=tmp_path/'ordinary.txt';file.write_text('Synthetic upload')
        r.file_selector=lambda:str(file)
        response=await a.perform('edit-file',{'id':data['id'],'revision':data['revision']},str(uuid.uuid4()))
        assert set(response['value'])=={'file'} and str(file) not in str(response)
        upload=r.store.save({'version':1,'name':'Upload replacement','inputs':[],'steps':[
            {'action':'upload','locator':{'by':'label','value':'Image'},'value':response['value']}]})
        data['steps']=[{'source':0},{'recording':{'id':fragment['id'],'revision':r.store.revision(fragment),'step':0}},
                       {'recording':{'id':upload['id'],'revision':r.store.revision(upload),'step':0}}]
        out=await a.perform('edit-copy',data,str(uuid.uuid4()));new=r.store.get(out['new_task_id'])
        saved=a.vault.read()['defaults'][new['id']]
        resolved=resolve_task(new,saved,a.vault.file)
        assert resolved['steps'][1]['value']=='Replacement value' and resolved['steps'][2]['value']==str(file)
        assert original==r.store.get(original['id'])
        stale=copy.deepcopy(data);stale['steps'][1]['recording']['revision']='b'*64
        with pytest.raises(EditInvalid):await a.perform('edit-copy',stale,str(uuid.uuid4()))
        await a.close()
    asyncio.run(main())


@pytest.mark.parametrize('entry',[
    {'source':0,'locator':{'by':'text','value':'Injected'}},
    {'source':False}, {'source':-1}, {'check':{'action':'script','value':'anything'}},
    {'check':{'action':'wait','value':'password'}},
    {'source':0,'value':'https://example.com/?token=private'},
    {'source':1,'value':'Bearer abcdefghijk'},
    {'source':0,'value':{'input':'raw_path'}},
])
def test_data_only_privacy_validation(entry):
    data={'id':str(uuid.uuid4()),'revision':'a'*64,'name':'Edited','steps':[entry]}
    with pytest.raises(Invalid):payload('edit-copy',data)


def test_relay_compatibility_exclusion_owner_and_duplicate(transport):
    relay,_,owner,device,key,boot,state=transport
    data={'id':str(uuid.uuid4()),'revision':'a'*64,'name':'Edited','steps':[{'source':0}]}
    command=str(uuid.uuid4())
    with pytest.raises(Invalid,match='helper'):relay.enqueue(owner,device,command,'edit-copy',data)
    state={**state,'protocol':4}
    relay.exchange(device,key,{'boot_id':boot,'epoch':1,'state':state,'state_version':2})
    first=relay.enqueue(owner,device,command,'edit-copy',data)
    assert relay.enqueue(owner,device,command,'edit-copy',data)['id']==first['id']
    with pytest.raises(PermissionError):relay.enqueue(str(uuid.uuid4()),device,str(uuid.uuid4()),'edit-copy',data)
    run=str(uuid.uuid4());relay.enqueue(owner,device,run,'play',{'id':data['id'],'revision':data['revision']})
    for kind in ('edit-copy','edit-file','record-replacement'):
        request=data if kind=='edit-copy' else {'id':data['id'],'revision':data['revision']}
        if kind=='record-replacement':request['step']=0
        with pytest.raises(Invalid,match='Stop'):relay.enqueue(owner,device,str(uuid.uuid4()),kind,request)


def test_replacement_keeps_prepared_browser_context(tmp_path):
    async def main():
        r=Runner(tmp_path,headless=True);a=DeviceAgent(r,'http://127.0.0.1:18938',preview=True)
        original=r.store.save(recording());r.context=object()
        r.page=type('PreparedPage',(),{'is_closed':lambda self:False,'bring_to_front':AsyncMock()})()
        r.open_browser=AsyncMock();r.set_recording=AsyncMock()
        a.save_setting('url','https://example.com/old-start')
        result=await a.perform('record-replacement',{'id':original['id'],'revision':r.store.revision(original),'step':1},str(uuid.uuid4()))
        assert result['replacement_id']!=original['id'] and r.draft['name'].startswith('Replacement')
        r.open_browser.assert_not_awaited();r.page.bring_to_front.assert_awaited_once()
        assert a.settings()['url']=='https://example.com/old-start'
        await a.close()
    asyncio.run(main())
