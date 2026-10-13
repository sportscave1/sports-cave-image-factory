"""Windows engine readiness and HTTP failure regression; no live companion."""
import json
import subprocess
import unittest
from unittest.mock import patch, Mock
import preview_boundary as boundary
import test_draft_ui

class ReadinessTests(unittest.TestCase):
    def test_cli_timeout_is_actionable_not_uncaught(self):
        with patch.object(boundary.subprocess,'run',side_effect=subprocess.TimeoutExpired(['docker','info'],8)):
            with self.assertRaisesRegex(RuntimeError,'Docker info timed out'):
                boundary.docker('info',timeout=8)

    def test_ready_engine_is_not_restarted(self):
        with patch.object(boundary,'docker',return_value=Mock(stdout='linux\n')) as call:
            boundary.ready_local_engine('desktop-linux')
            self.assertEqual(call.call_count,1)

    def test_sleeping_engine_is_started_once_and_verified(self):
        with patch.object(boundary.os,'name','nt'), patch.object(boundary,'docker',side_effect=[RuntimeError('unavailable'),Mock(),Mock(stdout='linux\n')]) as call:
            boundary.ready_local_engine('desktop-linux')
            self.assertEqual(call.call_args_list[1].args,('desktop','start','--timeout','45'))
            self.assertEqual(call.call_args_list[2].kwargs['context'],'desktop-linux')

    def test_wrong_engine_fails_without_switching(self):
        with patch.object(boundary,'docker',return_value=Mock(stdout='windows\n')) as call:
            with self.assertRaises(ValueError):boundary.ready_local_engine('desktop-linux')
            self.assertEqual(call.call_count,1)

class HTTPFailureTests(test_draft_ui.UITests):
    def test_timeout_has_json_and_server_survives(self):
        server=self.server()
        with patch.object(server,'action',side_effect=subprocess.TimeoutExpired(['private-argument'],30)):
            status,body,_=self.request(server,'/api/action',{'action':'start-preview'})
        self.assertEqual(status,500)
        self.assertIn('TimeoutExpired',json.loads(body)['error'])
        self.assertNotIn(b'private-argument',body)
        log=(self.home/'.studio/last-action-error.json').read_text()
        self.assertNotIn('private-argument',log)
        self.assertEqual(self.request(server)[0],200)

if __name__=='__main__':
    suite=unittest.TestSuite([unittest.defaultTestLoader.loadTestsFromTestCase(ReadinessTests),HTTPFailureTests('test_timeout_has_json_and_server_survives')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
