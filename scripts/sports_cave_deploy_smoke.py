"""Offline checks of the exported release candidate, never the dirty checkout."""
import argparse
import importlib
import json
import os
from pathlib import Path
import re
import socket
import sys
import unittest
from unittest.mock import patch
from contextlib import nullcontext

_LOCAL_CONNECT = socket.socket.connect


def local_test_socketpair(family=None, type=socket.SOCK_STREAM, proto=0):
    """Windows asyncio IPC without granting application network access.

    The saved primitive connects only a fresh socket to this function's own
    ephemeral loopback listener. Returned sockets retain the blocked connect
    method; HTTP and every application/provider connection remain denied.
    """
    if family not in (None, socket.AF_INET) or type != socket.SOCK_STREAM or proto != 0:
        raise ValueError('Only local test IPC socket pairs are supported.')
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        _LOCAL_CONNECT(client, listener.getsockname())
        accepted, _ = listener.accept()
        return accepted, client
    except Exception:
        client.close()
        raise
    finally:
        listener.close()


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
    pair_guard = patch.object(socket, 'socketpair', local_test_socketpair) if os.name == 'nt' else nullcontext()
    with pair_guard, patch.object(socket.socket, 'connect', side_effect=AssertionError('Deployment smoke forbids network')), \
         patch.object(socket.socket, 'connect_ex', side_effect=AssertionError('Deployment smoke forbids network')), \
         patch('requests.sessions.Session.request', side_effect=AssertionError('Deployment smoke forbids HTTP')):
        from scripts.validate_render_topology import main as topology
        assert topology(['--path', str(root/'render.yaml')]) == 0
        from crm_lifecycle_definition import expanded_flow
        from crm_lifecycle_runtime import locked
        total = 0
        for kind in ('welcome', 'post_purchase', 'win_back'):
            flow = expanded_flow(kind)
            assert locked({'config': {'draft': flow}}), kind
            assert not locked({'config': {'draft': flow,'published_version':1}}), kind
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
