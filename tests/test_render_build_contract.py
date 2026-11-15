"""Offline checks for the shared dependency/runtime fix, not a live deploy."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]


class RenderBuildContractTests(unittest.TestCase):
    def test_render_runtime_matches_existing_declared_runtime(self):
        version = (ROOT / ".python-version").read_text().strip()
        self.assertEqual(version, "3.12.8")
        self.assertEqual((ROOT / "runtime.txt").read_text().strip(), "python-" + version)

    def test_dateutil_uses_official_hash_verified_universal_wheel(self):
        requirements = (ROOT / "requirements.txt").read_text()
        self.assertIn("svix==1.99.1", requirements)
        direct = next(line for line in requirements.splitlines() if line.startswith("python-dateutil @ "))
        url = urlsplit(direct.split(" @ ", 1)[1])
        self.assertEqual(url.scheme, "https")
        self.assertEqual(url.hostname, "files.pythonhosted.org")
        self.assertTrue(url.path.endswith("python_dateutil-2.9.0.post0-py2.py3-none-any.whl"))
        self.assertEqual(url.fragment, "sha256=a8b2bc7bffae282281c8140a97d3aa9c14da0b136dfe83f850eea9a5f7470427")

    def test_service_entrypoints_and_crm_modules_import_without_network(self):
        script = '''
import importlib, json, socket
def blocked(*args, **kwargs):
    raise AssertionError('Network during import is forbidden')
socket.create_connection = blocked
socket.socket.connect = blocked
modules = ['sports_cave_server', 'webhook_server', 'google_seo_import',
           'crm_campaign_html', 'crm_campaign_page', 'crm_html_workspace',
           'crm_settings_page', 'crm_store', 'crm_workspace_store',
           'crm_brand_templates', 'crm_brand_template_ui']
for name in modules:
    importlib.import_module(name)
print('IMPORTS_OK=' + json.dumps(modules))
'''
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace")[-2500:])
        self.assertIn(b"IMPORTS_OK=", result.stdout)

    def test_vscode_preserves_literal_whitespace_and_trims_extra_eof(self):
        settings = json.loads((ROOT / ".vscode/settings.json").read_text())
        self.assertTrue(settings["files.trimFinalNewlines"])
        self.assertTrue(settings["files.insertFinalNewline"])
        self.assertFalse(settings["files.trimTrailingWhitespace"])
        self.assertEqual(settings["files.eol"], "\n")


if __name__ == "__main__":
    unittest.main()
