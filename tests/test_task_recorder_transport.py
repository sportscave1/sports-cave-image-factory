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
