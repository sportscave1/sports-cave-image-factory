"""Focused tests for preview export and policy refusal; never starts application code."""
import copy
import hashlib
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import preview_export as export
import preview_runtime as runtime

class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
    def test_data_and_runtime_paths_excluded(self):
        for name in [".env",".git/config","data/customers.json","output/invoice.html",
                     "credentials.json","sports_cave_server.py","run_migrations.py",
                     "support_email_worker.py","components/../../leak.html"]:
            self.assertFalse(export.allowed(name),name)
        self.assertTrue(export.allowed("app.py"))
        self.assertTrue(export.allowed("components/sports_cave_top_bar/index.html"))
    def test_authentication_default_replaced_without_source_write(self):
        path=self.root/"sc_auth.py"
        original='DEFAULT_APP_PASSWORD = "FixtureOnlyOriginal"\n'
        path.write_text(original)
        data,changed=export.source_bytes(self.root,"sc_auth.py")
        self.assertTrue(changed)
        self.assertNotIn(b"FixtureOnlyOriginal",data)
        self.assertIn(export.SYNTHETIC_PASSWORD.encode(),data)
        self.assertEqual(path.read_text(),original)
    def test_changed_authentication_structure_refused(self):
        (self.root/"sc_auth.py").write_text('DEFAULT_APP_PASSWORD = calculate()\n')
        with self.assertRaises(ValueError):
            export.source_bytes(self.root,"sc_auth.py")
    def test_unknown_short_credential_refused(self):
        (self.root/"test.py").write_text('SERVICE_PASSWORD = "fixture-only-password"\n')
        with self.assertRaises(ValueError):
            export.source_bytes(self.root,"test.py")
    def test_export_path_escape_refused(self):
        with self.assertRaises(ValueError):
            export.source_bytes(self.root,"../outside.py")
    def test_policy_line_endings_do_not_change_reviewed_rules(self):
        original=runtime.PROFILE.read_bytes().replace(b"\r\n",b"\n")
        from unittest.mock import Mock
        for data in [original,original.replace(b"\n",b"\r\n")]:
            with patch.object(runtime,"PROFILE",Mock(read_bytes=lambda:data)):
                self.assertEqual(runtime.profile_digest(),runtime.PROFILE_SHA256)

    def test_unreviewed_policy_hash_refused(self):
        with patch.object(runtime,"PROFILE_SHA256","0"*64):
            with self.assertRaises(RuntimeError):
                runtime.options("sha256:fake","name","task")
    def test_runtime_flags_preserve_boundary(self):
        args=runtime.options("sha256:fake","name","task")
        self.assertEqual(args[args.index("--network")+1],"none")
        self.assertIn("--read-only",args)
        self.assertEqual(args[args.index("--cap-drop")+1],"ALL")
        self.assertFalse(any(x in args for x in ["--privileged","--volume","--mount","--publish"]))
    def test_policy_requires_bounded_resources(self):
        for key,value in [("Memory",0),("PidsLimit",-1)]:
            config={"HostConfig":{"Memory":1073741824,"PidsLimit":192}}
            config["HostConfig"][key]=value
            with self.assertRaises(RuntimeError):
                runtime.validate_runtime(config,"sha256:fake","task")
if __name__=="__main__":
    unittest.main()


class SyntheticCookieTests(unittest.TestCase):
    def handler(self):
        import ast
        path=Path(__file__).parent/"isolation/controller.py"
        tree=ast.parse(path.read_text(encoding="utf-8-sig"))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="synthetic_cookie_cleanup")
        ns={}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(path),"exec"),ns)
        return ns[function.name]

    def test_exact_local_post_only_no_authentication_cookie_fabrication(self):
        from unittest.mock import Mock
        route=Mock()
        route.request.url="http://127.0.0.1:8501/api/os/auth/clear-cookie"
        route.request.method="POST"
        self.handler()(route)
        route.fulfill.assert_called_once_with(status=204,headers={"Cache-Control":"no-store"},body="")
        route.abort.assert_not_called()

    def test_other_methods_hosts_and_paths_fail_closed(self):
        from unittest.mock import Mock
        for url,method in [("https://production.invalid/api/os/auth/clear-cookie","POST"),
                           ("http://127.0.0.1:8501/api/os/auth/clear-cookie","GET"),
                           ("http://127.0.0.1:8501/api/other","POST")]:
            route=Mock();route.request.url=url;route.request.method=method
            self.handler()(route)
            route.abort.assert_called_once();route.fulfill.assert_not_called()
