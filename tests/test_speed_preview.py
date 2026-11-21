import importlib.util
from pathlib import Path
import sys
import socket
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_static_catalog_resolves_current_navigation_without_app_execution():
    sys.path.insert(0, str(ROOT / 'scripts' / 'studio'))
    from page_catalog import pages
    import os_accounts
    catalog = pages(ROOT)
    assert {p['key'] for p in catalog if p['key'] != '__signin__'} == {p['key'] for p in os_accounts.PAGE_REGISTRY}
    assert any(p['key'] == 'speed_optimisation' for p in catalog)


def test_static_catalog_does_not_execute_imports_or_calls(tmp_path):
    sys.path.insert(0, str(ROOT / 'scripts' / 'studio'))
    from page_catalog import pages
    (tmp_path / 'os_accounts.py').write_text("import os\nPAGE_REGISTRY = os.system('forbidden')\n")
    with pytest.raises(ValueError, match='statically'):
        pages(tmp_path)


def test_preview_exports_source_dependency_without_runtime_or_credentials():
    sys.path.insert(0, str(ROOT / 'scripts' / 'studio'))
    import preview_export
    assert preview_export.allowed('services/r2_storage.py')
    assert not preview_export.allowed('services/credentials.json')
    assert not preview_export.allowed('services/.env')
    assert not preview_export.allowed('services/customer_data.csv')
    assert preview_export.allowed('data/home_sports_schedule.json')
    assert not preview_export.allowed('data/customers.json')


def test_cleanup_candidates_preserve_public_exports_and_never_delete(tmp_path):
    spec = importlib.util.spec_from_file_location('speed_code_review', ROOT / 'scripts/speed_code_review.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = 'import unused\nfrom source import exported\n__all__ = ["exported"]\n'
    (tmp_path / 'fixture.py').write_text(source)
    result = module.inspect(tmp_path, ['fixture.py'])
    assert [r['name'] for r in result['candidates']] == ['unused']
    assert not result['code_deleted']
    assert (tmp_path / 'fixture.py').read_text() == source


def test_nightly_release_cannot_reuse_installation_exception_or_regress():
    spec = importlib.util.spec_from_file_location('speed_release', ROOT / 'scripts/speed_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    gate = dict(commit='a' * 40, phase2_verified=True, functional_checks_passed=True, purpose='installation')
    with pytest.raises(module.Stop, match='initial authorised'):
        module.check_gate(gate, 'a' * 40, 'b' * 40, 'nightly-task')
    gate.update(purpose='improvement', behaviour_preserved=True, baseline_samples_ms=[100, 100, 100],
                candidate_samples_ms=[200, 200, 200], code_smaller=True)
    with pytest.raises(module.Stop, match='No proven improvement'):
        module.check_gate(gate, 'a' * 40, 'b' * 40, 'nightly-task')
    gate['candidate_samples_ms'] = [90, 90, 90]
    module.check_gate(gate, 'a' * 40, 'b' * 40, 'nightly-task')
    with pytest.raises(module.Stop, match='Exact-commit'):
        module.check_gate(gate, 'c' * 40, 'b' * 40, 'nightly-task')
    before = b'from worker_health_api import ROUTES as WORKER_HEALTH_ROUTES\n        *WORKER_HEALTH_ROUTES,\n'
    after = b'from worker_health_api import ROUTES as WORKER_HEALTH_ROUTES\nfrom speed_optimisation_api import ROUTES as SPEED_OPTIMISATION_ROUTES\n        *WORKER_HEALTH_ROUTES,\n        *SPEED_OPTIMISATION_ROUTES,\n'
    module.reviewed_server_source(before, after)
    with pytest.raises(module.Stop, match='exceeds'):
        module.reviewed_server_source(before, after + b'run_migrations()\n')


def test_windows_ipc_fix_keeps_application_network_denied():
    from scripts.sports_cave_deploy_smoke import local_test_socketpair
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network denied')):
        a, b = local_test_socketpair()
        try:
            assert a.getsockname()[0] == b.getsockname()[0] == '127.0.0.1'
            b.sendall(b'local-ipc')
            assert a.recv(9) == b'local-ipc'
            with pytest.raises(AssertionError, match='network denied'):
                b.connect(('192.0.2.1', 443))
            with socket.socket() as external:
                with pytest.raises(AssertionError, match='network denied'):
                    external.connect(('192.0.2.1', 443))
        finally:
            a.close(); b.close()
