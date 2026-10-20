"""Focused name, metadata, ID controls and safe deletion regressions."""
import asyncio
import json
from pathlib import Path
import tempfile
import uuid
from unittest.mock import AsyncMock
import pytest
from task_recorder.runner import Runner
from task_recorder.device import DeviceAgent, payload
from task_recorder.schema import Invalid
from task_recorder.store import Store


def task(name="Existing custom name"):
    return {"version":1,"id":str(uuid.uuid4()),"name":name,"inputs":[],"steps":[{"action":"navigate","value":"https://example.com"}]}


def test_metadata_cache_legacy_duration_and_durable_deletion(tmp_path):
    store=Store(tmp_path)
    old=task();(store.tasks/(old["id"]+".json")).write_text(json.dumps(old))
    assert store.list()[0]["duration_ms"] is None
    assert store.list()[0]["updated_at"] is None
    first=store.save(task("Keep"));second=store.save(task("Delete"))
    store.metadata(first["id"],duration_ms=12345)
    store.result(second["id"],"completed",1,"Done")
    store.checkpoint(second,False)
    profile=tmp_path/"browser-profile";profile.mkdir();(profile/"session").write_text("keep")
    upload=tmp_path/"source.txt";upload.write_text("keep")
    store.delete(second["id"])
    assert not any(t["id"]==second["id"] for t in Store(tmp_path).list())
    with pytest.raises(Invalid):store.get(second["id"])
    with pytest.raises(Invalid):store.save(second)
    assert not (tmp_path/"recording.json").exists()
    assert store.get(first["id"])["name"]=="Keep"
    assert next(t for t in store.list() if t["id"]==first["id"])["duration_ms"]==12345
    assert upload.exists() and (profile/"session").exists()


def test_id_scoped_rename_and_active_delete_guard(tmp_path):
    async def check():
        r=Runner(tmp_path,headless=True);agent=DeviceAgent(r,"http://127.0.0.1:18932",preview=True)
        one=r.store.save(task("First"));two=r.store.save(task("Second"));r.draft=two
        await agent.perform("rename",{"id":one["id"],"name":"Renamed"},"test")
        assert r.store.get(one["id"])["name"]=="Renamed"
        assert r.draft["name"]=="Second"
        r.draft=one;r.recording=True;r.mode="recording"
        with pytest.raises(Invalid,match="Stop this task first"):
            await agent.perform("delete",{"id":one["id"]},"test")
        await agent.perform("delete",{"id":two["id"]},"test")
        r.recording=False;r.mode="idle"
        await agent.close()
    asyncio.run(check())


def test_supplied_record_name_default_and_pause_acknowledgement(tmp_path):
    async def check():
        r=Runner(tmp_path,headless=True);agent=DeviceAgent(r,"http://127.0.0.1:18932",preview=True)
        r.context=object();r.page=type("Page",(),{"is_closed":lambda s:False,"bring_to_front":AsyncMock()})()
        r.set_recording=AsyncMock()
        await agent.perform("record",{"name":"Clicking to Home"},"one")
        assert r.draft["name"]=="Clicking to Home"
        first_id=r.draft["id"]
        await agent.perform("record",{"name":"  "},"two")
        assert r.draft["name"].startswith("Recording ") and r.draft["id"]!=first_id
        r.job=asyncio.create_task(asyncio.Event().wait());r.mode="running";r.in_action=True
        await r.pause();assert r.mode=="pausing" and not r.gate.is_set()
        gate=asyncio.create_task(r.wait_gate());await asyncio.sleep(0)
        assert r.mode=="paused"
        await r.resume();await gate
        r.job.cancel()
        try:await r.job
        except asyncio.CancelledError:pass
        await agent.close()
    asyncio.run(check())


def test_payloads_reject_unscoped_deletion_and_arbitrary_fields():
    payload("record",{"name":"Clicking to Home","url":"https://example.com/?page=2"})
    payload("rename",{"id":str(uuid.uuid4()),"name":"Custom"})
    with pytest.raises(Invalid):payload("delete",{})
    with pytest.raises(Invalid):payload("delete",{"id":"../outside"})
    with pytest.raises(Invalid):payload("record",{"script":"anything"})
