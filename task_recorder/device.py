"""Outbound HTTPS client and crash-safe command receipts for the local V1 engine."""
import asyncio
import contextlib
import hashlib
import json
import re
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
from .windows import startup, choose_file

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
    fields={"record":{"url"},"play":{"id","revision","values"},"load":{"id"},"rename":{"name"},
            "edit":{"task"},"startup":{"enabled"}}
    keys(data,fields.get(kind,set()))
    if "url" in data: safe_url(data["url"])
    if kind=="play":
        keys(data,fields[kind],{"id","revision"})
        if not re.fullmatch("[a-f0-9]{64}",str(data["revision"])): raise Invalid("Select the saved recording again.")
        values=data.get("values",{})
        if not isinstance(values,dict) or len(values)>50: raise Invalid("Invalid inputs.")
        for name,value in values.items():
            text(name,40);text(value,empty=True)
            if value.startswith(("http://","https://")):safe_url(value)
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
        self.acks={}
        self.fence=0
        self.active_commands={}
        self.control_lock=asyncio.Lock()
        self.preparing=False
        self.client=None
        self.task=None

    def credentials(self):
        return self.vault.read().get("device")

    def snapshot(self):
        s=self.runner.state()
        s.pop("draft",None)
        s.update(operation_id=self.operation_id,selected_id=self.runner.draft.get("id"),
                 starting_url=self.settings().get("url",""),startup=self.settings().get("startup",False),
                 connection="connected" if self.connected else "reconnecting")
        if self.preparing and s["mode"] in {"idle","stopped","completed"}: s["mode"]="starting"
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
        if interrupted:
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
                    timeout=httpx.Timeout(22 if wait else 5,connect=4))
        if response.status_code==403:
            await self.network_lost(True)
            raise Invalid("Device disconnected.")
        response.raise_for_status()
        self.connected=True
        result=response.json()
        for command in result["commands"]:
            command["valid_for"]-=time.monotonic()-started
        return result

    async def publish(self,device):
        last=None
        while not self.stopping and self.credentials()==device:
            s=self.snapshot()
            fingerprint=json.dumps(s,sort_keys=True)
            if fingerprint!=last or self.acks:
                self.state_version+=1
                outgoing=list(self.acks.values())
                await self.exchange(device,{"state":s,"state_version":self.state_version,"acks":outgoing})
                for ack in outgoing:
                    if self.acks.get(ack["id"])==ack:self.acks.pop(ack["id"],None)
                last=fingerprint
            await asyncio.sleep(.65 if self.runner.busy() or self.runner.recording or self.preparing else 2)

    async def loop(self):
        self.client=httpx.AsyncClient(follow_redirects=False,trust_env=False)
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
                    first=await self.exchange(device,{"state":self.snapshot(),"state_version":self.state_version})
                    publisher=asyncio.create_task(self.publish(device))
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
                except asyncio.CancelledError:raise
                except Exception:
                    await self.network_lost()
                    await asyncio.sleep(2)
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
            return
        self.db.execute("INSERT INTO commands VALUES(?,?,?,?)",(key,fingerprint,"accepted","{}"));self.db.commit()
        try:
            payload(kind,data)
            if command["boot_id"]!=self.boot_id or command["fence"]<self.fence or command["valid_for"]<=0:
                raise Invalid("This control expired. Press it again.")
            if kind in {"stop","stop-save"}:
                for other,task in list(self.active_commands.items()):
                    if other!=key:task.cancel()
                await self.runner.stop()
                self.preparing=False
                self.runner.message="Recording saved." if self.runner.draft.get("steps") and self.runner.simple_recording else "Stopped."
                result={}
            else:
                async with self.control_lock:
                    if command["fence"]<self.fence:raise Invalid("Cancelled by Stop.")
                    if time.monotonic()>=deadline:raise Invalid("This control expired. Press it again.")
                    result=await self.perform(kind,data,key)
            status="applied"
        except asyncio.CancelledError:
            status="uncertain";result={"message":"Cancelled while applying a control. Check the previous result."}
        except (Invalid,ValueError) as error:
            status="rejected";result={"message":str(error)}
        except Exception:
            status="uncertain";result={"message":"This control could not be confirmed. Press Stop and check the browser."}
        self.db.execute("UPDATE commands SET status=?,receipt=? WHERE id=?",(status,json.dumps(result),key));self.db.commit()
        self.acks[key]={"id":key,"status":status,"receipt":result}

    async def perform(self,kind,data,key):
        r=self.runner
        if kind in {"record","play"}:
            if r.busy() or r.recording or r.mode=="recording_paused":raise Invalid("Already in progress. Press Stop first.")
            self.operation_id=key
            atomic(self.root/"device-session.json",{"boot_id":self.boot_id,"epoch":self.epoch,"operation_id":key})
        if kind=="record":
            self.preparing=True
            try:
                url=data.get("url") or self.settings().get("url")
                if url:self.save_setting("url",safe_url(url))
                if not r.context:await r.open_browser(url or self.local_origin+"/demo")
                elif url:await r.open_browser(url)
                else:await r.page.bring_to_front()
                r.simple_recording=True
                r.draft={**r.blank(),"id":str(uuid.uuid4()),"name":"Recording "+datetime.now().strftime("%d %b %H:%M")}
                await r.set_recording(True)
            finally:self.preparing=False
        elif kind=="play":
            task=r.store.get(data["id"])
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
        elif kind=="view":
            if r.page and not r.page.is_closed():await r.page.bring_to_front()
            else:await r.open_browser(self.settings().get("url") or self.local_origin+"/demo")
        elif kind in {"pause","resume"}:await getattr(r,kind)()
        elif kind=="load":await r.command("load",data)
        elif kind=="new":await r.command("new",{})
        elif kind=="rename":
            await r.command("save",{"task":{**r.draft,"name":data["name"]}})
        elif kind=="edit":await r.command("save",data)
        elif kind=="reusable":
            if r.busy() or r.recording or r.mode=="recording_paused":raise Invalid("Stop first.")
            task=validate_task(r.draft);defaults=self.vault.read().get("defaults",{})
            saved=defaults.setdefault(task["id"],{})
            for i,step in enumerate(task["steps"]):
                if step["action"] in {"fill","select"} and isinstance(step.get("value"),str):
                    name=re.sub("[^a-z0-9]+","_",step["locator"]["value"].lower()).strip("_")[:30] or "value"
                    if name in {v["name"] for v in task["inputs"]}:name+="_"+str(i)
                    saved[name]=step["value"];task["inputs"].append({"name":name,"required":True});step["value"]={"input":name}
            self.vault.put("defaults",defaults);r.draft=r.store.save(task)
        elif kind=="inspect":
            defaults=self.vault.read().get("defaults",{}).get(r.draft.get("id"),{})
            return {"task":r.draft,"values":{i["name"]:defaults.get(i["name"],"") for i in r.draft["inputs"] if not any(s["action"]=="upload" and s.get("value")=={"input":i["name"]} for s in r.draft["steps"])}}
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
        return {}

    async def close(self):
        self.stopping=True;self.wake.set()
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):await self.task
        for task in list(self.active_commands.values()):task.cancel()
        if self.active_commands:await asyncio.gather(*self.active_commands.values(),return_exceptions=True)
        self.db.close()
