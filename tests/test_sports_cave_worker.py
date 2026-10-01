"""Offline supervisor and existing CRM gate checks; never start real workers."""
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import sports_cave_worker as worker


class SupervisorTests(unittest.TestCase):
    def child(self):
        return Mock(pid=123, poll=Mock(return_value=None))

    def test_both_start_with_original_arguments_and_inherited_environment(self):
        seo, crm = self.child(), self.child()
        supervisor = worker.Supervisor()
        with patch.object(worker.subprocess, 'Popen', side_effect=[seo, crm]) as launch:
            supervisor.check_children()
        self.assertEqual(supervisor.children, {'seo': seo, 'crm': crm})
        self.assertEqual(launch.call_args_list[0].args[0],
                         [sys.executable, '-u', 'google_seo_import.py', 'worker', '--poll-seconds', '15'])
        self.assertEqual(launch.call_args_list[1].args[0], [sys.executable, '-u', 'crm_worker.py'])
        for call in launch.call_args_list:
            self.assertEqual(call.kwargs, {'cwd': worker.ROOT})

    def test_each_child_restarts_without_stopping_its_sibling(self):
        for failed in ('seo', 'crm'):
            with self.subTest(failed=failed):
                supervisor = worker.Supervisor()
                original = {name: self.child() for name in worker.WORKERS}
                supervisor.children.update(original)
                original[failed].poll.return_value = 1
                replacement = self.child()
                with patch.object(worker.time, 'monotonic', return_value=100), self.assertLogs(level='WARNING'):
                    supervisor.check_children()
                sibling = original['crm' if failed == 'seo' else 'seo']
                sibling.terminate.assert_not_called()
                with patch.object(worker.time, 'monotonic', return_value=104), patch.object(worker.subprocess, 'Popen') as launch:
                    supervisor.check_children()
                    launch.assert_not_called()
                with patch.object(worker.time, 'monotonic', return_value=105), patch.object(worker.subprocess, 'Popen', return_value=replacement) as launch:
                    supervisor.check_children()
                    launch.assert_called_once()
                self.assertIs(supervisor.children[failed], replacement)

    def test_start_failure_is_redacted_and_other_child_starts(self):
        supervisor = worker.Supervisor()
        with patch.object(worker.subprocess, 'Popen', side_effect=[OSError('secret-value'), self.child()]), self.assertLogs(level='ERROR') as logs:
            supervisor.check_children()
        self.assertIn('crm', supervisor.children)
        self.assertNotIn('secret-value', '\n'.join(logs.output))

    def test_shutdown_signals_both_before_wait_and_reaps_them(self):
        supervisor = worker.Supervisor()
        seo, crm = self.child(), self.child()
        supervisor.children = {'seo': seo, 'crm': crm}
        seo.wait.side_effect = lambda **_: crm.terminate.assert_called_once()
        supervisor.shutdown()
        seo.terminate.assert_called_once()
        crm.wait.assert_called_once()
        seo.kill.assert_not_called()
        self.assertEqual(supervisor.children, {})

    def test_shutdown_timeout_kills_and_reaps_unresponsive_child(self):
        supervisor = worker.Supervisor()
        child = self.child()
        child.wait.side_effect = [subprocess.TimeoutExpired('fixture', 20), 0]
        supervisor.children = {'seo': child}
        with self.assertLogs(level='WARNING'):
            supervisor.shutdown()
        child.kill.assert_called_once()
        self.assertEqual(child.wait.call_count, 2)

    def test_both_signals_request_stop_and_handlers_are_restored(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            supervisor = worker.Supervisor()
            previous = {value: signal.getsignal(value) for value in (signal.SIGTERM, signal.SIGINT)}
            def run():
                signal.getsignal(sig)(sig, None)
                self.assertTrue(supervisor.stop.is_set())
                with patch.object(worker.subprocess, 'Popen') as launch:
                    supervisor.check_children()
                    launch.assert_not_called()
                return 0
            with patch.object(worker, 'Supervisor', return_value=supervisor), patch.object(supervisor, 'run', side_effect=run):
                self.assertEqual(worker.main(), 0)
            for value, handler in previous.items():
                self.assertEqual(signal.getsignal(value), handler)

    def test_loop_cleans_up_on_unexpected_exception(self):
        supervisor = worker.Supervisor()
        with patch.object(supervisor, 'check_children', side_effect=RuntimeError), patch.object(supervisor, 'shutdown') as shutdown:
            with self.assertRaises(RuntimeError):
                supervisor.run()
        shutdown.assert_called_once()

    def test_real_synthetic_children_inherit_env_and_are_reaped(self):
        # Replace both commands: no business worker or production client runs.
        script = "import os,time; from pathlib import Path; Path(os.environ['WORKER_FIXTURE_DIR'], '{name}').write_text(os.environ['WORKER_FIXTURE_VALUE']); time.sleep(60)"
        supervisor = worker.Supervisor()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            'WORKER_FIXTURE_DIR': directory, 'WORKER_FIXTURE_VALUE': 'synthetic'
        }), patch.object(worker, 'WORKERS', {
            name: ('-c', script.replace('{name}', name)) for name in ('seo', 'crm')
        }):
            children = []
            try:
                supervisor.check_children()
                children = list(supervisor.children.values())
                deadline = time.monotonic() + 5
                while not all(Path(directory, name).exists() for name in ('seo', 'crm')):
                    self.assertLess(time.monotonic(), deadline, 'Synthetic child startup timed out')
                    time.sleep(0.02)
                for name in ('seo', 'crm'):
                    self.assertEqual(Path(directory, name).read_text(), 'synthetic')
            finally:
                supervisor.shutdown()
            self.assertEqual(len(children), 2)
            self.assertTrue(all(child.poll() is not None for child in children))


class CRMGateTests(unittest.TestCase):
    def test_marketing_off_still_reconciles_without_send_or_campaign_execution(self):
        from crm_engine import Engine
        from crm_resend import Config
        store, shop, provider = Mock(), Mock(), Mock()
        store.lease.return_value = True
        store.q.return_value = []
        with patch.dict(os.environ, {'CRM_MARKETING_ENABLED': 'false',
                                    'CRM_MARKETING_SEND_ENABLED': 'true',
                                    'CRM_MARKETING_TEST_ENABLED': 'true'}, clear=True):
            engine = Engine(store, shop, provider=provider, config=Config())
            with patch('crm_campaign_schedule.schedule_gate') as gate, patch('crm_campaign_attribution.reconcile') as reconcile, patch('crm_consent_sync.reconcile_pending'), patch.object(engine, 'campaign_page') as campaigns, patch.object(engine, 'advance') as advance:
                self.assertEqual(engine.tick('fixture-owner'), {'leader': True})
        self.assertFalse(engine.config.enabled)
        self.assertFalse(engine.config.tests_enabled)
        reconcile.assert_called_once_with(store, shop, engine.clock)
        gate.assert_called_once()
        self.assertEqual(gate.call_args.args[:2], (store, False))
        campaigns.assert_not_called()
        advance.assert_not_called()
        store.claim_send.assert_not_called()
        provider.send.assert_not_called()
        store.release.assert_called_once_with('fixture-owner')

    def test_crm_entrypoint_runs_when_marketing_off(self):
        import crm_worker
        with patch.dict(os.environ, {'CRM_MARKETING_ENABLED': 'false'}, clear=True), patch('crm_store.Store'), patch('crm_shopify.Shopify'), patch('crm_engine.Engine') as engine, patch.object(crm_worker.signal, 'signal'):
            self.assertEqual(crm_worker.main(['--once']), 0)
        engine.return_value.tick.assert_called_once()


if __name__ == '__main__':
    unittest.main()
