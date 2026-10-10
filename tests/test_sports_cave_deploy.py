"""Disposable Git origins and fake Render responses: never GitHub or production."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from scripts.sports_cave_deploy import Git, Render, SERVICES, Stop, deploy, digest, prepare, validate


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sports-cave-deploy-test-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base/'working'; self.root.mkdir()
        self.origin = self.base/'origin.git'; self.manifest = self.base/'release.json'
        self.env = patch.dict(os.environ, {'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                                         'GIT_TERMINAL_PROMPT': '0'})
        self.env.start(); self.addCleanup(self.env.stop)
        self.git('init', '--bare', str(self.origin)); self.git('init', '-b', 'main')
        self.git('config', 'user.name', 'Deployment test'); self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'core.autocrlf', 'false'); self.git('config', 'commit.gpgsign', 'false')
        (self.root/'sports_cave_server.py').write_text('# Never executed\n')
        (self.root/'source.py').write_text('VALUE = 1\n')
        self.git('add', '.'); self.git('commit', '-m', 'baseline')
        self.git('remote', 'add', 'origin', str(self.origin)); self.git('push', '-u', 'origin', 'main')
        self.before = self.git('rev-parse', 'HEAD')
        self.render = Mock()

    def git(self, *args):
        p = subprocess.run(['git', *args], cwd=self.root, capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr.decode(errors='replace'))
        return p.stdout.decode().strip()

    def approved(self, paths=('source.py',), mode='normal'):
        m = dict(version=1, mode=mode, base=self.before, message='Approved fixture', tests=[], imports=[],
                 files=[dict(path=p, sha256=digest((self.root/p).read_bytes()) if (self.root/p).exists() else None)
                        for p in paths])
        self.manifest.write_text(json.dumps(m)); return m

    def change(self):
        (self.root/'source.py').write_text('VALUE = 2\n'); self.approved()

    def run_deploy(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = deploy(self.root, self.manifest, expected_origin=str(self.origin),
                            render=self.render, validator=kwargs.pop('validator', lambda *args: None), **kwargs)
        return result, output.getvalue()

    def unchanged(self):
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.before)
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

    def test_clean_and_already_current(self):
        self.approved([]); self.assertEqual(self.run_deploy()[0], 'NOTHING'); self.unchanged()
        self.approved(); self.assertEqual(self.run_deploy()[0], 'NOTHING'); self.unchanged()

    def test_modified_new_and_unfinished_exclusion(self):
        self.change(); (self.root/'new.py').write_text('NEW = True\n')
        (self.root/'support_email_page.py').write_text('UNFINISHED = True\n')
        (self.root/'tmp').mkdir(); (self.root/'tmp/private.log').write_text('private')
        self.approved(['source.py', 'new.py'])
        def inspect(candidate, paths, manifest):
            self.assertEqual((candidate/'source.py').read_text(), 'VALUE = 2\n')
            self.assertFalse((candidate/'support_email_page.py').exists())
            self.assertFalse((candidate/'tmp').exists())
        result, output = self.run_deploy(validator=inspect)
        self.assertEqual(result, 'LIVE'); self.assertIn('PUSHED:', output)
        self.assertEqual(self.git('rev-parse', 'HEAD'), self.git('rev-parse', 'origin/main'))
        self.assertTrue((self.root/'support_email_page.py').exists())
        self.assertNotIn('support_email', self.git('show', '--format=', '--name-only', 'HEAD'))
        self.render.wait.assert_called_once_with(self.git('rev-parse', 'HEAD'))

    def test_dry_run_preserves_everything(self):
        self.change(); before = (self.root/'source.py').read_bytes()
        self.assertEqual(self.run_deploy(dry_run=True)[0], 'DRY_RUN'); self.unchanged()
        self.assertEqual(before, (self.root/'source.py').read_bytes()); self.render.preflight.assert_not_called()

    def test_remote_advanced_stops_without_overwrite(self):
        self.change()
        other = self.base/'other'; self.git('clone', str(self.origin), str(other))
        subprocess.run(['git', 'checkout', 'main'], cwd=other, check=True, capture_output=True)
        (other/'source.py').write_text('REMOTE = True\n')
        for args in [('config','user.name','Remote'),('config','user.email','remote@example.invalid'),
                     ('add','source.py'),('commit','-m','remote'),('push','origin','main')]:
            subprocess.run(['git',*args], cwd=other, check=True, capture_output=True)
        with self.assertRaisesRegex(Stop, 'Remote branch advanced'): self.run_deploy()
        self.unchanged(); self.assertEqual((self.root/'source.py').read_text(), 'VALUE = 2\n')

    def test_staged_work_conflict_marker_and_index_lock(self):
        self.change(); self.git('add', 'source.py')
        with self.assertRaisesRegex(Stop, 'staged work'): self.run_deploy()
        self.assertEqual(self.git('diff','--cached','--name-only'), 'source.py')
        self.git('restore','--staged','source.py')
        (self.root/'.git/MERGE_HEAD').write_text(self.before+'\n')
        with self.assertRaisesRegex(Stop, 'existing merge'): self.run_deploy()
        (self.root/'.git/MERGE_HEAD').unlink()
        (self.root/'.git/index.lock').write_text('other task')
        with self.assertRaisesRegex(Stop, 'index is busy'): self.run_deploy()
        self.assertEqual((self.root/'.git/index.lock').read_text(), 'other task')

    def test_missing_remote_reference(self):
        self.change(); subprocess.run(['git','--git-dir',str(self.origin),'update-ref','-d','refs/heads/main'],check=True)
        with self.assertRaisesRegex(Stop, 'fetch failed'): self.run_deploy()
        self.unchanged()

    def test_missing_local_tracking_reference_is_refetched(self):
        self.change();self.git('update-ref','-d','refs/remotes/origin/main')
        self.assertEqual(self.run_deploy(dry_run=True)[0],'DRY_RUN')
        self.assertEqual(self.git('rev-parse','origin/main'),self.before)

    def test_stale_worktree_is_ignored_not_deleted(self):
        self.change(); path = self.base/'stale'
        self.git('worktree','add','--detach',str(path),'HEAD'); shutil.rmtree(path)
        self.assertEqual(self.run_deploy(dry_run=True)[0], 'DRY_RUN')
        self.assertIn(str(path).replace('\\','/'), self.git('worktree','list','--porcelain'))

    def test_failed_tests_preserve_index_and_branch(self):
        self.change()
        with self.assertRaisesRegex(Stop, 'fixture test failed'):
            self.run_deploy(validator=Mock(side_effect=Stop('fixture test failed')))
        self.unchanged(); self.render.wait.assert_not_called()

    def test_fetch_authentication_failure(self):
        self.change(); original = Git.run
        def fail(git, *args, **kwargs):
            if args[0]=='fetch': raise Stop('git fetch failed: authentication')
            return original(git,*args,**kwargs)
        with patch.object(Git,'run',fail), self.assertRaisesRegex(Stop,'authentication'): self.run_deploy()
        self.unchanged()

    def test_push_failure_retains_commit_and_retry_is_idempotent(self):
        self.change(); hook = self.origin/'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
        with self.assertRaisesRegex(Stop, 'push failed'): self.run_deploy()
        committed = self.git('rev-parse','HEAD'); self.assertNotEqual(committed,self.before)
        self.assertEqual(self.git('rev-parse','origin/main'),self.before)
        self.render.wait.assert_not_called(); hook.unlink()
        self.assertEqual(self.run_deploy()[0], 'LIVE')
        self.assertEqual(self.git('rev-parse','HEAD'),committed)
        self.assertEqual(self.run_deploy()[0], 'LIVE')
        self.assertEqual(self.git('rev-parse','HEAD'),committed)

    def test_missing_render_credentials_never_claims_live(self):
        self.change(); self.render=Render(token='')
        result, output=self.run_deploy()
        self.assertEqual(result,'UNVERIFIED');self.assertIn('RENDER UNVERIFIED',output)
        self.assertNotIn('DEPLOYED AND HEALTHY',output)

    def test_render_failure_never_claims_success(self):
        self.change(); self.render.wait.side_effect=Stop('PUSHED BUT NOT LIVE: build_failed')
        with self.assertRaisesRegex(Stop,'NOT LIVE'): self.run_deploy()
        self.assertEqual(self.git('rev-parse','HEAD'),self.git('rev-parse','origin/main'))

    def test_explicit_unverified_is_distinct_result(self):
        self.change(); self.assertEqual(self.run_deploy(unverified=True)[0], 'UNVERIFIED')
        self.render.wait.assert_not_called()

    def test_migration_secrets_inbox_and_path_traversal_rejected(self):
        for name in ('migrations/new.sql','.env','tmp/test.py','support_email_page.py','app.py','../outside.py'):
            path=self.root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_text('fixture')
            self.approved([name])
            with self.subTest(name=name),self.assertRaises(Stop):self.run_deploy()
            self.unchanged()

    def test_changed_hash_and_unapproved_local_commit(self):
        self.change(); (self.root/'source.py').write_text('NEWER = True\n')
        with self.assertRaisesRegex(Stop,'changed since manifest'):self.run_deploy()
        self.approved(); (self.root/'other.py').write_text('UNAPPROVED = True\n')
        self.git('add','other.py');self.git('commit','-m','unapproved')
        with self.assertRaisesRegex(Stop,'outside this manifest'):self.run_deploy()

    def test_normal_and_full_manifests_are_separate(self):
        self.change(); self.approved(mode='full')
        with self.assertRaisesRegex(Stop,'Invalid deployment manifest'):self.run_deploy()
        self.assertEqual(self.run_deploy(mode='full',dry_run=True)[0],'DRY_RUN')

    def test_prepare_explicit_paths_only(self):
        self.change()
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(self.root,self.manifest,'normal',['source.py'],[],[],'message',str(self.origin))
        self.assertEqual(json.loads(self.manifest.read_text())['files'][0]['path'],'source.py');self.unchanged()

    def test_explicit_deletion_only(self):
        (self.root/'source.py').unlink();self.approved()
        self.assertEqual(self.run_deploy()[0],'LIVE')
        self.assertNotIn('source.py',self.git('ls-files'))

    def test_crlf_rules_do_not_dirty_committed_files_or_rewrite_work(self):
        (self.root/'.gitattributes').write_text('* text=auto eol=lf\n')
        self.git('add','.gitattributes');self.git('commit','-m','attributes');self.git('push','origin','main')
        self.before=self.git('rev-parse','HEAD')
        data=b'VALUE = 2\r\n';(self.root/'source.py').write_bytes(data);self.approved()
        self.assertEqual(self.run_deploy()[0],'LIVE')
        self.assertEqual((self.root/'source.py').read_bytes(),data)
        self.assertEqual(self.git('diff','HEAD','--','source.py'),'')
        self.assertEqual(self.run_deploy()[0],'LIVE')

    def test_unapproved_attributes_stop_candidate(self):
        self.change();(self.root/'.gitattributes').write_text('* text eol=lf\n')
        with self.assertRaisesRegex(Stop,'Uncommitted Git attributes'):self.run_deploy()
        self.unchanged()

    def test_candidate_import_failure_is_not_ignored(self):
        self.change()
        def imports(candidate, paths, manifest):
            process=subprocess.run([sys.executable,'-c','import missing_sports_cave_fixture_module'],cwd=candidate,capture_output=True)
            if process.returncode:raise Stop('Candidate import failed')
        with self.assertRaisesRegex(Stop,'Candidate import failed'):self.run_deploy(validator=imports)
        self.unchanged()

    def test_python_and_javascript_syntax_errors(self):
        self.change(); (self.root/'source.py').write_text('def invalid(:\n');self.approved()
        with self.assertRaisesRegex(Stop,'Python syntax error'):self.run_deploy(validator=validate,dry_run=True)
        if shutil.which('node'):
            (self.root/'source.js').write_text('const = ;');self.approved(['source.js'])
            with self.assertRaisesRegex(Stop,'Validation failed'):self.run_deploy(validator=validate,dry_run=True)
        self.unchanged()

    def test_concurrent_edits_and_staging_are_preserved(self):
        self.change()
        def edit(*args): (self.root/'source.py').write_text('LATEST = True\n')
        with self.assertRaisesRegex(Stop,'changed since manifest'):self.run_deploy(validator=edit)
        self.assertEqual((self.root/'source.py').read_text(),'LATEST = True\n');self.unchanged()
        self.approved()
        def stage(*args):
            (self.root/'other.py').write_text('OTHER = True\n');self.git('add','other.py')
        with self.assertRaisesRegex(Stop,'Another task staged'):self.run_deploy(validator=stage)
        self.assertEqual(self.git('diff','--cached','--name-only'),'other.py')

    def test_failed_commit_hook_stops_without_losing_work(self):
        self.change();hook=self.root/'.git/hooks/pre-commit'
        hook.write_text('#!/bin/sh\nexit 1\n');hook.chmod(0o755)
        with self.assertRaisesRegex(Stop,'commit failed'):self.run_deploy()
        self.unchanged();self.assertFalse((self.root/'.git/index.lock').exists())

    def test_unmerged_index_blocks(self):
        self.change();oid=self.git('rev-parse','HEAD:source.py')
        payload=f'0 {"0"*40}\tsource.py\n100644 {oid} 1\tsource.py\n100644 {oid} 2\tsource.py\n100644 {oid} 3\tsource.py\n'
        subprocess.run(['git','update-index','--index-info'],input=payload.encode(),cwd=self.root,check=True)
        with self.assertRaisesRegex(Stop,'Unresolved index conflicts'):self.run_deploy()

    def test_wrong_upstream_and_branch(self):
        self.change();self.git('config','branch.main.merge','refs/heads/missing')
        with self.assertRaises(Stop):self.run_deploy()
        self.git('config','branch.main.merge','refs/heads/main');self.git('checkout','-b','feature')
        with self.assertRaisesRegex(Stop,'Production deploys main'):self.run_deploy()


class RenderTests(unittest.TestCase):
    def test_failure_timeout_and_wrong_sha(self):
        for status in ('build_failed','update_failed','pre_deploy_failed','canceled','deactivated'):
            client=Render('fixture',timeout=0);client.get=Mock(return_value=[{'deploy':{'commit':{'id':'sha'},'status':status}}])
            with self.subTest(status=status),self.assertRaisesRegex(Stop,'NOT LIVE'):client.wait('sha')
        client.get=Mock(return_value=[{'deploy':{'commit':{'id':'other'},'status':'live'}}])
        with self.assertRaisesRegex(Stop,'UNCONFIRMED'):client.wait('sha')

    def test_configuration_disabled_or_wrong_branch_fails(self):
        client=Render('fixture');client.get=Mock(return_value={'autoDeploy':'no','branch':'other'})
        with self.assertRaisesRegex(Stop,'configuration mismatch'):client.preflight()

    def test_all_services_expected_sha_and_health_required(self):
        client=Render('fixture');client.get=Mock(return_value=[{'deploy':{'commit':{'id':'sha'},'status':'live'}}])
        response=Mock();response.status=200;response.read.return_value=b'{"git_sha":"sha"}'
        response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        with patch('urllib.request.urlopen',return_value=response),contextlib.redirect_stdout(io.StringIO()):client.wait('sha')
        self.assertEqual(client.get.call_count,len(SERVICES))
        response.read.return_value=b'{"git_sha":"wrong"}'
        with patch('urllib.request.urlopen',return_value=response),self.assertRaisesRegex(Stop,'SHA differs'):client.wait('sha')


if __name__=='__main__':unittest.main()
