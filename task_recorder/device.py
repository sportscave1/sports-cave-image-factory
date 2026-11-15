"""Outbound HTTPS client and crash-safe command receipts for the local V1 engine."""
import asyncio
import copy
import contextlib
import hashlib
import json
import re
import random
import secrets
import socket
import sqlite3
import time
import uuid
from datetime import datetime
from urllib.parse import urlsplit

import httpx
from .schema import Invalid, keys, text, validate_task, safe_url
from .store import atomic
from .state_updates import task_changes
from .windows import startup, choose_file
from .editing import EDIT_COMMANDS, validate_edit_payload, source as edit_source, edited_copy

PRODUCTION = "https://sports-cave-image-factory.onrender.com"

def origin(value, preview=False):
    u=urlsplit(value)
    if u.username or u.password or u.query or u.fragment or u.path not in {"","/"}:
        raise Invalid("Use the Sports Cave OS website address.")
    if value.rstrip("/")!=PRODUCTION:
        if not (preview and u.scheme=="http" and u.hostname in {"127.0.0.1","localhost"} and u.port):
            raise Invalid("Only Sports Cave OS is supported. Local previews require the preview launcher.")
    return value.rstrip("/")

def payload(kind,data):
    if kind in EDIT_COMMANDS:
        validate_edit_payload(kind,data)
        return data
    fields={"library-page":{"offset"},"record":{"url","name"},"play":{"id","revision","values"},"load":{"id"},"rename":{"id","name"},"delete":{"id"},"inspect":{"id"},"reusable":{"id"},
            "repair-copy":{"id","revision","step","replacement"},"edit":{"task"},"startup":{"enabled"}}
    keys(data,fields.get(kind,set()))
    if kind == "library-page" and (type(data.get("offset")) is not int or data["offset"] < 0): raise Invalid("Invalid library page.")
    if "id" in data:
        try: uuid.UUID(data["id"])
        except (ValueError,TypeError,AttributeError):raise Invalid("Select a saved recording.")
    if kind == "delete" and not data.get("id"):raise Invalid("Select a saved recording.")
    if kind == "record" and "name" in data:text(data["name"],100,empty=True)
    if "url" in data: safe_url(data["url"])
    if kind=="play":
        keys(data,fields[kind],{"id","revision"})
        if not re.fullmatch("[a-f0-9]{64}",str(data["revision"])): raise Invalid("Select the saved recording again.")
        values=data.get("values",{})
        if not isinstance(values,dict) or len(values)>50: raise Invalid("Invalid inputs.")
        for name,value in values.items():
            text(name,40);text(value,empty=True)
            if value.startswith(("http://","https://")):safe_url(value)
    if kind=="repair-copy":
        keys(data,fields[kind],fields[kind])
        if not re.fullmatch("[a-f0-9]{64}",str(data["revision"])):raise Invalid("Select the recording again.")
        if isinstance(data["step"],bool) or not isinstance(data["step"],int) or not 1<=data["step"]<=500:raise Invalid("Select a flagged step.")
        item=data["replacement"];keys(item,{"action","value"},{"action","value"})
        if item["action"]=="navigate":safe_url(item["value"])
        elif item["action"]=="wait":
            from .schema import validate_locator
            validate_locator({"by":"text","value":item["value"]})
        else:raise Invalid("Choose a website or a visible-text readiness check.")
    if kind=="edit": validate_task(data.get("task"))
    if kind=="startup" and not isinstance(data.get("enabled"),bool): raise Invalid("Choose on or off.")
    if kind=="rename": text(data.get("name"),100)
    return data

class DeviceAgent:
    def __init__(self,runner,local_origin,*,preview=False):
        self.runner,self.root,self.local_origin=runner,runner.store.root,local_origin
        self.preview=preview
        self.vault=runner.vault
        self.db=sqlite3.connect(self.root/"commands.sqlite",check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS commands(id TEXT PRIMARY KEY,hash TEXT,status TEXT,receipt TEXT)")
        self.db.execute("UPDATE commands SET status='uncertain',receipt=? WHERE status='accepted'",
                        (json.dumps({"message":"Helper restarted before this command was confirmed. Check the previous result."}),))
        self.db.commit()
        meta=self.root/"device-session.json"
        old=json.loads(meta.read_text()) if meta.exists() else {}
        self.boot_id=str(uuid.uuid4());self.epoch=int(old.get("epoch",0))+1
        self.operation_id=old.get("operation_id")
        atomic(meta,{"boot_id":self.boot_id,"epoch":self.epoch,"operation_id":self.operation_id})
        self.state_version=0
        self.connected=False
        self.stopping=False
        self.wake=asyncio.Event()
        self.publish_wake=asyncio.Event()
        self.runner.state_changed=self.publish_wake.set
        self.acks={}
        self.fence=0
        self.active_commands={}
        self.control_lock=asyncio.Lock()
        self.preparing=False
        self.preparing_task=None
        self.client=None
        self.task=None
        self.last_failure=0

    def credentials(self):
        return self.vault.read().get("device")

    def snapshot(self):
        s=self.runner.state()
        s.pop("draft",None)
        if self.runner.recording or self.runner.mode=="recording_paused":
            draft=self.runner.draft
            if draft.get("id") and not any(t["id"]==draft["id"] for t in s["tasks"]):
                s["tasks"].append({"id":draft["id"],"name":draft["name"],"inputs":[],"steps":len(draft["steps"]),
                                   "duration_ms":None,"updated_at":None,"result":"Recording","revision":None})
        settings=self.settings()
        s.update(protocol=4,operation_id=self.operation_id,selected_id=s.get("selected_id",self.runner.draft.get("id")),
                 starting_url=settings.get("url",""),startup=settings.get("startup",False),
                 connection="connected" if self.connected else "reconnecting")
        if self.preparing and s["mode"] in {"idle","stopped","completed"}:
            s["mode"]="starting"
            if self.preparing_task:s.update(active_task_id=self.preparing_task["id"],active_task_name=self.preparing_task["name"])
        return s

    def settings(self):
        return self.vault.read().get("settings",{})

    def save_setting(self,name,value):
        data=self.vault.read();data.setdefault("settings",{})[name]=value;self.vault.write(data)

    async def pair(self,site,code,name):
        site=origin(site,self.preview)
        # Caller must be the explicit same-origin PC approval UI.
        device={"origin":site,"device_id":str(uuid.uuid4()),"key":secrets.token_urlsafe(32),"name":text(name,80)}
        pending=self.vault.read().get("pending_pair")
        if pending and pending.get("code")==code and pending.get("device",{}).get("origin")==site:
            device=pending["device"]
        else:self.vault.put("pending_pair",{"code":code,"device":device})
        async with httpx.AsyncClient(timeout=10,follow_redirects=False,trust_env=False) as client:
            response=await client.post(site+"/api/task-recorder/pairing/claim",json={"code":code,**{k:device[k] for k in ("device_id","key","name")}})
            if response.status_code!=200: raise Invalid("Pairing failed. Generate a new code in Sports Cave OS.")
        self.vault.put("device",device)
        self.vault.put("pending_pair",None)
        self.wake.set()
        return {"paired":True,"name":name}

    async def inspect_pair(self,site,code):
        site=origin(site,self.preview)
        async with httpx.AsyncClient(timeout=10,follow_redirects=False,trust_env=False) as client:
            response=await client.post(site+"/api/task-recorder/pairing/inspect",json={"code":code})
            if response.status_code!=200: raise Invalid("Code is invalid or expired. Generate a new code in Sports Cave OS.")
            return response.json()

    async def network_lost(self,revoked=False):
        self.connected=False
        interrupted=self.preparing or self.runner.busy() or self.runner.recording or self.runner.mode=="recording_paused"
        for task in list(self.active_commands.values()):task.cancel()
        if self.active_commands:await asyncio.gather(*list(self.active_commands.values()),return_exceptions=True)
        self.preparing=False
        if hasattr(self.runner, "connection_lost"):
            await self.runner.connection_lost(revoked=revoked)
        elif interrupted:
            await self.runner.stop()
            self.runner.mode="interrupted"
            self.runner.message="Connection lost. The recording was saved or playback interrupted. Check its result, then press Stop before starting again."
        if revoked:
            self.vault.put("device",None)
            self.runner.message="This PC was disconnected. Pair it again to use the OS controls."

    async def exchange(self,device,data,wait=False):
        started=time.monotonic()
        data={**data,"device_id":device["device_id"],"boot_id":self.boot_id,"epoch":self.epoch,"wait":wait}
        response=await self.client.post(device["origin"]+"/api/task-recorder/device/exchange",
                    headers={"Authorization":"Bearer "+device["key"]},json=data,
                    # A healthy long poll includes the 15-second server wait
                    # plus two authenticated database exchanges across regions.
                    timeout=httpx.Timeout(45 if wait else 20,connect=8))
        if response.status_code==403:
            await self.network_lost(True)
            raise Invalid("Device disconnected.")
        response.raise_for_status()
        self.connected=True
        result=response.json()
        for command in result["commands"]:
            command["valid_for"]-=time.monotonic()-started
        return result

    async def publish(self,device,initial=None,delta_supported=False,task_delta_supported=False):
        last=initial
        last_version=self.state_version
        while not self.stopping and self.credentials()==device:
            # Clear before taking the snapshot: a command finishing while we send
            # leaves the event set, so its acknowledgement is never delayed/lost.
            self.publish_wake.clear()
            s=self.snapshot()
            if s!=last or self.acks:
                self.state_version+=1
                outgoing=list(self.acks.values())
                data={"state_version":self.state_version,"acks":outgoing}
                if delta_supported and last is not None:
                    data["state_delta"]={"base_version":last_version,
                                         "changes":{k:v for k,v in s.items() if last.get(k)!=v}}
                    if task_delta_supported and "tasks" in data["state_delta"]["changes"]:
                        data["state_delta"]["tasks"]=task_changes(last.get("tasks",[]),s["tasks"])
                        del data["state_delta"]["changes"]["tasks"]
                else:data["state"]=s
                result=await self.exchange(device,data)
                for ack in outgoing:
                    if self.acks.get(ack["id"])==ack:self.acks.pop(ack["id"],None)
                # A lost baseline requires a full snapshot, never a guessed merge.
                last=None if result.get("state_resync") else s
                last_version=self.state_version
                if last is None:continue
            try:
                await asyncio.wait_for(self.publish_wake.wait(),timeout=.65 if self.runner.busy() or self.runner.recording or self.preparing else 2)
            except asyncio.TimeoutError:pass

    async def loop(self):
        self.client=httpx.AsyncClient(follow_redirects=False,trust_env=False)
        retry=0
        try:
            while not self.stopping:
                device=self.credentials()
                if not device:
                    self.wake.clear()
                    try:await asyncio.wait_for(self.wake.wait(),timeout=5)
                    except asyncio.TimeoutError:pass
                    continue
                publisher=None
                poll=None
                try:
                    self.state_version+=1
                    initial=self.snapshot()
                    first=await self.exchange(device,{"state":initial,"state_version":self.state_version})
                    retry=0
                    publisher=asyncio.create_task(self.publish(device,initial,first.get("state_delta",False),first.get("task_delta",False)))
                    result=first
                    while self.credentials()==device and not self.stopping:
                        self.fence=max(self.fence,result["fence"])
                        for command in result["commands"]:
                            if command["id"] in self.active_commands:continue
                            task=asyncio.create_task(self.apply(command))
                            self.active_commands[command["id"]]=task
                            task.add_done_callback(lambda _,key=command["id"]:self.active_commands.pop(key,None))
                        poll=asyncio.create_task(self.exchange(device,{},wait=True))
                        done,_=await asyncio.wait({poll,publisher},return_when=asyncio.FIRST_COMPLETED)
                        if publisher in done:
                            poll.cancel()
                            with contextlib.suppress(asyncio.CancelledError):await poll
                            await publisher
                            break
                        result=await poll
                        retry=0
                except asyncio.CancelledError:raise
                except Exception as error:
                    if time.monotonic()-self.last_failure>30:
                        atomic(self.root/"transport-status.json",{"error_type":type(error).__name__, "http_status":error.response.status_code if isinstance(error,httpx.HTTPStatusError) else None,
                               "explanation":("OS rejected helper authentication; reconnect this PC." if isinstance(error,httpx.HTTPStatusError) and error.response.status_code in (401,403) else "OS connection failed; check the local preview address and server health."),
                               "at":datetime.now().astimezone().isoformat()})
                        self.last_failure=time.monotonic()
                    for pending in (poll,publisher):
                        if pending:
                            pending.cancel()
                            with contextlib.suppress(asyncio.CancelledError,Exception):await pending
                    await self.network_lost()
                    retry=min(retry+1,5)
                    await asyncio.sleep(min(30,2**retry*random.uniform(.8,1.2)))
                finally:
                    if poll:
                        poll.cancel()
                        with contextlib.suppress(asyncio.CancelledError,Exception):await poll
                    if publisher:
                        publisher.cancel()
                        with contextlib.suppress(asyncio.CancelledError,Exception):await publisher
        finally:
            await self.client.aclose()

    async def apply(self,command):
        deadline=time.monotonic()+command["valid_for"]
        key=command["id"];kind=command["kind"];data=command["payload"]
        fingerprint=hashlib.sha256(json.dumps({"kind":kind,"payload":data},sort_keys=True).encode()).hexdigest()
        previous=self.db.execute("SELECT hash,status,receipt FROM commands WHERE id=?",(key,)).fetchone()
        if previous:
            if previous[0]!=fingerprint:
                self.acks[key]={"id":key,"status":"rejected","receipt":{"message":"Command content changed."}}
            else:
                self.acks[key]={"id":key,"status":"uncertain" if previous[1]=="accepted" else previous[1],"receipt":json.loads(previous[2])}
            self.publish_wake.set()
            return
        self.db.execute("INSERT INTO commands VALUES(?,?,?,?)",(key,fingerprint,"accepted","{}"));self.db.commit()
        try:
            payload(kind,data)
            if command["boot_id"]!=self.boot_id or command["fence"]<self.fence or command["valid_for"]<=0:
                raise Invalid("This control expired. Press it again.")
            if kind in {"stop","stop-save"}:
                for other,task in list(self.active_commands.items()):
                    if other!=key:task.cancel()
                was_recording=self.runner.recording or self.runner.mode=="recording_paused"
                if hasattr(self.runner, "stop_from_device"):
                    await self.runner.stop_from_device()
                else:
                    await self.runner.stop()
                self.preparing=False
                self.runner.message="Recording saved." if was_recording and self.runner.draft.get("steps") and self.runner.simple_recording else "Stopped."
                result={}
            else:
                async with self.control_lock:
                    if command["fence"]<self.fence:raise Invalid("Cancelled by Stop.")
                    if time.monotonic()>=deadline:raise Invalid("This control expired. Press it again.")
                    result=await asyncio.wait_for(self.perform(kind,data,key), timeout=max(.01, deadline-time.monotonic()))
            status="applied"
        except asyncio.TimeoutError:
            status="uncertain";result={"message":"Command deadline expired. Its outcome is unconfirmed; it will not be repeated. Inspect the preserved run."}
        except asyncio.CancelledError:
            status="uncertain";result={"message":"Cancelled while applying a control. Check the previous result."}
        except (Invalid,ValueError) as error:
            status="rejected";result={"message":str(error)}
            if getattr(error,"step_errors",None):result["step_errors"]=error.step_errors
        except Exception:
            status="uncertain";result={"message":"This control could not be confirmed. Press Stop and check the browser."}
        self.db.execute("UPDATE commands SET status=?,receipt=? WHERE id=?",(status,json.dumps(result),key));self.db.commit()
        self.acks[key]={"id":key,"status":status,"receipt":result}
        self.publish_wake.set()

    async def perform(self,kind,data,key):
        r=self.runner
        if hasattr(r,"desktop_command"):
            desktop_target=data.get("id") and r.is_desktop(data["id"])
            if desktop_target and kind not in {"inspect","play","rename","delete"}:
                raise Invalid("This desktop task is immutable. Use the native recorder to create another recording.")
            if kind in {"record","open-popup","library-page"} or desktop_target or (kind in {"pause","resume"} and r.desktop_busy()):
                if kind in {"record","play"}:
                    self.operation_id=key
                    atomic(self.root/"device-session.json",{"boot_id":self.boot_id,"epoch":self.epoch,"operation_id":key})
                return await r.desktop_command(kind,data,key)
            if kind in {"play","record-replacement"}:
                r.last_engine="browser"
        replacement=False
        if kind in EDIT_COMMANDS:
            payload(kind,data)
            if r.busy() or r.recording or r.mode in {"recording_paused","interrupted"} or self.preparing:
                raise Invalid("Stop the current task before editing.")
            original=edit_source(r.store,data)
            if kind=="edit-file":
                chosen=await asyncio.to_thread(r.file_selector or choose_file)
                if not chosen:raise Invalid("No file selected. Choose a replacement file on your PC.")
                return {"value":{"file":self.vault.add_file(chosen)}}
            if kind=="edit-copy":
                task_id=str(uuid.uuid5(uuid.NAMESPACE_URL,"sports-cave-recorder-edit:"+key))
                task,defaults=edited_copy(r.store,self.vault,data,task_id)
                saved=self.vault.read().get("defaults",{})
                saved[task_id]=defaults;self.vault.put("defaults",saved)
                meta=r.store.metadata(original["id"])
                duration=meta.get("duration_ms") if meta.get("duration_ms") is not None else meta.get("source_duration_ms")
                r.store.metadata(task_id,source_id=original["id"],source_revision=data["revision"],
                                 source_duration_ms=duration,duration_ms=None,edited=True)
                task=r.store.save(task)
                await r.command('load',{'id':task_id})
                r.run_id=None;r.can_resume=False;r.message="Edited copy saved. Not yet run."
                return {"new_task_id":task_id,"tasks":r.store.list()}
            # Replacement uses the ordinary recorder and durable Stop/autosave.
            # Its separate recording is reviewed before insertion into an edit.
            replacement=True
            position=data['step']
            if position>=len(original['steps']):raise Invalid("Choose an existing action to replace.")
            data={"name":("Replacement — "+original["name"])[:100]}
            if not r.page or r.page.is_closed():
                url=next((s.get("value") for s in reversed(original["steps"][:position+1]) if s["action"] in {"navigate","wait_url"} and isinstance(s.get("value"),str)),None)
                if url:data["url"]=url
            kind="record"
        if kind in {"record","play"}:
            if r.busy() or r.recording or r.mode=="recording_paused":raise Invalid("Already in progress. Press Stop first.")
            self.operation_id=key
            atomic(self.root/"device-session.json",{"boot_id":self.boot_id,"epoch":self.epoch,"operation_id":key})
        if kind=="record":
            self.preparing=True
            try:
                url=data.get("url") or (None if replacement else self.settings().get("url"))
                if url:
                    safe_url(url)
                    if not replacement:self.save_setting("url",url)
                if not r.context or not r.page or r.page.is_closed():await r.open_browser(url or self.local_origin+"/demo")
                elif url:await r.open_browser(url)
                else:await r.page.bring_to_front()
                r.simple_recording=True
                r.draft={**r.blank(),"id":str(uuid.uuid4()),"name":data.get("name","").strip() or "Recording "+datetime.now().strftime("%d %b %H:%M")}
                r.recorded_ms=0;r.recording_started=None;r.run_id=None
                await r.set_recording(True)
            finally:self.preparing=False
        elif kind=="play":
            self.preparing=True
            try:
                task=r.store.get(data["id"])
                self.preparing_task={"id":task["id"],"name":task["name"]}
                defaults=self.vault.read().get("defaults",{}).get(task["id"],{})
                values={**defaults,**data.get("values",{})}
                for step in task["steps"]:
                    if step["action"]=="upload" and isinstance(step.get("value"),dict) and "input" in step["value"]:
                        name=step["value"]["input"]
                        from pathlib import Path
                        if not values.get(name) or not Path(values[name]).is_file():
                            chosen=await asyncio.to_thread(r.file_selector or choose_file)
                            if not chosen:raise Invalid("Choose the file on this PC before pressing Play.")
                            values[name]=chosen
                await r.play(data["id"],values,data["revision"],key)
                r.draft=task
            finally:self.preparing=False;self.preparing_task=None
        elif kind=="view":
            if r.page and not r.page.is_closed():await r.page.bring_to_front()
            else:await r.open_browser(self.settings().get("url") or self.local_origin+"/demo")
        elif kind in {"pause","resume"}:await getattr(r,kind)()
        elif kind=="load":await r.command("load",data)
        elif kind=="new":await r.command("new",{})
        elif kind in {"rename","delete"}:
            task_id=data.get("id") or r.draft.get("id")
            active=r.draft.get("id") if r.recording or r.mode=="recording_paused" else r.run_id if r.busy() else None
            if task_id==active:raise Invalid("Stop this task first.")
            task=r.store.get(task_id)
            if kind=="delete":
                r.store.delete(task_id)
                defaults=self.vault.read().get("defaults",{})
                defaults.pop(task_id,None);self.vault.put("defaults",defaults)
                if r.draft.get("id")==task_id:r.draft=r.blank()
                if r.run_id==task_id:r.run_id=None
                return {"deleted_id":task_id,"tasks":r.store.list()}
            task=r.store.save({**task,"name":data["name"].strip()})
            if r.draft.get("id")==task_id:r.draft=task
            if r.run_id==task_id:r.run_name=task["name"]
            return {"task_id":task_id,"name":task["name"],"tasks":r.store.list()}
        elif kind=="repair-copy":
            if r.busy() or r.recording or r.mode=="recording_paused":raise Invalid("Stop the current task first.")
            original=r.store.get(data["id"])
            if r.store.revision(original)!=data["revision"]:raise Invalid("This recording changed. Select it again.")
            index=data["step"]-1
            if index>=len(original["steps"]) or original["steps"][index]["action"]!="unsupported":raise Invalid("Select a flagged step to correct.")
            task=copy.deepcopy(original);task["id"]=str(uuid.uuid4());task["name"]=original["name"][:85]+" — corrected"
            replacement=data["replacement"]
            task["steps"][index]=({"action":"navigate","value":replacement["value"],"timeout_ms":30000} if replacement["action"]=="navigate" else
                                   {"action":"wait","locator":{"by":"text","value":replacement["value"]},"timeout_ms":30000})
            task=r.store.save(task)
            meta=r.store.metadata(original["id"])
            r.store.metadata(task["id"],duration_ms=meta.get("duration_ms"),source_id=original["id"],source_revision=data["revision"],corrected_step=data["step"])
            defaults=self.vault.read().get("defaults",{})
            if original["id"] in defaults:
                defaults[task["id"]]=copy.deepcopy(defaults[original["id"]]);self.vault.put("defaults",defaults)
            r.draft=task
            return {"new_task_id":task["id"],"tasks":r.store.list()}
        elif kind=="edit":await r.command("save",data)
        elif kind=="reusable":
            if r.busy() or r.recording or r.mode=="recording_paused":raise Invalid("Stop first.")
            task=r.store.get(data["id"]) if data.get("id") else validate_task(r.draft);defaults=self.vault.read().get("defaults",{})
            saved=defaults.setdefault(task["id"],{})
            for i,step in enumerate(task["steps"]):
                if step["action"] in {"fill","select"} and isinstance(step.get("value"),str):
                    name=re.sub("[^a-z0-9]+","_",step["locator"]["value"].lower()).strip("_")[:30] or "value"
                    if name in {v["name"] for v in task["inputs"]}:name+="_"+str(i)
                    saved[name]=step["value"];task["inputs"].append({"name":name,"required":True});step["value"]={"input":name}
            self.vault.put("defaults",defaults);r.draft=r.store.save(task)
        elif kind=="inspect":
            task=r.store.get(data["id"]) if data.get("id") else r.draft
            defaults=self.vault.read().get("defaults",{}).get(task.get("id"),{})
            return {"task":task,"revision":r.store.revision(task),"values":{i["name"]:defaults.get(i["name"],"") for i in task["inputs"] if not any(s["action"]=="upload" and s.get("value")=={"input":i["name"]} for s in task["steps"])}}
        elif kind=="startup":
            startup(data["enabled"]);self.save_setting("startup",data["enabled"])
        elif kind=="choose-files":
            if r.busy() or r.recording or r.mode=="recording_paused":raise Invalid("Stop first.")
            for step in r.draft["steps"]:
                if step["action"]=="upload" and "file" in step.get("value",{}):
                    chosen=await asyncio.to_thread(r.file_selector or choose_file)
                    if not chosen:raise Invalid("No file selected.")
                    step["value"]={"file":self.vault.add_file(chosen)}
            r.draft=r.store.save(r.draft)
        return {"replacement_id":r.draft["id"]} if replacement else {}

    async def close(self):
        self.stopping=True;self.wake.set()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await self.task
        for task in list(self.active_commands.values()):task.cancel()
        if self.active_commands:await asyncio.gather(*self.active_commands.values(),return_exceptions=True)
        self.runner.state_changed=None
        self.db.close()
