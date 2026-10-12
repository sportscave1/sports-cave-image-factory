"""Focused integration gates; synthetic fixtures and pure owner predicates only."""
import ast
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import drafts
import studio
import test_draft_ui

ROOT=Path(__file__).resolve().parents[2]

class CatalogTests(test_draft_ui.UITests):
    def test_catalog_real_drafts_no_paths_or_tokens(self):
        s=self.server()
        draft=drafts.new(self.home,"task-a","owner-a","Actual draft")
        status,body,_=self.request(s,"/api/action",{"action":"catalog"})
        data=json.loads(body)
        self.assertEqual(status,200)
        self.assertEqual(len(data["categories"]),9)
        self.assertEqual([r["id"] for r in data["rows"]],[draft["id"]])
        self.assertNotIn(str(self.root),body.decode())
        self.assertNotIn(s.token,body.decode())
        self.assertIsNone(data["rows"][0]["test"]["passed"])
        self.assertTrue(data["rows"][0]["actionable"])

    def test_handoff_exact_selection_and_owner(self):
        s=self.server()
        draft=drafts.new(self.home,"task-a","owner-a","Selected")
        command={"action":"handoff","draft_id":draft["id"],"intent":"edit"}
        status,body,_=self.request(s,"/api/action",command)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["task_id"],"task-a")
        self.assertTrue(json.loads(body)["url"].startswith(s.origin+"/workspace#token="))
        for change in [{"intent":"publish"},{"draft_id":"../other"}]:
            self.assertEqual(self.request(s,"/api/action",{**command,**change})[0],409)
        registry=studio.read(self.home/".studio/registry.json")
        registry["drafts"][0]["owner"]="other-owner"
        studio.atomic(self.home/".studio/registry.json",registry)
        self.assertEqual(self.request(s,"/api/action",command)[0],409)
        self.assertFalse(json.loads(self.request(s,"/api/action",{"action":"catalog"})[1])["rows"][0]["actionable"])

    def test_other_draft_reuses_distinct_owned_companion(self):
        s=self.server()
        other=self.home/"task-b";other.mkdir();(other/"screen.html").write_text("Original B")
        registry=studio.read(self.home/".studio/registry.json")
        registry["tasks"].append({**self.task,"id":"task-b","category":"ADS","branch":"codex/task/b","worktree_path":str(other)})
        studio.atomic(self.home/".studio/registry.json",registry)
        draft=drafts.new(self.home,"task-b","owner-a","Other real draft")
        data={"action":"handoff","draft_id":draft["id"],"intent":"open"}
        a=json.loads(self.request(s,"/api/action",data)[1])
        b=json.loads(self.request(s,"/api/action",data)[1])
        self.assertEqual(a,b)
        self.assertEqual(a["task_id"],"task-b")
        self.assertFalse(a["url"].startswith(s.origin+"/"))
        child=s.children["task-b"][0]
        state=json.loads(self.request(child)[1])
        self.assertEqual(state["task"]["category"],"ADS")
        self.assertEqual(state["task"]["worktree_path"],str(other))
        self.assertEqual((other/"screen.html").read_text(),"Original B")

    def test_pairing_assets_no_cors_or_embedding(self):
        s=self.server()
        for path in ["/pair","/pair.js","/pair.css"]:
            status,_,headers=self.request(s,path,headers={"X-Studio-Token":""})
            self.assertEqual(status,200)
            self.assertNotIn("Access-Control-Allow-Origin",headers)
            self.assertIn("frame-ancestors 'none'",headers["Content-Security-Policy"])
        for action in ["catalog","handoff"]:
            self.assertEqual(self.request(s,"/api/action",{"action":action},headers={"X-Studio-Token":""})[0],401)
            self.assertEqual(self.request(s,"/api/action",{"action":action},headers={"Origin":"https://unapproved.example"})[0],403)

class OwnerTests(unittest.TestCase):
    def test_actual_owner_predicate_and_route_fail_closed(self):
        tree=ast.parse((ROOT/"os_accounts.py").read_text(encoding="utf-8-sig"))
        wanted={"normalise_login","account_status","account_is_removed","account_is_active","is_admin","reporting_owner_email","is_reporting_owner","can_access_page"}
        module=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in wanted],type_ignores=[])
        import os
        ns={"os":os,"ROLE_ADMIN":"admin","ACCOUNT_STATUS_ACTIVE":"active","ACCOUNT_STATUS_REMOVED":"removed","VALID_ACCOUNT_STATUSES":{"active","removed"},"REPORTING_OWNER_ENV_KEYS":("SPORTS_CAVE_REPORTING_OWNER_EMAIL","SPORTS_CAVE_ADMIN_EMAIL"),
            "PAGE_BY_KEY":{"developer_studio":{"key":"developer_studio"}},"PAGE_BY_ROUTE":{"Developer Studio":{"key":"developer_studio"}},
            "normalise_page_key":lambda s:s,"normalise_route":lambda s:s}
        exec(compile(module,"owner-predicates","exec"),ns)
        owner={"email":"owner@example.invalid","role":"admin","is_active":True}
        with patch.dict(os.environ,{"SPORTS_CAVE_ADMIN_EMAIL":"owner@example.invalid"},clear=True):
            self.assertTrue(ns["can_access_page"](owner,"Developer Studio"))
            for user in [None,{**owner,"role":"worker"},{**owner,"email":"other@example.invalid"},{**owner,"is_active":False}]:
                self.assertFalse(ns["can_access_page"](user,"Developer Studio"))
        with patch.dict(os.environ,{},clear=True):
            self.assertFalse(ns["can_access_page"](owner,"Developer Studio"))

    def test_direct_page_render_denies_before_loading_assets(self):
        sys.path.insert(0,str(ROOT))
        import developer_studio_page
        from types import SimpleNamespace
        errors=[]
        with patch.dict(sys.modules,{"os_accounts":SimpleNamespace(is_reporting_owner=lambda user:False),
                                     "streamlit":SimpleNamespace(error=errors.append)}):
            with patch.object(developer_studio_page,"panel_html",side_effect=AssertionError("must stay lazy")):
                developer_studio_page.render_page({"role":"admin","email":"other@example.invalid"})
        self.assertEqual(len(errors),1)

    def test_lazy_page_has_no_development_backend_import(self):
        tree=ast.parse((ROOT/"app.py").read_text(encoding="utf-8-sig"))
        top_imports=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertNotIn("developer_studio_page",ast.dump(ast.Module(body=top_imports,type_ignores=[])))
        sys.path.insert(0,str(ROOT))
        import developer_studio_page
        page=developer_studio_page.panel_html()
        self.assertIn("Production unchanged",page)
        self.assertNotIn("/*STUDIO_",page)
        self.assertNotIn("setInterval",page)
        self.assertLess(len(page.encode()),90000)
        self.assertEqual(set(n.name for n in ast.walk(ast.parse((ROOT/"developer_studio_page.py").read_text())) if isinstance(n,ast.Import) for n in n.names),{"os_accounts","streamlit","json"})

if __name__=="__main__":unittest.main()
