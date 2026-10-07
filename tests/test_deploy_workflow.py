"""Real Git integration against disposable, local-only bare origins. No GitHub."""
import contextlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.deploy import DeployError, Git, deploy, normalize, local_only_path


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "working"
        self.remote = self.base / "origin.git"
        self.root.mkdir()
        self.env = patch.dict(os.environ, {
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cmd("init", "--bare", str(self.remote))
        self.cmd("init", "-b", "main")
        self.cmd("config", "user.name", "Deployment fixture")
        self.cmd("config", "user.email", "fixture@example.invalid")
        self.cmd("config", "core.autocrlf", "false")
        self.cmd("config", "commit.gpgsign", "false")
        (self.root / "sports_cave_server.py").write_bytes(b"# fixture, never executed\n")
        (self.root / "source.py").write_bytes(b"VALUE = 1\n")
        self.cmd("add", ".")
        self.cmd("commit", "-m", "Fixture baseline")
        self.cmd("remote", "add", "origin", str(self.remote))
        self.cmd("push", "origin", "main")
        self.before = self.cmd("rev-parse", "HEAD")

    def cmd(self, *args):
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8", "replace").strip()

    def run_deploy(self, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = deploy(self.root, "Fixture change", expected_origin=str(self.remote), **kwargs)
        return result, output.getvalue()

    def change(self, value="VALUE = 2\n"):
        (self.root / "source.py").write_bytes(value.encode())

    def test_git_add_all_skips_local_workspaces_but_keeps_shopify_runtime(self):
        repository = Path(__file__).resolve().parents[1]
        shutil.copyfile(repository / '.gitignore', self.root / '.gitignore')
        local = ['.tmp-cw/capture.html', '.tmp-cwv/working/templates/product.json',
                 'shopify_theme_reviews/source/assets/main.js', '.tmp-deploy-review/run.log',
                 'test-results/screen.png', 'docs/evidence/local-export.json']
        production = ['shopify_client.py', 'shopify_theme/assets/sports-cave-image-protection.js',
                      'tests/fixtures/sport_taxonomy.json']
        for name in local + production:
            file = self.root / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('fixture\n', encoding='utf-8')
        self.cmd('add', '-A')
        indexed = self.cmd('ls-files').splitlines()
        for name in local:
            self.assertNotIn(name, indexed)
            self.assertTrue((self.root / name).is_file())
        for name in production:
            self.assertIn(name, indexed)
            self.assertFalse(local_only_path(name))

    def test_forced_local_file_staging_fails_before_commit(self):
        folder = self.root / 'shopify_theme_reviews'
        folder.mkdir()
        (folder / 'theme.json').write_text('{}\n')
        self.cmd('add', '-f', 'shopify_theme_reviews/theme.json')
        with self.assertRaisesRegex(DeployError, 'Local-only files'):
            self.run_deploy()
        self.assertEqual(self.before, self.cmd('rev-parse', 'HEAD'))
        self.assertTrue((folder / 'theme.json').is_file())

    def test_removing_committed_evidence_from_index_preserves_disk_and_can_deploy(self):
        folder = self.root / 'test-results'
        folder.mkdir()
        file = folder / 'result.txt'
        file.write_text('historic evidence\n')
        self.cmd('add', 'test-results/result.txt')
        self.cmd('commit', '-m', 'Historic fixture evidence')
        self.cmd('rm', '--cached', 'test-results/result.txt')
        result, _ = self.run_deploy()
        self.assertEqual(result, 'PUSHED')
        self.assertTrue(file.is_file())
        self.assertNotIn('test-results/result.txt', self.cmd('ls-files').splitlines())

    def test_clean_tree_success_no_commit_no_push(self):
        with patch.object(Git, "run", autospec=True, wraps=None) as observed:
            # Record calls while still exercising real Git.
            observed.side_effect = self.real_git_run
            result, output = self.run_deploy()
        self.assertEqual(result, "NOTHING TO DEPLOY")
        self.assertIn("Working tree clean", output)
        self.assertFalse(any(call.args[1] in ("commit", "push") for call in observed.call_args_list))
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))

    real_git_run = staticmethod(Git.run)

    def test_source_change_commit_and_local_push(self):
        self.change()
        result, output = self.run_deploy()
        self.assertEqual(result, "PUSHED")
        self.assertIn("COMMITTED", output)
        self.assertEqual(self.cmd("rev-parse", "HEAD"), self.cmd("rev-parse", "origin/main"))
        self.assertEqual(self.cmd("status", "--porcelain"), "")

    def test_extra_eof_and_trailing_space_repaired(self):
        self.change("VALUE = 2   \n\n   \n")
        result, _ = self.run_deploy()
        self.assertEqual(result, "PUSHED")
        self.assertEqual((self.root / "source.py").read_bytes(), b"VALUE = 2\n")
        self.assertEqual(self.cmd("diff", "HEAD^", "--check"), "")

    def test_whitespace_only_change_does_not_attempt_commit(self):
        self.change("VALUE = 1\n\n")
        result, _ = self.run_deploy()
        self.assertEqual(result, "NOTHING TO DEPLOY")
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))

    def test_real_syntax_failure_stops_before_commit(self):
        self.change("def broken(:\n")
        with self.assertRaisesRegex(DeployError, "syntax error"):
            self.run_deploy()
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))
        self.assertEqual(self.before, self.cmd("rev-parse", "origin/main"))

    def test_precommit_failure_stops_no_push(self):
        self.change()
        hook = self.root / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\necho Fixture real failure >&2\nexit 1\n")
        hook.chmod(0o755)
        with self.assertRaisesRegex(DeployError, "commit failed"):
            self.run_deploy()
        self.assertEqual(self.before, self.cmd("rev-parse", "origin/main"))

    def test_lf_crlf_warning_is_not_failure(self):
        self.cmd("config", "core.autocrlf", "true")
        self.change("VALUE = 2\n")
        result, output = self.run_deploy()
        self.assertEqual(result, "PUSHED")
        self.assertIn("LF will be replaced by CRLF", output)

    def test_partial_staging_is_preserved(self):
        self.change("VALUE = 2\n")
        self.cmd("add", "source.py")
        self.change("VALUE = 3\n")
        with self.assertRaisesRegex(DeployError, "Partially staged"):
            self.run_deploy()
        self.assertEqual(self.cmd("show", ":source.py"), "VALUE = 2")
        self.assertEqual((self.root / "source.py").read_text(), "VALUE = 3\n")

    def test_staged_selection_does_not_swallow_untracked(self):
        self.change()
        self.cmd("add", "source.py")
        (self.root / "notes.txt").write_text("private working notes\n")
        self.run_deploy()
        self.assertEqual(self.cmd("status", "--porcelain"), "?? notes.txt")

    def test_explicit_paths_and_literal_pathspec(self):
        name = "[draft] notes.py"
        (self.root / name).write_bytes(b"A = 1\n\n")
        self.change()
        self.run_deploy(paths=[name])
        self.assertIn("source.py", self.cmd("status", "--porcelain"))
        self.assertEqual(self.cmd("show", f"HEAD:{name}"), "A = 1")

    def test_binary_and_multiline_string_untouched(self):
        binary = self.root / "image.png"
        binary.write_bytes(b"\x89PNG\0\n\n")
        source = self.root / "literal.py"
        source.write_bytes(b'TEXT = """literal  \n  \n"""\n\n')
        self.assertFalse(normalize(binary))
        self.assertTrue(normalize(source))
        self.assertEqual(source.read_bytes(), b'TEXT = """literal  \n  \n"""\n')
        self.assertEqual(binary.read_bytes(), b"\x89PNG\0\n\n")

    def test_unrepairable_html_whitespace_stops(self):
        (self.root / "content.html").write_bytes(b"<pre>literal  \n</pre>\n")
        with self.assertRaisesRegex(DeployError, "diff failed"):
            self.run_deploy()
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))

    def test_fetch_failure_no_commit(self):
        self.change()
        missing = str(self.base / "missing.git")
        self.cmd("remote", "set-url", "origin", missing)
        with self.assertRaisesRegex(DeployError, "fetch failed"):
            deploy(self.root, "No commit", expected_origin=missing)
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))

    def test_rejected_push_reports_failure_then_requires_explicit_retry(self):
        self.change()
        hook = self.remote / "hooks/pre-receive"
        hook.write_bytes(b"#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        with self.assertRaisesRegex(DeployError, "push failed"):
            self.run_deploy()
        self.assertNotEqual(self.before, self.cmd("rev-parse", "HEAD"))
        self.assertEqual(self.before, self.cmd("rev-parse", "origin/main"))
        self.assertEqual(self.run_deploy()[0], "NOTHING TO DEPLOY")
        hook.unlink()
        self.assertEqual(self.run_deploy(push_existing=True)[0], "PUSHED")

    def test_remote_ahead_stops_without_rewriting_history(self):
        other = self.base / "other"
        self.cmd("clone", "-b", "main", str(self.remote), str(other))
        def other_git(*args):
            result = subprocess.run(["git", "-C", str(other), *args], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
        other_git("config", "user.name", "Other fixture")
        other_git("config", "user.email", "other@example.invalid")
        (other / "other.txt").write_bytes(b"Another commit\n")
        other_git("add", ".")
        other_git("commit", "-m", "Other commit")
        other_git("push", "origin", "main")
        self.change()
        with self.assertRaisesRegex(DeployError, "commits missing locally"):
            self.run_deploy()
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))

    def test_wrong_branch_and_remote_rejected(self):
        with self.assertRaisesRegex(DeployError, "origin fetch/push"):
            deploy(self.root, "No commit")
        self.cmd("switch", "-c", "feature")
        with self.assertRaisesRegex(DeployError, "Production uses main"):
            self.run_deploy()

    def test_check_only_stages_but_never_commits_or_pushes(self):
        self.change("VALUE = 2\n\n")
        result, _ = self.run_deploy(check_only=True)
        self.assertEqual(result, "CHECKS PASSED")
        self.assertEqual(self.before, self.cmd("rev-parse", "HEAD"))
        self.assertIn("source.py", self.cmd("diff", "--cached", "--name-only"))

    def test_clean_ahead_requires_explicit_push_existing(self):
        self.change()
        self.cmd("add", "source.py")
        self.cmd("commit", "-m", "Already committed")
        result, _ = self.run_deploy()
        self.assertEqual(result, "NOTHING TO DEPLOY")
        self.assertEqual(self.before, self.cmd("rev-parse", "origin/main"))
        self.assertEqual(self.run_deploy(push_existing=True)[0], "PUSHED")

    def test_powershell_wrapper_clean_and_real_failure_exit_codes(self):
        shell = shutil.which("powershell") or shutil.which("pwsh")
        if not shell:
            self.skipTest("PowerShell unavailable")
        repo = Path(__file__).resolve().parents[1]
        scripts = self.root / "scripts"
        scripts.mkdir()
        for name in ("deploy.ps1", "deploy_render.ps1"):
            shutil.copyfile(repo / "scripts" / name, scripts / name)
        # Same deploy engine and actual wrapper, with only the origin fixture seam.
        shim = (
            "import sys\nfrom pathlib import Path\n"
            f"sys.path.insert(0, {str(repo)!r})\n"
            "from scripts.deploy import deploy, DeployError\n"
            "try:\n"
            f"    deploy(Path({str(self.root)!r}), 'Fixture', expected_origin={str(self.remote)!r})\n"
            "except DeployError:\n    raise SystemExit(1)\n"
        )
        (scripts / "deploy.py").write_text(shim, encoding="utf-8")
        self.cmd("add", ".")
        self.cmd("commit", "-m", "Wrapper fixture")
        self.cmd("push", "origin", "main")
        env = dict(os.environ, PATH=str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"])
        commands = [[shell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(scripts / name)]
                    for name in ("deploy.ps1", "deploy_render.ps1")]
        for command in commands:
            result = subprocess.run(command, cwd=self.root, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(b"NOTHING TO DEPLOY", result.stdout)
        self.change("def broken(:\n")
        for command in commands:
            result = subprocess.run(command, cwd=self.root, env=env, capture_output=True)
            self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
