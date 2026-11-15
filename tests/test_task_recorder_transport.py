"""Focused bandwidth/latency regressions using isolated loopback PostgreSQL only."""
import asyncio
import copy
import json
import secrets
import uuid
from unittest.mock import patch

import httpx
import pytest
from starlette.applications import Starlette
from starlette.routing import Route

from task_recorder import hosted_api as api
from task_recorder.device import DeviceAgent
from task_recorder.runner import Runner
from task_recorder.schema import Invalid
from tests.test_task_recorder_relay import connect, Users
from task_recorder.relay_store import Relay


@pytest.fixture
def transport():
    owner=str(uuid.uuid4());device=str(uuid.uuid4());key=secrets.token_urlsafe(32);boot=str(uuid.uuid4())
    relay=Relay(connect,Users(owner))
    c=relay.challenge(owner);relay.claim(c["code"],device,key,"Synthetic PC")
    state={"protocol":3,"mode":"idle","tasks":[{"id":str(uuid.uuid4()),"name":"Synthetic recording "+str(n),
           "revision":"a"*64,"steps":4,"attention":[],"inputs":[],"result":"Never run"} for n in range(80)]}
    relay.exchange(device,key,{"boot_id":boot,"epoch":1,"state":state,"state_version":1})
    app=Starlette(routes=[Route(path,fn,methods=list(methods)) for path,fn,methods in api.ROUTES])
    app.state.recorder_relay=relay
    api._events.clear()
    with patch.object(api,"current_admin",return_value={"id":owner}):
        yield relay,app,owner,device,key,boot,state
    with connect() as conn:
        for table in ("commands","pairings","devices"):
            conn.execute("DELETE FROM task_recorder_private."+table+" WHERE owner_id=%s",(owner,))
    api._events.clear()


def test_delta_updates_are_versioned_bounded_and_preserve_tasks(transport):
    relay,_,owner,device,key,boot,state=transport
    def update(changes,base=1,version=2):
        return relay.exchange(device,key,{"boot_id":boot,"epoch":1,"state_version":version,
               "state_delta":{"base_version":base,"changes":changes}})
    assert update({"mode":"running","step":1})["state_delta"] is True
    saved=relay.devices(owner)[0]
    assert saved["state"]["tasks"]==state["tasks"] and saved["state"]["step"]==1
    assert update({"step":99})["state_resync"] is True
    assert relay.devices(owner)[0]["state"]["step"]==1
    assert not update({"step":2},base=2,version=3)["state_resync"]
    with pytest.raises(Invalid):update({"cookies":"must not be accepted"})
    with pytest.raises(Invalid):update({"tasks":["x"*180001]})
    with pytest.raises(Invalid):update({"message":"x"*170000},base=3,version=4)
    assert not update({"tasks":[]},base=3,version=4)["state_resync"]
    assert relay.devices(owner)[0]["state"]["tasks"]==[]
    with pytest.raises(PermissionError):
        relay.exchange(device,"wrong",{"boot_id":boot,"epoch":1,"state_delta":{"base_version":3,"changes":{"step":3}},"state_version":4})
    # A helper restart must establish a full baseline before any delta is used.
    result=relay.exchange(device,key,{"boot_id":str(uuid.uuid4()),"epoch":2,"state_version":4,
                         "state_delta":{"base_version":3,"changes":{"step":3}}})
    assert result["state_resync"] is True


def test_http_compact_poll_and_receipt_wake(transport):
    async def check():
        relay,app,owner,device,key,boot,state=transport
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1:18990") as client:
            full=await client.get("/api/task-recorder/state")
            row=full.json()["devices"][0];seq=row["seq"]
            api.event("state:"+device).set()
            compact=await client.get(f"/api/task-recorder/state?device={device}&after={seq}&compact=1")
            reduced=compact.json()["devices"][0]
            assert "state" not in reduced and reduced["connected"]
            assert len(compact.content)<len(full.content)*.1
            print(f"Idle response bytes: {len(full.content)} -> {len(compact.content)}")
            # An older client still receives the full snapshot; a new sequence
            # always returns full state, so compact omission cannot hide a change.
            assert "state" in (await client.get(f"/api/task-recorder/state?device={device}&after={seq}")).json()["devices"][0]
            relay.exchange(device,key,{"boot_id":boot,"epoch":1,"state_version":2,"state_delta":{"base_version":1,"changes":{"mode":"completed"}}})
            assert (await client.get(f"/api/task-recorder/state?device={device}&after={seq}&compact=1")).json()["devices"][0]["state"]["mode"]=="completed"
            command=str(uuid.uuid4());relay.enqueue(owner,device,command,"view",{})
            api._events.clear()
            waiting=asyncio.create_task(client.get(f"/api/task-recorder/receipt?device={device}&id={command}&wait=1"))
            await asyncio.sleep(.1);assert not waiting.done()
            exchange=await client.post("/api/task-recorder/device/exchange",headers={"Authorization":"Bearer "+key},json={"device_id":device,"boot_id":boot,"epoch":1,"acks":[{"id":command,"status":"applied","receipt":{}}]})
            assert exchange.status_code==200
            receipt=await asyncio.wait_for(waiting,2)
            assert receipt.json()["status"]=="applied"
            # Durable duplicate receipt is immediately available; no new command.
            assert (await client.get(f"/api/task-recorder/receipt?device={device}&id={command}&wait=1")).json()["status"]=="applied"
    asyncio.run(check())


def test_helper_delta_fallback_resync_and_immediate_ack(tmp_path):
    async def check():
        runner=Runner(tmp_path,headless=True);agent=DeviceAgent(runner,"http://127.0.0.1:18990",preview=True)
        agent.credentials=lambda:{"synthetic":True}
        snapshot={"mode":"idle","tasks":[{"name":"Saved task"}]*80,"step":0}
        agent.snapshot=lambda:copy.deepcopy(snapshot)
        agent.state_version=1
        sent=[]
        async def exchange(device,data):
            sent.append(copy.deepcopy(data))
            if len(sent)==1:return {"state_resync":True}
            agent.stopping=True
            return {}
        agent.exchange=exchange
        snapshot["step"]=1
        await agent.publish({"synthetic":True},{**snapshot,"step":0},True)
        assert sent[0]["state_delta"]=={"base_version":1,"changes":{"step":1}}
        assert "state" in sent[1] and sent[1]["state"]["tasks"]==snapshot["tasks"]
        assert len(json.dumps(sent[0]))<len(json.dumps(sent[1]))*.1
        agent.stopping=False;sent.clear()
        async def old_exchange(device,data):
            sent.append(data);agent.stopping=True;return {}
        agent.exchange=old_exchange
        await agent.publish({"synthetic":True},None,False)
        assert "state" in sent[0] and "state_delta" not in sent[0]
        agent.stopping=False;sent.clear();agent.state_version=1
        published=asyncio.Event()
        async def acknowledge(device,data):
            sent.append(data);published.set();agent.stopping=True;return {}
        agent.exchange=acknowledge
        job=asyncio.create_task(agent.publish({"synthetic":True},copy.deepcopy(snapshot),True))
        await asyncio.sleep(.01)
        agent.acks["command"]={"id":"command","status":"applied","receipt":{}}
        agent.publish_wake.set()
        await asyncio.wait_for(published.wait(),.5)
        await job
        assert sent[0]["acks"][0]["id"]=="command" and not agent.acks
        await agent.close()
    asyncio.run(check())


def test_catalogue_patch_is_bounded_versioned_and_owner_scoped(transport):
    from task_recorder.state_updates import task_changes, merge_tasks
    relay,_,owner,device,key,boot,state=transport
    original=state["tasks"]
    changed=copy.deepcopy(original);changed[0]["result"]="completed";removed=changed.pop();new=dict(changed[1],id=str(uuid.uuid4()),name="New synthetic");changed.append(new)
    patch=task_changes(original,changed)
    assert len(patch["upsert"])==2 and patch["remove"]==[removed["id"]]
    result=relay.exchange(device,key,{"boot_id":boot,"epoch":1,"state_version":2,
        "state_delta":{"base_version":1,"changes":{"step":1},"tasks":patch}})
    assert result["task_delta"] is True
    saved=relay.devices(owner)[0]["state"]
    assert saved["tasks"]==merge_tasks(original,patch) and saved["step"]==1
    assert len(json.dumps(patch))<len(json.dumps(original))*.1
    for invalid in ({"upsert":[{"id":new["id"],"cookies":"secret"}],"remove":[]},
                    {"upsert":[new,new],"remove":[]},{"upsert":[new],"remove":[new["id"]]},
                    {"upsert":[],"remove":["not-an-id"]}):
        with pytest.raises(Invalid):merge_tasks(original,invalid)
    bad={"boot_id":boot,"epoch":1,"state_version":3,"state_delta":{"base_version":2,"changes":{"tasks":[]},"tasks":patch}}
    with pytest.raises(Invalid):relay.exchange(device,key,bad)
    stale=relay.exchange(device,key,{"boot_id":boot,"epoch":1,"state_version":3,"state_delta":{"base_version":1,"changes":{},"tasks":patch}})
    assert stale["state_resync"] is True
    assert relay.devices(owner)[0]["state"]["tasks"]==saved["tasks"]


def test_http_changed_state_uses_catalogue_delta_only_for_exact_baseline(transport):
    async def check():
        relay,app,owner,device,key,boot,state=transport
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://127.0.0.1:18990") as client:
            full=await client.get('/api/task-recorder/state');seq=full.json()['devices'][0]['seq']
            assert full.json()['compact']==2
            immediate=await asyncio.wait_for(client.get(f'/api/task-recorder/state?device={device}&after={seq}&compact=2&wait=0'),1)
            assert 'state' not in immediate.json()['devices'][0]
            api._events.clear()
            waiting=asyncio.create_task(client.get(f'/api/task-recorder/state?device={device}&after={seq}&compact=2'))
            await asyncio.sleep(.1);assert not waiting.done()
            changed=copy.deepcopy(state);changed['mode']='running';changed['tasks'][0]['result']='running'
            reply=await client.post('/api/task-recorder/device/exchange',headers={'Authorization':'Bearer '+key},json={'device_id':device,'boot_id':boot,'epoch':1,'state_version':2,'state':changed})
            assert reply.status_code==200
            reduced=await asyncio.wait_for(waiting,2);row=reduced.json()['devices'][0]
            assert 'state' not in row and row['state_delta']['base_seq']==seq
            assert len(row['state_delta']['tasks']['upsert'])==1
            assert row['state_delta']['changes']=={'mode':'running'}
            assert len(reduced.content)<len(full.content)*.1
            # No old snapshot is cached/guessed when initial DB sequence is newer.
            fallback=await client.get(f'/api/task-recorder/state?device={device}&after={seq}&compact=2')
            assert fallback.json()['devices'][0]['state']==changed
    asyncio.run(check())


def test_helper_negotiates_catalogue_deltas_and_stop_labels(tmp_path):
    async def check():
        from task_recorder.state_updates import merge_tasks
        runner=Runner(tmp_path,headless=True);agent=DeviceAgent(runner,'http://127.0.0.1:18990',preview=True)
        old={'mode':'running','tasks':[{'id':str(uuid.uuid4()),'name':'Synthetic '+str(n),'result':'Never run'} for n in range(40)]}
        new=copy.deepcopy(old);new['tasks'][0]['result']='completed'
        agent.snapshot=lambda:copy.deepcopy(new);agent.credentials=lambda:{'synthetic':True};sent=[]
        async def exchange(device,data):sent.append(data);agent.stopping=True;return {}
        agent.exchange=exchange;agent.state_version=1
        await agent.publish({'synthetic':True},old,True,True)
        assert 'tasks' not in sent[0]['state_delta']['changes']
        assert merge_tasks(old['tasks'],sent[0]['state_delta']['tasks'])==sorted(new['tasks'],key=lambda t:t['name'])
        agent.stopping=False;sent.clear()
        await agent.publish({'synthetic':True},old,True,False)
        assert sent[0]['state_delta']['changes']['tasks']==new['tasks']
        runner.simple_recording=True;runner.draft={'version':1,'name':'Prior recording','inputs':[],'steps':[{'action':'navigate','value':'https://example.com'}]}
        await agent.apply({'id':str(uuid.uuid4()),'kind':'stop','payload':{},'boot_id':agent.boot_id,'fence':0,'valid_for':30})
        assert runner.message=='Stopped.'
        await agent.close()
    asyncio.run(check())


def test_cold_play_advertises_starting_until_browser_is_ready(tmp_path):
    async def check():
        from unittest.mock import AsyncMock
        runner=Runner(tmp_path,headless=True);agent=DeviceAgent(runner,'http://127.0.0.1:18990',preview=True)
        task=runner.store.save({'version':1,'name':'Cold readiness','inputs':[],'steps':[{'action':'navigate','value':'https://example.com'}]})
        runner.mode='completed';entered=asyncio.Event();release=asyncio.Event()
        async def cold(*args):entered.set();await release.wait();runner.mode='running'
        runner.play=cold
        call=asyncio.create_task(agent.perform('play',{'id':task['id'],'revision':runner.store.revision(task),'values':{}},str(uuid.uuid4())))
        await entered.wait()
        assert agent.snapshot()['mode']=='starting' and agent.preparing
        assert agent.snapshot()['active_task_id']==task['id'] and agent.snapshot()['active_task_name']=='Cold readiness'
        # Network loss during browser startup must be an interruption, not a
        # stale Completed state; there is no replay or second start.
        runner.stop=AsyncMock();agent.active_commands['test']=call
        await agent.network_lost()
        assert call.cancelled() and runner.mode=='interrupted'
        runner.stop.assert_awaited_once()
        agent.active_commands.clear();await agent.close()
    asyncio.run(check())


def test_compact_metadata_does_not_repeat_unselected_pc_catalogues(transport):
    async def check():
        relay,app,owner,device,key,boot,state=transport
        second=str(uuid.uuid4());second_key=secrets.token_urlsafe(32);code=relay.challenge(owner)
        relay.claim(code['code'],second,second_key,'Second synthetic PC')
        relay.exchange(second,second_key,{'boot_id':str(uuid.uuid4()),'epoch':1,'state_version':1,'state':state})
        seq=next(row['seq'] for row in relay.devices(owner) if row['id']==device)
        api.event('state:'+device).set()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://127.0.0.1:18990') as client:
            result=await client.get(f'/api/task-recorder/state?device={device}&after={seq}&compact=2')
            assert len(result.json()['devices'])==2
            assert all('state' not in row for row in result.json()['devices'])
    asyncio.run(check())


def test_completion_notifies_publisher_without_faster_progress_polling(tmp_path):
    async def check():
        from unittest.mock import AsyncMock
        runner=Runner(tmp_path,headless=True);agent=DeviceAgent(runner,'http://127.0.0.1:18990',preview=True)
        task=runner.store.save({'version':1,'name':'Notification','inputs':[],'steps':[{'action':'navigate','value':'https://example.com'}]})
        runner.run_id=task['id'];runner.total=1;runner.perform=AsyncMock()
        assert not agent.publish_wake.is_set()
        await runner.run(task)
        assert runner.mode=='completed' and agent.publish_wake.is_set()
        await agent.close();assert runner.state_changed is None
    asyncio.run(check())


def test_open_popup_retains_active_run_and_review_fence(transport):
    relay,_,owner,device,key,boot,state=transport
    operation=str(uuid.uuid4())
    relay.enqueue(owner,device,operation,'record',{})
    state.update(mode='recording', desktop_capabilities={'popup_reopen':True})
    relay.exchange(device,key,{'boot_id':boot,'epoch':1,'state':state,'state_version':2})
    before=relay.devices(owner)[0]
    assert before['active_run']==operation
    receipt=relay.enqueue(owner,device,str(uuid.uuid4()),'open-popup',{})
    after=relay.devices(owner)[0]
    assert receipt['kind']=='open-popup'
    assert after['active_run']==before['active_run']
    assert after['needs_review']==before['needs_review']
    state.update(mode='interrupted')
    relay.exchange(device,key,{'boot_id':boot,'epoch':1,'state':state,'state_version':3})
    before=relay.devices(owner)[0]
    relay.enqueue(owner,device,str(uuid.uuid4()),'open-popup',{})
    after=relay.devices(owner)[0]
    assert after['active_run']==before['active_run']
    assert after['needs_review']==before['needs_review']
