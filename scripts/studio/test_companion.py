"""Focused V5 tests; disposable synthetic registry, no app or provider calls."""
import json
import os
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
import device_trust
import draft_ui
import studio
import test_draft_ui
import companion

@unittest.skipUnless(os.name == "nt", "Real Windows DPAPI required")
class DeviceTests(test_draft_ui.UITests):
    def persistent(self):
        server=draft_ui.DraftServer(self.home,"task-a","owner-a",idle_seconds=.1,persistent=True)
        thread=threading.Thread(target=server.run,daemon=True);thread.start()
        def cleanup():
            server.stopping=True;thread.join(4)
            self.assertFalse(thread.is_alive())
        self.addCleanup(cleanup)
        return server
    def device(self,s,operation,**extra):
        headers={"Origin":s.origin,"X-Studio-Local":"1",**extra.pop("headers",{})}
        return self.request(s,"/api/device",{"operation":operation,"origin":"https://os.example",**extra},headers=headers)
    def test_real_dpapi_rotation_restart_expiry_and_revocation(self):
        s=self.persistent()
        status,body,headers=self.device(s,"trust")
        self.assertEqual(status,200)
        access=json.loads(body)["token"]
        cookie=headers["Set-Cookie"].split(";",1)[0]
        self.assertIn("HttpOnly",headers["Set-Cookie"])
        self.assertIn("SameSite=Strict",headers["Set-Cookie"])
        self.assertNotIn(access,s.device.path.read_text())
        self.assertNotIn("https://os.example",s.device.path.read_text())
        self.assertTrue(s.device.valid(access))
        # Reopen/restart drops in-memory sessions; protected trust survives.
        s.device=device_trust.Trust(self.home,"task-a","owner-a")
        self.assertFalse(s.device.valid(access))
        status,body,new=self.device(s,"renew",headers={"Cookie":cookie,"X-Studio-Token":""})
        self.assertEqual(status,200)
        token=json.loads(body)["token"]
        self.assertNotEqual(token,access)
        self.assertEqual(self.device(s,"renew",headers={"Cookie":cookie})[0],403)
        cookie=new["Set-Cookie"].split(";",1)[0]
        self.assertEqual(self.device(s,"renew",origin="https://evil.example",headers={"Cookie":cookie})[0],403)
        self.assertEqual(self.device(s,"revoke",headers={"X-Studio-Token":token})[0],200)
        self.assertFalse(s.device.valid(token))
        self.assertEqual(self.device(s,"renew",headers={"Cookie":cookie})[0],403)
        record=s.device.read();self.assertTrue(all(r["expires"]==0 for r in record["records"].values()))
    def test_chrome_and_edge_trust_coexist(self):
        trust=device_trust.Trust(self.home,"task-a","owner-a")
        chrome,chrome_access=trust.enroll("https://os.example")
        edge,edge_access=trust.enroll("https://os.example")
        self.assertTrue(trust.valid(chrome_access),"Trusting Edge must not revoke Chrome")
        self.assertTrue(trust.valid(edge_access))
        chrome,_=trust.renew(chrome,"https://os.example")
        edge,_=trust.renew(edge,"https://os.example")
        trust.revoke()
        for cookie in (chrome,edge):
            with self.assertRaises(ValueError):trust.renew(cookie,"https://os.example")

    def test_origin_cookies_are_separate_and_cross_origin_renewal_fails(self):
        s=self.persistent()
        _,_,a=self.device(s,"trust")
        first=a["Set-Cookie"].split(";",1)[0]
        _,_,b=self.device(s,"trust",origin="http://127.0.0.1:18861")
        second=b["Set-Cookie"].split(";",1)[0]
        self.assertNotEqual(first.split("=")[0],second.split("=")[0])
        self.assertEqual(self.device(s,"renew",headers={"Cookie":first+"; "+second})[0],200)
        self.assertEqual(self.device(s,"renew",origin="https://evil.example",headers={"Cookie":second})[0],403)

    def test_legacy_enrollment_survives_schema_upgrade(self):
        trust=device_trust.Trust(self.home,"task-a","owner-a")
        trust.write({"task":"task-a","owner":"owner-a","origin":"https://os.example","hash":device_trust.digest("legacy-cookie"),"generation":"old","expires":time.time()+1000})
        cookie,_=trust.renew("legacy-cookie","https://os.example")
        trust.enroll("https://os.example")
        trust.renew(cookie,"https://os.example")

    def test_expiry_and_protected_file_tampering_fail_closed(self):
        clock=[1000]
        trust=device_trust.Trust(self.home,"task-a","owner-a",clock=lambda:clock[0])
        cookie,token=trust.enroll("https://os.example")
        clock[0]+=301;self.assertFalse(trust.valid(token))
        clock[0]+=device_trust.TRUST_SECONDS
        with self.assertRaises(ValueError):trust.renew(cookie,"https://os.example")
        obj=json.loads(trust.path.read_text());obj["protected"]="00"*100
        studio.atomic(trust.path,obj)
        with self.assertRaises(OSError):trust.read()
    def test_origin_host_csrf_and_owner_revalidation(self):
        s=self.persistent()
        self.assertEqual(self.request(s,"/api/device",[],headers={"Origin":s.origin,"X-Studio-Local":"1"})[0],403)
        for headers in [{"Origin":"https://os.example"},{"Origin":""},{"X-Studio-Local":""},{"Host":"evil.example"},{"X-Studio-Token":""}]:
            self.assertIn(self.device(s,"trust",headers=headers)[0],(401,403))
        _,_,h=self.device(s,"trust");cookie=h["Set-Cookie"].split(";",1)[0]
        registry=studio.read(self.home/".studio/registry.json");registry["tasks"][0]["owner"]="other"
        studio.atomic(self.home/".studio/registry.json",registry)
        self.assertEqual(self.device(s,"renew",headers={"Cookie":cookie})[0],403)
    def test_idle_companion_survives_preview_stops_independently(self):
        s=self.persistent();preview=Mock();preview.name="synthetic"
        s.preview_runtime=preview
        s.last_preview_activity=time.monotonic()-100
        s.idle_previews();preview.stop.assert_called_once()
        time.sleep(.15)
        self.assertEqual(self.request(s)[0],200)
        self.assertFalse(s.stopping)
    def test_trusted_session_cannot_replace_device_enrollment(self):
        s=self.persistent();_,body,_=self.device(s,"trust")
        token=json.loads(body)["token"]
        self.assertEqual(self.device(s,"trust",headers={"X-Studio-Token":token})[0],403)
        self.assertEqual(self.device(s,"stop",headers={"X-Studio-Token":token})[0],200)
        self.assertTrue(s.stopping)
    def test_fixed_port_conflict_never_takes_over(self):
        s=self.persistent()
        with self.assertRaises(OSError):
            draft_ui.DraftServer(self.home,"task-a","owner-a",persistent=True,port=s.server_port)
    def test_lock_and_config_are_per_task_no_reallocation(self):
        root,cfg=companion.config(self.home,"task-a","owner-a")
        self.assertEqual(companion.config(self.home,"task-a","owner-a"),(root,cfg))
        with companion.instance_lock(root/"test.lock"):
            with self.assertRaises(RuntimeError):
                with companion.instance_lock(root/"test.lock"):pass
        with companion.instance_lock(root/"test.lock"):pass
    def test_recovery_ignores_other_process_and_owner(self):
        registry=studio.read(self.home/".studio/registry.json")
        registry["preview_leases"]={"task-a":{"id":"lease","pid":123,"owner":"owner-a"}}
        studio.atomic(self.home/".studio/registry.json",registry)
        companion.recover_previews(self.home,"owner-a",456)
        self.assertIn("task-a",studio.read(self.home/".studio/registry.json")["preview_leases"])
        companion.recover_previews(self.home,"owner-a",123)
        self.assertEqual(studio.read(self.home/".studio/registry.json")["preview_leases"],{})
    def test_scheduled_watch_respects_intentional_stop(self):
        root,_=companion.config(self.home,"task-a","owner-a")
        (root/"stopped").touch()
        import sys
        with patch.object(sys,"argv",["companion.py","watch","--home",str(self.home),"--id","task-a","--owner","owner-a"]), patch.object(companion,"supervise") as supervise:
            companion.main()
            supervise.assert_not_called()

    def test_wrong_owner_cannot_start(self):
        with self.assertRaises(RuntimeError):companion.config(self.home,"task-a","other")

if __name__=="__main__":unittest.main()
