"""Offline checks of the exported release candidate, never the dirty checkout."""
import argparse
import importlib
import json
from pathlib import Path
import re
import socket
import sys
import unittest
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--manifest-json', required=True)
    args = parser.parse_args()
    root = Path(args.candidate).resolve()
    sys.path.insert(0, str(root))
    manifest = json.loads(args.manifest_json)
    tests = manifest['tests']
    imports = manifest['imports']
    if not all(isinstance(n, str) and re.fullmatch(r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*', n)
               for n in tests + imports):
        raise ValueError('Tests/imports must be dotted Python identifiers, not commands.')
    runtime = [f['path'] for f in manifest['files'] if
               not f['path'].startswith(('docs/', 'tests/', 'scripts/', 'deploy/'))]
    if (runtime or manifest['mode'] == 'full') and not tests:
        raise ValueError('Application/full releases require explicit affected regression tests in the manifest.')
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('Deployment smoke forbids network')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('Deployment smoke forbids network')), \
         patch('requests.sessions.Session.request', side_effect=AssertionError('Deployment smoke forbids HTTP')):
        from scripts.validate_render_topology import main as topology
        assert topology(['--path', str(root/'render.yaml')]) == 0
        from crm_lifecycle_definition import expanded_flow
        from crm_lifecycle_runtime import DRAFT_ONLY, locked
        assert DRAFT_ONLY is True, 'Lifecycle activation lock must remain enabled'
        total = 0
        for kind in ('welcome', 'post_purchase', 'win_back'):
            flow = expanded_flow(kind)
            assert locked({'config': {'draft': flow}}), kind
            total += len(flow['emails'])
            if kind == 'win_back': assert flow['emails'][3]['enabled'] is False
        assert total == 10
        for module in imports:
            importlib.import_module(module)
        names = ['tests.test_crm_lifecycle_expansion.PolicyTests',
                 'tests.test_automation_v6_cache.CacheTests'] + tests
        suite = unittest.defaultTestLoader.loadTestsFromNames(list(dict.fromkeys(names)))
        result = unittest.TextTestRunner(verbosity=1).run(suite)
        if not result.wasSuccessful() or result.skipped:
            raise RuntimeError(f'Smoke/regression failed or skipped: {len(result.skipped)} skips. '
                               'Database/browser gates require separately verified evidence, never silent skips.')


if __name__ == '__main__':
    main()
