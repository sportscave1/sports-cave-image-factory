"""Real PostgreSQL relay/security tests. Refuses any non-loopback test database."""
import json
from pathlib import Path
import secrets
import unittest
import uuid
import psycopg
from psycopg.rows import dict_row
from task_recorder.relay_store import Relay
from task_recorder.schema import Invalid,safe_url
from task_recorder.device import origin

DSN="postgresql://postgres:synthetic-recorder-only@127.0.0.1:55439/recorder"
def connect(): return psycopg.connect(DSN,row_factory=dict_row)

class Users:
    def __init__(self,owner):self.id=owner;self.active=True
    def get_user(self,key):return {"id":key,"role":"admin","is_active":self.active,"display_name":"Synthetic test admin"}

class RelayTests(unittest.TestCase):
    def setUp(self):
        self.owner=str(uuid.uuid4());self.users=Users(self.owner);self.now=1000.
        self.relay=Relay(connect,self.users,lambda:self.now)
        self.device=str(uuid.uuid4());self.key=secrets.token_urlsafe(32);self.boot=str(uuid.uuid4())
        challenge=self.relay.challenge(self.owner)
        self.relay.claim(challenge["code"],self.device,self.key,"Synthetic Windows PC")
        self.poll()

    def tearDown(self):
        with connect() as conn:
            conn.execute("DELETE FROM task_recorder_private.commands WHERE owner_id=%s",(self.owner,))
            conn.execute("DELETE FROM task_recorder_private.pairings WHERE owner_id=%s",(self.owner,))
            conn.execute("DELETE FROM task_recorder_private.devices WHERE owner_id=%s",(self.owner,))

    def poll(self,**extra):
        return self.relay.exchange(self.device,self.key,{"boot_id":self.boot,"epoch":1,"state":{"mode":"idle","tasks":[]},"state_version":1,**extra})

    def test_single_use_short_lived_pairing_and_credential(self):
        c=self.relay.challenge(self.owner);other=str(uuid.uuid4())
        self.relay.inspect_pair(c["code"])
        with self.assertRaises(Invalid):self.relay.claim(c["code"],other,"bad","PC")
        self.relay.claim(c["code"],other,secrets.token_urlsafe(32),"PC")
        with self.assertRaises(Invalid):self.relay.claim(c["code"],str(uuid.uuid4()),self.key,"Other PC")
        c=self.relay.challenge(self.owner)
        self.now+=301
        with self.assertRaises(Invalid):self.relay.inspect_pair(c["code"])
        with self.assertRaises(PermissionError):self.relay.authenticate(self.device,"invalid-key")

    def test_ownership_revoke_and_removed_admin(self):
        with self.assertRaises(PermissionError):self.relay.enqueue(str(uuid.uuid4()),self.device,str(uuid.uuid4()),"record",{})
        with self.assertRaises(PermissionError):self.relay.revoke(str(uuid.uuid4()),self.device)
        self.users.active=False
        with self.assertRaises(PermissionError):self.relay.authenticate(self.device,self.key)
        self.users.active=True;self.relay.revoke(self.owner,self.device)
        with self.assertRaises(PermissionError):self.poll()

    def test_duplicate_start_and_priority_stop(self):
        key=str(uuid.uuid4())
        self.relay.enqueue(self.owner,self.device,key,"record",{})
        self.assertEqual(self.relay.enqueue(self.owner,self.device,key,"record",{})["id"],key)
        with self.assertRaises(Invalid):self.relay.enqueue(self.owner,self.device,str(uuid.uuid4()),"record",{})
        stop=str(uuid.uuid4());self.relay.enqueue(self.owner,self.device,stop,"stop",{})
        commands=self.poll()["commands"]
        self.assertEqual([c["id"] for c in commands],[stop])
        self.poll(acks=[{"id":stop,"status":"applied","receipt":{}}])
        self.assertIsNone(self.relay.devices(self.owner)[0]["active_run"])

    def test_restart_reconciliation_and_expired_start(self):
        command=str(uuid.uuid4());self.relay.enqueue(self.owner,self.device,command,"record",{})
        restarted=str(uuid.uuid4())
        result=self.relay.exchange(self.device,self.key,{"boot_id":restarted,"epoch":2,"state_version":1,"state":{"mode":"interrupted"}})
        self.assertFalse(result["commands"])
        self.assertTrue(self.relay.devices(self.owner)[0]["needs_review"])
        with self.assertRaises(PermissionError):self.poll()
        with self.assertRaises(Invalid):self.relay.enqueue(self.owner,self.device,str(uuid.uuid4()),"record",{})

    def test_old_snapshots_cannot_roll_back_progress(self):
        self.poll(state={"mode":"running","step":5},state_version=3)
        self.poll(state={"mode":"running","step":1},state_version=2)
        self.assertEqual(self.relay.devices(self.owner)[0]["state"]["step"],5)

    def test_data_only_controls_and_url_privacy(self):
        with self.assertRaises(Invalid):self.relay.enqueue(self.owner,self.device,str(uuid.uuid4()),"evaluate",{"script":"anything"})
        with self.assertRaises(Invalid):self.relay.enqueue(self.owner,self.device,str(uuid.uuid4()),"record",{"script":"anything"})
        self.assertEqual(safe_url("https://example.com/products?category=sport&page=2"),"https://example.com/products?category=sport&page=2")
        for value in ["https://example.com/?access_token=abc","https://example.com/#id_token=abc","https://example.com/?code=abc","https://example.com/session/abc"]:
            with self.assertRaises(Invalid):safe_url(value)
        with self.assertRaises(Invalid):origin("http://sports-cave-image-factory.onrender.com")

    def test_private_schema_rls(self):
        with connect() as conn:
            rows=conn.execute("SELECT relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='task_recorder_private' AND c.relkind='r'").fetchall()
            self.assertTrue(rows and all(r["relrowsecurity"] for r in rows))
            allowed=conn.execute("SELECT has_schema_privilege('public','task_recorder_private','USAGE') AS allowed").fetchone()["allowed"]
            self.assertFalse(allowed)

if __name__=="__main__":unittest.main()
