from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "scripts" / "validate_render_topology.py"


class RenderTopologyTests(unittest.TestCase):
    def run_guard(self, text=None):
        path = ROOT / "render.yaml"
        temporary = None
        if text is not None:
            temporary = tempfile.TemporaryDirectory()
            path = Path(temporary.name) / "render.yaml"
            path.write_text(text, encoding="utf-8")
        try:
            return subprocess.run(
                [sys.executable, str(GUARD), "--path", str(path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        finally:
            if temporary is not None:
                temporary.cleanup()

    def test_repository_blueprint_cannot_recreate_primary_app(self):
        result = self.run_guard()

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        render_yaml = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertNotIn("name: sports-cave-image-factory\n", render_yaml)
        self.assertNotIn("name: sports-cave-os\n", render_yaml)
        self.assertEqual(1, render_yaml.count("name: sports-cave-os-webhooks"))

    def test_guard_rejects_one_or_more_blueprint_primary_apps(self):
        result = self.run_guard(
            """services:
  - type: web
    name: sports-cave-os
    startCommand: python sports_cave_server.py
  - type: web
    name: sports-cave-image-factory
    startCommand: python sports_cave_server.py
  - type: web
    name: sports-cave-os-webhooks
    startCommand: python webhook_server.py
"""
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("must declare zero primary apps", result.stdout)
        self.assertIn("RENDER_SERVICE_TOPOLOGY.md", result.stdout)

    def test_intentional_supporting_services_are_allowed(self):
        result = self.run_guard(
            """services:
  - type: web
    name: sports-cave-os-webhooks
    startCommand: python webhook_server.py
  - type: worker
    name: sports-cave-seo-worker
    startCommand: python google_seo_import.py worker
  - type: cron
    name: sports-cave-seo-daily-sync
    startCommand: python google_seo_import.py daily
"""
        )

        self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
