"""Disposable in-memory Git/provider fixtures: no commit, merge, network or Docker."""
import copy
import hashlib
import json
import unittest
from unittest.mock import patch
from pathlib import Path
import releases as r
import studio
import test_drafts
import test_draft_ui

A="a"*40;B="b"*40;C="c"*40;D="d"*40
class Objects:
    def __init__(self):
        self.data={};self.trees={};self.edges=set()
    def file(self,text,mode="100644"):
        value=text.encode();oid=hashlib.sha1(value).hexdigest();self.data[oid]=value
        return [mode,"blob",oid]
    def tree(self,sha):return copy.deepcopy(self.trees[sha])
    def blob(self,entry):
        if entry[0] not in {"100644","100755"}:raise ValueError("Links forbidden")
        return self.data[entry[2]]
    def blobs(self,entries):return [self.blob(e) for e in entries]
    def ancestor(self,a,b):return a==b or (a,b) in self.edges

def fixture():
    repo=Objects();repo.trees[A]={"screen.html":repo.file("Original"),"layout.css":repo.file("body{}")}
    repo.trees[B]={**repo.trees[A],"screen.html":repo.file("Accepted")}
    repo.trees[C]={**repo.trees[A],"layout.css":repo.file("body{color:red}")}
    repo.trees[D]={**repo.trees[A],"screen.html":repo.file("Conflicting")}
    repo.edges={(A,B),(A,C),(A,D)}
    return repo

def selected(sha=B,id="task-b"):
    return {"task_id":id,"name":id,"owner":"feature-owner","category":"CORE","base_commit":A,"commit":sha}

def record(repo=None):
    repo=repo or fixture();p=r.assemble(repo,A,[selected()])
    p.update(id="candidate",owner="release-owner",release_task="release",status="Prepared",version=1,checks={})
    p["fingerprint"]=r.fingerprint(p);r.audit(p,"prepared",{})
    p["checks"]={n:{"passed":True,"fingerprint":p["fingerprint"]} for n in r.REQUIRED}
    return p

def approved():
    p=record();r.review(p,"release-owner","REVIEW "+B);r.approve(p,"release-owner","APPROVE "+B);return p

class AssemblyTests(unittest.TestCase):
    def test_independent_selected_files_combine_without_git_writes(self):
        repo=fixture();p=r.assemble(repo,A,[selected(),selected(C,"task-c")])
        self.assertEqual(repo.blob(p["tree"]["screen.html"]),b"Accepted")
        self.assertEqual(repo.blob(p["tree"]["layout.css"]),b"body{color:red}")
        self.assertIsNone(p["candidate_commit"])
    def test_exact_selected_commit_is_locked(self):self.assertEqual(record()["candidate_commit"],B)
    def test_base_ancestor_selection_is_not_reverse_applied(self):
        repo=fixture();p=r.assemble(repo,B,[selected()]);self.assertEqual(p["candidate_commit"],B);self.assertEqual(p["changed_files"],[])
    def test_uncertain_same_file_changes_block(self):
        with self.assertRaisesRegex(ValueError,"Conflicting"):r.assemble(fixture(),A,[selected(),selected(D,"task-d")])
    def test_duplicates_and_empty_selection_block(self):
        for x in [[],[selected(),selected()]]:
            with self.assertRaises(ValueError):r.assemble(fixture(),A,x)
    def test_unrelated_history_blocks(self):
        repo=fixture();repo.edges.clear()
        with self.assertRaises(ValueError):r.assemble(repo,A,[selected()])
    def test_sensitive_and_traversal_paths_block(self):
        for name in ["../x","C:/x","a\\b",".env",".aws/credentials","secrets.toml","private.key","x.db"]:
            with self.assertRaises(ValueError):r.safe_name(name)
    def test_symlink_change_blocks(self):
        repo=fixture();repo.trees[B]["link"]=repo.file("target","120000")
        with self.assertRaises(ValueError):r.assemble(repo,A,[selected()])
    def test_migration_and_worker_changes_flagged(self):
        repo=fixture();repo.trees[B]["migrations/x.sql"]=repo.file("ALTER TABLE synthetic ADD COLUMN n int;");repo.trees[B]["example_worker.py"]=repo.file("pass")
        p=r.assemble(repo,A,[selected()]);self.assertEqual(set(p["risks"]),{"database_migration","worker_or_deployment_compatibility"})

class ExportTests(unittest.TestCase):
    def test_candidate_export_reads_only_locked_objects(self):
        import io,tarfile,preview_export
        repo=fixture()
        for sha in (A,B):
            repo.trees[sha]["app.py"]=repo.file("# immutable application\n")
            repo.trees[sha]["sc_auth.py"]=repo.file('DEFAULT_APP_PASSWORD = "synthetic-fixture"\n')
            repo.trees[sha][".env"]=repo.file("SECRET=not-exported")
            repo.trees[sha]["example_worker.py"]=repo.file("# excluded worker")
        p=record(repo)
        with patch.object(preview_export,"source_bytes",side_effect=AssertionError("No working files")):
            archive,manifest=preview_export.capture_objects(repo,p)
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            self.assertEqual(tar.extractfile("source/app.py").read(),b"# immutable application\n")
            self.assertNotIn("source/.env",tar.getnames());self.assertNotIn("source/example_worker.py",tar.getnames())
            self.assertIn(b"StudioOnly-2026",tar.extractfile("source/sc_auth.py").read())
        self.assertEqual(manifest["commit"],B);self.assertEqual(manifest["fingerprint"],p["fingerprint"])

class ApprovalTests(unittest.TestCase):
    def test_review_then_exact_owner_approval(self):self.assertEqual(approved()["status"],"Approved for simulation")
    def test_missing_review_blocks(self):
        with self.assertRaises(ValueError):r.approve(record(),"release-owner","APPROVE "+B)
    def test_wrong_owner_or_revision_blocks(self):
        for owner,text in [("other","REVIEW "+B),("release-owner","REVIEW "+A)]:
            with self.assertRaises(ValueError):r.review(record(),owner,text)
    def test_failed_or_missing_tests_block(self):
        for missing in [True,False]:
            p=record()
            if missing:p["checks"].pop("combined_runtime")
            else:p["checks"]["combined_runtime"]["passed"]=False
            with self.assertRaises(ValueError):r.review(p,"release-owner","REVIEW "+B)
    def test_test_fingerprint_cannot_be_reused(self):
        p=record();p["checks"]["static"]["fingerprint"]="stale"
        with self.assertRaises(ValueError):r.tested(p)
    def test_uncommitted_composition_cannot_be_approved(self):
        p=record();combined=r.assemble(fixture(),A,[selected(),selected(C,"task-c")]);p.update(combined);p["fingerprint"]=r.fingerprint(p);p["checks"]={n:{"passed":True,"fingerprint":p["fingerprint"]} for n in r.REQUIRED}
        with self.assertRaisesRegex(ValueError,"authorised immutable"):r.tested(p)
    def test_migration_cannot_be_waived_by_checkbox(self):
        p=record();p["risks"]=["database_migration"];p["fingerprint"]=r.fingerprint(p);p["checks"]={n:{"passed":True,"fingerprint":p["fingerprint"]} for n in r.REQUIRED}
        with self.assertRaisesRegex(ValueError,"migration backup"):r.tested(p)
    def test_candidate_and_audit_tampering_rejected(self):
        for target in ["tree","history"]:
            p=record()
            if target=="tree":p["tree"].clear()
            else:p["history"][0]["detail"]="tampered"
            with self.assertRaises(ValueError):r.intact(p)

class ExecutorTests(unittest.TestCase):
    def test_success_is_simulated_never_live(self):
        p=approved();r.simulate(p,"release-owner","SIMULATE "+B)
        self.assertEqual(p["status"],"Simulation verified");self.assertFalse(r.live_status()["verified"])
        self.assertEqual({x["revision"] for x in p["last_simulation"]["services"].values()},{B})
    def test_failures_never_become_live(self):
        for scenario in ["service_failure","revision_mismatch","unhealthy"]:
            p=approved();r.simulate(p,"release-owner","SIMULATE "+B,scenario);self.assertEqual(p["status"],"Simulation failed");self.assertIsNone(p["approval"])
    def test_duplicate_and_concurrent_attempts_block(self):
        p=approved();r.simulate(p,"release-owner","SIMULATE "+B)
        with self.assertRaises(ValueError):r.simulate(p,"release-owner","SIMULATE "+B)
        with self.assertRaises(ValueError):r.approve(p,"release-owner","APPROVE "+B)
        p=approved();p["status"]="Simulating"
        with self.assertRaises(ValueError):r.simulate(p,"release-owner","SIMULATE "+B)
    def test_owner_approval_and_final_confirmation_required(self):
        for p,owner,text in [(record(),"release-owner","SIMULATE "+B),(approved(),"other","SIMULATE "+B),(approved(),"release-owner","SIMULATE "+A)]:
            with self.assertRaises(ValueError):r.simulate(p,owner,text)
    def test_application_worker_ids_and_revision_required(self):
        receipt=r.MockExecutor().deploy(B);del receipt["services"]["sports-cave-seo-worker"]
        with self.assertRaises(ValueError):r.verify_receipt(receipt,B)
    def test_non_mock_provider_receipt_rejected(self):
        receipt=r.MockExecutor().deploy(B);receipt["simulation"]=False
        with self.assertRaises(ValueError):r.verify_receipt(receipt,B)
    def test_recovery_uses_previous_verified_sha(self):
        p=approved();previous=r.MockExecutor().deploy(A);r.simulate(p,"release-owner","SIMULATE "+B,previous=previous)
        r.recover(p,"release-owner","RECOVER "+A);self.assertEqual(p["recovery"]["github"]["revision"],A)
    def test_missing_or_wrong_recovery_revision_blocks(self):
        p=approved();r.simulate(p,"release-owner","SIMULATE "+B)
        with self.assertRaises(ValueError):r.recover(p,"release-owner","RECOVER "+A)
    def test_static_syntax_failure_explained(self):
        repo=fixture();repo.trees[B]["bad.py"]=repo.file("def broken(:")
        p=record(repo);result=r.static_checks(repo,p);self.assertFalse(result["passed"]);self.assertIn("bad.py",result["failures"][0])

class TransactionTests(unittest.TestCase):
    setUp=test_drafts.DraftTests.setUp
    def initialise(self):
        repo=fixture();self.repo=repo
        registry=studio.read(self.home/".studio/registry.json")
        snap={"commit":B,"files_hash":"f"*64,"status":""}
        source=registry["tasks"][0];source.update(name="Accepted task",status="Approved",current_commit=B,integration_readiness=True,base_commit=A,last_verified_test={"passed":True,"snapshot":snap},verification={"passed":True,"snapshot":snap})
        registry["approved_base"]={"commit":A};studio.atomic(self.home/".studio/registry.json",registry)
        self.git.stop();self.git=patch.object(studio,"git",side_effect=lambda root,*args: "" if args[0]=="status" else B);self.git.start()
        patches=[patch.object(studio,"snapshot",return_value=snap),patch.object(r,"GitObjects",return_value=repo),
                 patch.object(r,"authority",side_effect=lambda h,t,o:(studio.read(self.home/".studio/registry.json"),{"id":"release","base_commit":A},self.root))]
        for p in patches:p.start();self.addCleanup(p.stop)
        return r.action(self.home,"release","owner-a",{"operation":"prepare","task_ids":["task-a"]})
    def call(self,p,operation,**extra):return r.action(self.home,"release","owner-a",{"operation":operation,"id":p["id"],"version":p["version"],**extra})
    def ready(self):
        p=self.initialise();p=self.call(p,"test")
        p=r.runtime_result(self.home,"release","owner-a",p["id"],p["fingerprint"],{"isolated_preview":True,"combined_runtime":True})
        p=self.call(p,"review",confirmation="REVIEW "+B)
        return self.call(p,"approve",confirmation="APPROVE "+B)
    def test_persisted_immutable_lifecycle_and_duplicate_preparation(self):
        p=self.ready();p=self.call(p,"simulate",confirmation="SIMULATE "+B)
        self.assertEqual(p["status"],"Simulation verified")
        self.assertEqual(r.load(self.home)["last_verified_simulation"]["github"]["revision"],B)
        with self.assertRaises(ValueError):r.action(self.home,"release","owner-a",{"operation":"prepare","task_ids":["task-a"]})
    def test_retesting_cannot_enable_duplicate_publication(self):
        p=self.ready();p=self.call(p,"simulate",confirmation="SIMULATE "+B)
        p=self.call(p,"test");p=self.call(p,"review",confirmation="REVIEW "+B)
        with self.assertRaisesRegex(ValueError,"duplicate"):self.call(p,"approve",confirmation="APPROVE "+B)
    def test_stale_request_and_duplicate_simulation_rejected(self):
        p=self.ready();self.call(p,"simulate",confirmation="SIMULATE "+B)
        with self.assertRaisesRegex(ValueError,"Stale"):self.call(p,"simulate",confirmation="SIMULATE "+B)
    def test_unfinished_task_cannot_enter_candidate(self):
        self.initialise();reg=studio.read(self.home/".studio/registry.json");reg["tasks"][0]["status"]="In Progress";studio.atomic(self.home/".studio/registry.json",reg)
        with self.assertRaisesRegex(ValueError,"unfinished"):r.action(self.home,"release","owner-a",{"operation":"prepare","task_ids":["task-a"]})
    def test_approval_revalidates_task_evidence(self):
        p=self.ready();reg=studio.read(self.home/".studio/registry.json");reg["tasks"][0]["last_verified_test"]["passed"]=False;studio.atomic(self.home/".studio/registry.json",reg)
        with self.assertRaises(ValueError):self.call(p,"simulate",confirmation="SIMULATE "+B)
    def test_working_changes_block_eligibility(self):
        self.initialise();reg=studio.read(self.home/".studio/registry.json")
        with patch.object(studio,"git",return_value=" M unfinished.py"):
            with self.assertRaisesRegex(ValueError,"uncommitted"):r.eligible(reg,reg["tasks"][0],self.repo)
    def test_failed_runtime_prevents_review(self):
        p=self.initialise();p=self.call(p,"test");p=r.runtime_result(self.home,"release","owner-a",p["id"],p["fingerprint"],{"isolated_preview":True,"combined_runtime":False})
        with self.assertRaises(ValueError):self.call(p,"review",confirmation="REVIEW "+B)
    def test_production_publish_is_always_disabled(self):
        p=self.ready()
        with self.assertRaisesRegex(ValueError,"disabled"):self.call(p,"publish",confirmation="PUBLISH "+B)
    def test_candidate_reopen_preserves_identity(self):
        p=self.initialise();q,_=r.read_candidate(self.home,"release","owner-a",p["id"])
        self.assertEqual(q["fingerprint"],p["fingerprint"]);self.assertEqual(q["candidate_commit"],B)
    def test_base_change_blocks_approval(self):
        p=self.ready();reg=studio.read(self.home/".studio/registry.json");reg["approved_base"]["commit"]=C;studio.atomic(self.home/".studio/registry.json",reg)
        with self.assertRaisesRegex(ValueError,"base changed"):self.call(p,"simulate",confirmation="SIMULATE "+B)

class ReleaseHTTPTests(test_draft_ui.UITests):
    def test_non_release_owner_denied_and_publish_disabled(self):
        s=self.server()
        for data in [{"action":"release-catalog"},{"action":"release-operation","operation":"publish"}]:
            self.assertEqual(self.request(s,"/api/action",data)[0],409)
    def test_release_state_rejects_bad_auth_and_origin(self):
        s=self.server()
        for headers in [{"X-Studio-Token":""},{"Origin":"https://evil.example"}]:
            self.assertIn(self.request(s,"/api/action",{"action":"release-catalog"},headers=headers)[0],[401,403])

if __name__=="__main__":unittest.main()
