"""Offline contracts and real Chromium acceptance; never imports the application server."""
import asyncio
import ast
import copy
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch, AsyncMock
from types import SimpleNamespace
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from task_recorder.schema import Invalid, validate_task, resolve_task
from task_recorder.server import Bridge
from task_recorder.store import Store

def template():
    return {"version":1,"name":"Test","inputs":[],"steps":[{"action":"navigate","value":"http://127.0.0.1:18931/demo"}]}

class FormatTests(unittest.TestCase):
    def test_reject_code_unknown_fields_credentials_and_private_urls(self):
        for step in [
            {"action":"evaluate","value":"alert(1)"},
            {"action":"shell","value":"cmd.exe"},
            {"action":"click","locator":{"by":"css","value":"body"}},
            {"action":"fill","locator":{"by":"label","value":"Password"},"value":"private"},
            {"action":"navigate","value":"https://example.com/?token=private"},
            {"action":"navigate","value":"file:///C:/Windows"},
            {"action":"navigate","value":"https://user:password@example.com"},
            {"action":"navigate","value":"https://example.com/","script":"x"},
        ]:
            task=template(); task["steps"]=[step]
            with self.subTest(step=step["action"]), self.assertRaises(Invalid): validate_task(task)

    def test_required_inputs_and_upload_validation(self):
        task=template()
        task["inputs"]=[{"name":"product_name","required":True}]
        task["steps"].append({"action":"fill","locator":{"by":"label","value":"Product name"},"value":{"input":"product_name"}})
        with self.assertRaises(Invalid): resolve_task(task,{})
        self.assertEqual(resolve_task(task,{"product_name":"Product B"})["steps"][1]["value"],"Product B")
        task["steps"][-1]["action"]="upload"
        with self.assertRaises(Invalid): resolve_task(task,{"product_name":"relative.txt"})
        task["steps"]=[{"action":"unsupported","reason":"Review"}]
        with self.assertRaises(Invalid): resolve_task(task,{"product_name":"B"})

    def test_interruption_never_resumes_automatically(self):
        with tempfile.TemporaryDirectory() as d:
            store=Store(d);task=store.save(template());store.result(task["id"],"executing",3,"Step started.")
            restarted=Store(d)
            self.assertEqual(restarted.list()[0]["result"],"interrupted")
            self.assertEqual(json.loads(restarted.journal.read_text())["status"],"interrupted")
            self.assertEqual(restarted.get(task["id"]),task)

class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.server=Bridge(self.tmp.name,0,headless=True)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def tearDown(self):
        self.server.shutdown();self.server.close();self.thread.join();self.tmp.cleanup()

    def request(self,path,headers=None,data=None):
        return urlopen(Request(self.server.origin+path,headers=headers or {},data=data),timeout=10)

    def test_auth_host_origin_and_csrf(self):
        for headers,code in [({},401),({"X-Recorder-Key":"bad"},401),
                            ({"X-Recorder-Key":self.server.token,"Origin":"https://evil.example"},403),
                            ({"X-Recorder-Key":self.server.token,"Host":"evil.example"},403),
                            ({"X-Recorder-Key":self.server.token,"Origin":"null"},403),
                            ({"X-Recorder-Key":self.server.token,"Sec-Fetch-Site":"cross-site"},403)]:
            with self.subTest(code=code),self.assertRaises(HTTPError) as ctx:self.request("/api/state",headers)
            self.assertEqual(ctx.exception.code,code)
            ctx.exception.close()
        with self.request("/api/state",{"X-Recorder-Key":self.server.token}) as r:
            self.assertEqual(json.load(r)["mode"],"idle")
        with self.assertRaises(HTTPError) as ctx:
            self.request("/api/play",{"X-Recorder-Key":self.server.token,"Content-Type":"text/plain"},b"{}")
        self.assertEqual(ctx.exception.code,415)
        ctx.exception.close()

    def test_unknown_commands_and_scripts_rejected(self):
        headers={"X-Recorder-Key":self.server.token,"Content-Type":"application/json"}
        with self.assertRaises(HTTPError) as ctx:self.request("/api/evaluate",headers,b'{"script":"anything"}')
        self.assertEqual(ctx.exception.code,400)
        ctx.exception.close()

class NavigationTests(unittest.TestCase):
    def test_real_route_dispatch_and_local_only_admin_panel(self):
        import task_recorder_page
        import navigation_runtime
        source=Path(__file__).parents[1]/"app.py"
        tree=ast.parse(source.read_text(encoding="utf-8"))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="render_selected_page")
        accounts=SimpleNamespace(is_admin=lambda u:u.get("role")=="admin",WEEKLY_REVIEW_ROUTE="Weekly Review")
        st=Mock()
        st.session_state={}
        st.button.return_value=False
        st.dialog.side_effect=lambda *a,**kw:lambda fn:fn
        component=SimpleNamespace(iframe=Mock())
        namespace={"st":st,"os_accounts":accounts,"analytics_nav":SimpleNamespace(ANALYTICS_ROUTES=()),
                   "current_os_user":lambda:{"role":"admin"}}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),"exec"),namespace)
        with patch.dict(sys.modules,{"streamlit":st,"streamlit.components.v1":component,"os_accounts":accounts}):
            with patch.dict("os.environ",{},clear=True):
                namespace["render_selected_page"]("Task Recorder")
                component.iframe.assert_called_once_with("/task-recorder/panel",height=640,scrolling=False)
            component.iframe.reset_mock()
            st.session_state.clear()
            with patch.dict("os.environ",{"RENDER":"true"},clear=True):
                task_recorder_page.render_page({"role":"admin"})
                component.iframe.assert_called_once_with("/task-recorder/panel",height=640,scrolling=False)
            task_recorder_page.render_page({"role":"worker"})
            st.error.assert_called()
        self.assertEqual(navigation_runtime.active_disclosure_group("Task Recorder"),"developer")

    def test_real_access_check_blocks_staff(self):
        source=Path(__file__).parents[1]/"os_accounts.py"
        tree=ast.parse(source.read_text(encoding="utf-8"))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="can_access_page")
        entry=next(ast.literal_eval(item) for n in tree.body if isinstance(n,ast.Assign)
                   and any(isinstance(t,ast.Name) and t.id=="PAGE_REGISTRY" for t in n.targets)
                   for item in n.value.elts if isinstance(item,ast.Dict) and any(isinstance(v,ast.Constant) and v.value=="task_recorder" for v in item.values))
        namespace={"account_is_active":lambda u:True,"PAGE_BY_KEY":{"task_recorder":entry},
                   "PAGE_BY_ROUTE":{"Task Recorder":entry},"normalise_page_key":lambda x:x,
                   "normalise_route":lambda x:x,"is_admin":lambda u:u["role"]=="admin"}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),"exec"),namespace)
        self.assertTrue(namespace["can_access_page"]({"role":"admin"},"Task Recorder"))
        self.assertFalse(namespace["can_access_page"]({"role":"worker"},"Task Recorder"))
        self.assertFalse(entry["worker_assignable"])

class BrowserFocusTests(unittest.IsolatedAsyncioTestCase):
    async def test_browser_close_preserves_and_flags_unfinished_recording(self):
        from task_recorder.runner import Runner
        with tempfile.TemporaryDirectory() as directory:
            runner=Runner(directory)
            runner.draft={**runner.blank(),"steps":[{"action":"navigate","value":"https://example.com"}]}
            runner.recording=True;runner.simple_recording=True
            runner.closed()
            saved=runner.store.get(runner.draft["id"])
            self.assertEqual(runner.mode,"interrupted")
            self.assertFalse(runner.recording)
            self.assertTrue(any(s["action"]=="unsupported" for s in saved["steps"]))
            with self.assertRaises(Invalid):resolve_task(saved,{})

    async def test_exchange_allows_server_wait_and_database_round_trips(self):
        import httpx
        from task_recorder.runner import Runner
        from task_recorder.device import DeviceAgent
        with tempfile.TemporaryDirectory() as directory:
            runner=Runner(directory)
            agent=DeviceAgent(runner,"http://127.0.0.1:18931",preview=True)
            response=httpx.Response(200,json={"commands":[],"fence":0},request=httpx.Request("POST","https://example.invalid"))
            agent.client=SimpleNamespace(post=AsyncMock(return_value=response))
            device={"device_id":"synthetic-device","origin":"https://example.invalid","key":"synthetic"}
            try:
                await agent.exchange(device,{},wait=True)
                self.assertGreater(agent.client.post.call_args.kwargs["timeout"].read,30)
                await agent.exchange(device,{})
                self.assertGreaterEqual(agent.client.post.call_args.kwargs["timeout"].read,15)
            finally:await agent.close()

    async def test_record_and_play_bring_existing_browser_forward(self):
        from task_recorder.runner import Runner
        from task_recorder.device import DeviceAgent
        with tempfile.TemporaryDirectory() as directory:
            runner=Runner(directory)
            runner.context=SimpleNamespace(close=AsyncMock())
            runner.page=SimpleNamespace(bring_to_front=AsyncMock(),is_closed=lambda:False)
            runner.set_recording=AsyncMock()
            agent=DeviceAgent(runner,"http://127.0.0.1:18931",preview=True)
            try:
                await agent.perform("record",{},"synthetic-focus-check")
                runner.page.bring_to_front.assert_awaited_once()
                runner.page.bring_to_front.reset_mock()
                task=runner.store.save({**runner.blank(),"steps":[{"action":"navigate","value":"https://example.com"}]})
                runner.run=AsyncMock()
                await runner.play(task["id"],{})
                await runner.job
                runner.page.bring_to_front.assert_awaited_once()
            finally:
                await agent.close()
                await runner.close()

if __name__=="__main__":
    unittest.main()
