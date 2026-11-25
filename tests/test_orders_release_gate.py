"""Release diagnostics retain failures without skipping other offline checks."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest


@pytest.mark.parametrize('failure', ['timeout', 'exit', 'skip'])
def test_gate_preserves_failure_evidence_and_runs_every_suite(tmp_path, monkeypatch, failure):
    path = Path(__file__).resolve().parents[1] / 'scripts/check_orders_release.py'
    spec = importlib.util.spec_from_file_location('fixture_release_gate', path)
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    engine = tmp_path / 'synthetic-pglite.js'
    engine.write_text('synthetic runtime; never executed')
    out = tmp_path / 'evidence'
    monkeypatch.setattr(sys, 'argv', ['gate', '--pglite', str(engine), '--evidence', str(out)])
    monkeypatch.setattr(gate.subprocess, 'check_output', lambda *a, **kw: 'f' * 40)
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        if len(commands) == 1:
            if failure == 'timeout':
                raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=b'last fixture started', stderr=b'fixture stack')
            return subprocess.CompletedProcess(command, 1 if failure == 'exit' else 0,
                                               stdout='fixture failure' if failure == 'exit' else '1 skipped', stderr='')
        return subprocess.CompletedProcess(command, 0, stdout='fixture checks passed', stderr='')
    monkeypatch.setattr(gate.subprocess, 'run', run)
    assert gate.main() == 1
    report = json.loads((out / 'release-gate.json').read_text())
    assert set(report['suites']) == {'email', 'python', 'node', 'topology'}
    assert len(commands) == 4 and report['passed'] is False
    log = (out / 'email.log').read_text()
    if failure == 'timeout':
        assert 'last fixture started' in log and 'fixture stack' in log and 'time limit' in log
        assert report['suites']['email']['exit_code'] == 124
    elif failure == 'exit':
        assert 'fixture failure' in log and report['suites']['email']['exit_code'] == 1
    else:
        assert report['suites']['email']['skipped'] is True
