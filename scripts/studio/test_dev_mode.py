"""V9 references and bounded viewport tests; the V8 write allowlist stays unchanged."""
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch,Mock
import dev_sources,editor,preview_runtime
class DevModeTests(unittest.TestCase):
    def test_only_actual_route_functions_and_imports_are_referenced(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'app.py').write_text('def orders():\n    print("orders_page.css")\n\nif current_page == "Orders":\n    from orders_page import render\n    orders()\nelif current_page == "Other":\n    from unrelated import render\n')
            (root/'orders_page.py').write_text('print("orders_page.css")')
            with patch.object(dev_sources.page_catalog,'pages',return_value=[{'key':'orders','route':'Orders'}]):
                result=dev_sources.route_sources(root,'orders')
                self.assertTrue(any(r['path']=='orders_page.py' for r in result['references']))
                self.assertFalse(any('unrelated' in r['source'] for r in result['references']))
                self.assertEqual(next(f['group'] for f in result['files'] if f['path']=='orders_page.css'),'Current page source')
                self.assertEqual(result['components'],[])
                self.assertTrue(all(r['mode']=='read-only' for r in result['references']))
                with self.assertRaises(ValueError):dev_sources.route_sources(root,'../../secrets')
    def test_read_only_references_do_not_expand_write_allowlist(self):
        self.assertEqual(editor.CODE_FILES,('components/sports_cave_top_bar/index.html','mockups_page.css','orders_page.css','components/session_recovery.js'))
    def test_viewport_rejects_invalid_bounds_before_relay(self):
        runtime=preview_runtime.Preview(None,'task','owner');runtime.name='owned';runtime.container_id='a'*64;runtime.relay=Mock()
        with patch.object(runtime,'_scope'):
            for data in ({'width':True,'height':900},{'width':2000,'height':900},{'width':1280,'height':200}):
                with self.assertRaises(ValueError):runtime.event({'action':'viewport',**data})
        runtime.relay.request.assert_not_called()
    def test_unchanged_full_viewport_reuses_frame_but_checks_lease(self):
        runtime=preview_runtime.Preview(None,'task','owner');runtime.name='owned';runtime.container_id='a'*64;runtime.last_frame={'width':1200,'height':800,'image':'valid'}
        with patch.object(runtime,'_scope') as scope:
            self.assertEqual(runtime.event({'action':'viewport','width':1200,'height':800}),runtime.last_frame)
            scope.assert_called_once()
    def test_route_reference_command_remains_capability_scoped(self):
        import draft_ui
        self.assertIn('editor-reference',Path(draft_ui.__file__).read_text(encoding='utf-8'))
        from test_v6 import V6Tests
        fixture=V6Tests();fixture.setUp()
        try:
            server=fixture.server()
            with self.assertRaises(ValueError):server.workspace_request({'capability':'unknown','command':{'action':'editor-reference','page':'orders'}})
        finally:fixture.doCleanups()
    def test_idle_browser_preconnect_has_bounded_header_wait(self):
        import draft_ui
        from http.server import HTTPServer
        client=Mock()
        with patch.object(HTTPServer,'get_request',return_value=(client,('127.0.0.1',1234))):
            result=draft_ui.DraftServer.get_request(draft_ui.DraftServer.__new__(draft_ui.DraftServer))
        client.settimeout.assert_called_once_with(5)
        self.assertEqual(result[1][0],'127.0.0.1')
if __name__=='__main__':unittest.main()
