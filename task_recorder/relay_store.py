"""Durable, owner-scoped relay. All browser/task execution stays on the PC."""
import hashlib
import json
import secrets
import time
import uuid
from .schema import Invalid, text

KINDS = {"record", "stop", "stop-save", "play", "pause", "resume", "view", "load",
         "new", "rename", "reusable", "edit", "inspect", "startup", "choose-files", "delete", "repair-copy"}
STARTS = {"record", "play"}
TERMINAL = {"idle", "completed", "stopped", "interrupted"}
PREFIX = "task_recorder_private."

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def identifier(value):
    try: return str(uuid.UUID(str(value)))
    except (ValueError, TypeError): raise Invalid("Invalid request ID.")

class Relay:
    def __init__(self, connect, users, clock=time.time):
        self.connect, self.users, self.clock = connect, users, clock

    def owner(self, owner_id):
        import os_accounts
        user = self.users.get_user(owner_id)
        if not user or not os_accounts.is_admin(user) or not os_accounts.account_is_active(user):
            raise PermissionError("Administrator access was revoked.")
        return user

    def challenge(self, owner_id):
        self.owner(owner_id)
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(12))
        now, key = self.clock(), str(uuid.uuid4())
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO task_recorder_private.pairings(id,owner_id,code_hash,expires,created) VALUES(%s,%s,%s,%s,%s)",
                        (key,owner_id,digest(code),now+300,now))
        return {"id":key,"code":code[:4]+"-"+code[4:8]+"-"+code[8:],"expires":now+300}

    @staticmethod
    def clean_code(code):
        code = str(code).replace("-","").replace(" ","").upper()
        if len(code)!=12 or not code.isalnum(): raise Invalid("Pairing code is invalid or expired.")
        return code

    def inspect_pair(self, code):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM task_recorder_private.pairings WHERE code_hash=%s",(digest(self.clean_code(code)),))
            row = cur.fetchone()
        if not row or row["expires"]<self.clock() or row["device_id"]:
            raise Invalid("Pairing code is invalid, expired or already used.")
        user = self.owner(row["owner_id"])
        return {"account":user.get("display_name") or user.get("username") or "Sports Cave administrator",
                "expires":row["expires"]}

    def claim(self, code, device_id, key, name):
        identifier(device_id)
        text(name,80)
        if not isinstance(key,str) or len(key)!=43: raise Invalid("Invalid device credential.")
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM task_recorder_private.pairings WHERE code_hash=%s FOR UPDATE",
                        (digest(self.clean_code(code)),))
            row=cur.fetchone()
            if not row or row["expires"]<self.clock(): raise Invalid("Pairing code is invalid or expired.")
            self.owner(row["owner_id"])
            if row["device_id"]:
                cur.execute("SELECT id FROM task_recorder_private.devices WHERE id=%s AND key_hash=%s AND revoked=false",
                            (device_id,digest(key)))
                if row["device_id"]!=device_id or not cur.fetchone(): raise Invalid("Pairing code was already used.")
            else:
                cur.execute("INSERT INTO task_recorder_private.devices(id,owner_id,key_hash,name) VALUES(%s,%s,%s,%s)",
                            (device_id,row["owner_id"],digest(key),name))
                cur.execute("UPDATE task_recorder_private.pairings SET device_id=%s WHERE id=%s",(device_id,row["id"]))
        return {"device_id":device_id,"name":name}

    def authenticate(self, device_id, key):
        identifier(device_id)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM task_recorder_private.devices WHERE id=%s AND key_hash=%s AND revoked=false",
                        (device_id,digest(key)))
            row=cur.fetchone()
        if not row: raise PermissionError("This PC is not paired or has been disconnected.")
        self.owner(row["owner_id"])
        return row

    def devices(self, owner_id):
        self.owner(owner_id)
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT id,name,last_seen,state,seq,active_run,needs_review FROM task_recorder_private.devices WHERE owner_id=%s AND revoked=false ORDER BY name",
                        (owner_id,))
            rows=cur.fetchall()
        for row in rows:
            row["connected"]=self.clock()-row["last_seen"]<35
        return rows

    def revoke(self, owner_id, device_id):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("UPDATE task_recorder_private.devices SET revoked=true,seq=seq+1 WHERE id=%s AND owner_id=%s RETURNING id",
                        (device_id,owner_id))
            if not cur.fetchone(): raise PermissionError("PC does not belong to this account.")
            cur.execute("UPDATE task_recorder_private.commands SET status='cancelled',payload='{}'::jsonb WHERE device_id=%s AND status IN ('queued','dispatched')",(device_id,))

    def enqueue(self, owner_id, device_id, command_id, kind, payload):
        identifier(device_id); identifier(command_id)
        if kind not in KINDS: raise Invalid("Unsupported recorder control.")
        if not isinstance(payload,dict) or len(json.dumps(payload))>128000: raise Invalid("Invalid recorder request.")
        from .device import payload as validate_payload
        validate_payload(kind,payload)
        fingerprint=digest(json.dumps({"kind":kind,"payload":payload},sort_keys=True,separators=(",",":")))
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM task_recorder_private.devices WHERE id=%s AND owner_id=%s AND revoked=false FOR UPDATE",(device_id,owner_id))
            device=cur.fetchone()
            if not device: raise PermissionError("PC does not belong to this account.")
            cur.execute("SELECT * FROM task_recorder_private.commands WHERE id=%s",(command_id,))
            old=cur.fetchone()
            if old:
                if old["device_id"]!=device_id or old["owner_id"]!=owner_id or old["request_hash"]!=fingerprint:
                    raise PermissionError("Command ID belongs to another request.")
                return self.public_command(old)
            if self.clock()-device["last_seen"]>35:
                raise Invalid("This PC is offline. Start Task Recorder on that PC, then try again.")
            if kind in {"delete","rename"} and payload.get("id")==device["state"].get("active_task_id") and device["active_run"]:
                raise Invalid("Stop this task first.")
            if kind=="repair-copy" and device["state"].get("protocol",1)<3:
                raise Invalid("Update the PC helper from Settings before correcting a copy.")
            if kind == "delete" and device["state"].get("protocol",1)<2:
                raise Invalid("Update the PC helper from Settings before deleting recordings.")
            if kind in STARTS:
                if device["active_run"]: raise Invalid("A recording or playback is already in progress. Use Stop first.")
                if device["needs_review"]: raise Invalid("The last run was interrupted. Check the browser, then press Stop before starting again.")
                cur.execute("UPDATE task_recorder_private.devices SET active_run=%s WHERE id=%s",(command_id,device_id))
            if kind in {"stop","stop-save"}:
                cur.execute("UPDATE task_recorder_private.devices SET fence=fence+1 WHERE id=%s RETURNING fence",(device_id,))
                device["fence"]=cur.fetchone()["fence"]
                cur.execute("UPDATE task_recorder_private.commands SET status='cancelled',payload='{}'::jsonb WHERE device_id=%s AND status IN ('queued','dispatched')",(device_id,))
            now=self.clock()
            cur.execute("INSERT INTO task_recorder_private.commands(id,device_id,owner_id,kind,request_hash,payload,boot_id,fence,created,expires) VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s) RETURNING *",
                        (command_id,device_id,owner_id,kind,fingerprint,json.dumps(payload),device["boot_id"],device["fence"],now,now+(120 if kind in {"stop","stop-save"} else 30)))
            return self.public_command(cur.fetchone())

    @staticmethod
    def public_command(row):
        return {k:row[k] for k in ("id","kind","status","receipt")}

    def receipt(self, owner_id, device_id, command_id):
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM task_recorder_private.commands WHERE id=%s AND device_id=%s AND owner_id=%s",(command_id,device_id,owner_id))
            row=cur.fetchone()
        if not row: raise PermissionError("Command not available to this account.")
        return self.public_command(row)

    def exchange(self, device_id, key, body):
        self.authenticate(device_id,key)
        boot=identifier(body.get("boot_id"))
        epoch=body.get("epoch")
        if not isinstance(epoch,int) or epoch<1: raise Invalid("Invalid helper session.")
        snapshot=body.get("state")
        delta=body.get("state_delta")
        if delta is not None and (snapshot is not None or not isinstance(delta,dict) or
                set(delta)!={"base_version","changes"} or not isinstance(delta["base_version"],int) or
                not isinstance(delta["changes"],dict) or len(json.dumps(delta))>180000):
            raise Invalid("Invalid helper state update.")
        if snapshot is not None and (not isinstance(snapshot,dict) or len(json.dumps(snapshot))>180000): raise Invalid("Invalid helper state.")
        # These keys are produced by the helper, never cookies or browser sessions.
        allowed={"mode","message","step","total","action","can_resume","browser_open","recording","privacy_pause","tasks",
                 "operation_id","starting_url","selected_id","startup","connection","protocol","active_task_id","active_task_name"}
        if snapshot is not None and set(snapshot)-allowed: raise Invalid("Unsupported helper state fields.")
        if delta is not None and set(delta["changes"])-allowed: raise Invalid("Unsupported helper state fields.")
        if not isinstance(body.get("acks",[]),list):raise Invalid("Invalid command acknowledgements.")
        with self.connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM task_recorder_private.devices WHERE id=%s AND key_hash=%s AND revoked=false FOR UPDATE",(device_id,digest(key)))
            device=cur.fetchone()
            if not device: raise PermissionError("PC was disconnected.")
            new_boot=device["boot_id"]!=boot
            if new_boot:
                if epoch<=device["epoch"]: raise PermissionError("An old helper session cannot reconnect.")
                cur.execute("UPDATE task_recorder_private.commands SET status='uncertain',payload='{}'::jsonb WHERE device_id=%s AND status IN ('queued','dispatched')",(device_id,))
                device["needs_review"]=bool(device["active_run"]) or device["needs_review"] or (snapshot or {}).get("mode")=="interrupted"
                device["active_run"]=None
                device["state_version"]=0
                cur.execute("UPDATE task_recorder_private.devices SET boot_id=%s,epoch=%s,active_run=NULL,needs_review=%s,state_version=0 WHERE id=%s",
                            (boot,epoch,device["needs_review"],device_id))
            version=body.get("state_version",0)
            if not isinstance(version,int): raise Invalid("Invalid helper state version.")
            resync=False
            if delta is not None:
                if new_boot or delta["base_version"]!=device["state_version"] or version<=device["state_version"]:
                    resync=True
                else:
                    snapshot={**device["state"],**delta["changes"]}
                    if len(json.dumps(snapshot))>180000: raise Invalid("Invalid helper state.")
            if snapshot is None or version<=device["state_version"]:
                snapshot=device["state"]
            else:
                device["state_version"]=version
            for ack in body.get("acks",[])[:30]:
                if not isinstance(ack,dict): continue
                status=ack.get("status")
                if status not in {"applied","rejected","uncertain"}: continue
                receipt=ack.get("receipt",{})
                if not isinstance(receipt,dict) or len(json.dumps(receipt))>128000: raise Invalid("Invalid receipt.")
                cur.execute("UPDATE task_recorder_private.commands SET status=%s,receipt=%s::jsonb,payload='{}'::jsonb WHERE id=%s AND device_id=%s AND boot_id=%s AND status IN ('queued','dispatched') RETURNING kind",
                            (status,json.dumps(receipt),ack.get("id"),device_id,boot))
                accepted=cur.fetchone()
                if accepted and accepted["kind"] in {"stop","stop-save"} and status=="applied":
                    device["active_run"]=None
                    device["needs_review"]=False
                elif accepted and status=="rejected" and accepted["kind"] in STARTS:
                    device["active_run"]=None
                elif accepted and status=="uncertain":
                    device["needs_review"]=True
            if snapshot.get("operation_id")==device["active_run"] and snapshot.get("mode") in TERMINAL:
                device["active_run"]=None
                if snapshot.get("mode")=="interrupted": device["needs_review"]=True
            now=self.clock()
            cur.execute("UPDATE task_recorder_private.commands SET status='expired',payload='{}'::jsonb WHERE device_id=%s AND status IN ('queued','dispatched') AND expires<%s RETURNING id",(device_id,now))
            expired={row["id"] for row in cur.fetchall()}
            if device["active_run"] in expired:
                device["active_run"]=None
                device["needs_review"]=True
            changed=snapshot!=device["state"]
            cur.execute("UPDATE task_recorder_private.devices SET state=%s::jsonb,last_seen=%s,seq=seq+%s,active_run=%s,needs_review=%s,state_version=%s WHERE id=%s",
                        (json.dumps(snapshot),now,1 if changed else 0,device["active_run"],device["needs_review"],device["state_version"],device_id))
            cur.execute("SELECT * FROM task_recorder_private.commands WHERE device_id=%s AND boot_id=%s AND status IN ('queued','dispatched') AND expires>%s ORDER BY CASE WHEN kind IN ('stop','stop-save') THEN 0 ELSE 1 END,created LIMIT 10",(device_id,boot,now))
            commands=cur.fetchall()
            for command in commands:
                cur.execute("UPDATE task_recorder_private.commands SET status='dispatched' WHERE id=%s",(command["id"],))
        return {"commands":[{k:c[k] for k in ("id","kind","payload","fence","boot_id")} | {"valid_for":max(0,c["expires"]-self.clock())} for c in commands],
                "fence":device["fence"],"state_delta":True,"state_resync":resync}
