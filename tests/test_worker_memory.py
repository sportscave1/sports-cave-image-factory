"""Local resource-budget, sampling and process cleanup regressions."""
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import psutil
import worker_memory as memory
from crm_thumbnail_process import run_renderer


class MemoryTests(unittest.TestCase):
    def test_small_container_caps_browser_concurrency_only(self):
        for limit, expected in ((512*memory.MIB, 1), (768*memory.MIB, 1), (1024*memory.MIB, 2), (None, 2)):
            with patch.object(memory, 'cgroup_memory', return_value={'limit':limit}):
                self.assertEqual(memory.thumbnail_workers(2), expected)
                self.assertEqual(memory.thumbnail_workers(1), 1)

    def test_cgroup_v2_and_v1_and_unavailable(self):
        for readings, result in (([10,20,30], {'current':10,'limit':20,'peak':30}),
                ([None,None,None,11,22,33], {'current':11,'limit':22,'peak':33}),
                ([None]*6, {'current':None,'limit':None,'peak':None})):
            with patch.object(memory, '_number', side_effect=readings):
                self.assertEqual(memory.cgroup_memory(), result)

    def test_unlimited_and_missing_files_are_unknown(self):
        for value in ('max', str(2**63), '-1', 'invalid'):
            with patch.object(Path, 'read_text', return_value=value):
                self.assertIsNone(memory._number('unused'))
        with patch.object(Path, 'read_text', side_effect=FileNotFoundError):
            self.assertIsNone(memory._number('unused'))

    def test_includes_descendants_and_rate_limits_normal_logs(self):
        parent, child, browser = Mock(), Mock(), Mock()
        parent.memory_info.return_value.rss = 10*memory.MIB
        child.memory_info.return_value.rss = 20*memory.MIB
        browser.memory_info.return_value.rss = 30*memory.MIB
        child.children.return_value = [browser]
        monitor = memory.MemoryMonitor()
        with patch('psutil.Process', side_effect=lambda pid: parent if pid==os.getpid() else child), patch.object(memory, 'cgroup_memory', return_value={'current':60*memory.MIB,'limit':512*memory.MIB,'peak':90*memory.MIB}), patch.object(memory.time, 'monotonic', side_effect=[0,1,5,60]), self.assertLogs('worker_memory', logging.INFO) as logs:
            for _ in range(4):monitor.sample({'crm':Mock(pid=-1)})
        self.assertEqual(len(logs.output),2)
        self.assertIn('crm_tree_bytes='+str(50*memory.MIB), logs.output[0])
        self.assertIn('processes=3',logs.output[0])
        self.assertEqual(monitor.peak,60*memory.MIB)

    def test_monitor_failure_is_nonfatal_and_redacted(self):
        with patch('psutil.Process', side_effect=RuntimeError('private-value')), self.assertLogs('worker_memory', logging.WARNING) as logs:
            memory.MemoryMonitor().sample({})
        self.assertNotIn('private-value',str(logs.output))

    def test_pressure_logs_even_before_regular_interval(self):
        process=Mock();process.memory_info.return_value.rss=1
        with patch('psutil.Process',return_value=process), patch.object(memory,'cgroup_memory',return_value={'current':450*memory.MIB,'limit':512*memory.MIB,'peak':500*memory.MIB}), self.assertLogs('worker_memory',logging.WARNING) as logs:
            memory.MemoryMonitor().sample({})
        self.assertIn('cgroup_peak_bytes=',logs.output[0])


class RendererProcessTests(unittest.TestCase):
    def test_output_is_bounded_and_return_code_preserved(self):
        result=run_renderer([sys.executable,'-c',"import sys;sys.stderr.write('x'*100000);sys.exit(7)"])
        self.assertEqual(result.returncode,7)
        self.assertEqual(result.stdout,b'')
        self.assertEqual(result.stderr,b'x'*1024)

    def test_timeout_reaps_renderer_and_grandchild(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'pids.json'
            code="import subprocess,sys,os,json,time;from pathlib import Path;p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);Path(sys.argv[1]).write_text(json.dumps([os.getpid(),p.pid]));time.sleep(60)"
            with self.assertRaises(subprocess.TimeoutExpired):
                run_renderer([sys.executable,'-c',code,str(marker)],timeout=2)
            import json
            identities=json.loads(marker.read_text())
            for pid in identities:
                try:process=psutil.Process(pid)
                except psutil.NoSuchProcess:continue
                self.assertEqual(process.status(), psutil.STATUS_ZOMBIE)


if __name__=='__main__':unittest.main()
