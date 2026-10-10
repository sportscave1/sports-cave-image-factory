"""Manifest-selected deployment; no implicit all-files staging or production writes except Git push.

The production CLI pins repository, branch and Render service identities. Test fixtures
inject local origins and fake Render clients through the Python API only.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

REPO = 'sportscave1/sports-cave-image-factory'
ORIGINS = {f'https://github.com/{REPO}', f'https://github.com/{REPO}.git',
           f'git@github.com:{REPO}.git', f'ssh://git@github.com/{REPO}.git'}
SERVICES = {
    'srv-d8kl4on7f7vs73dvavv0': 'sports-cave-os',
    'srv-d9146onlk1mc739nrm7g': 'sports-cave-os-webhooks',
    'srv-d9ujm9navr4c73amurgg': 'sports-cave-seo-worker',
    'crn-d9ujqvvqj5pc73fpe0ag': 'sports-cave-seo-daily-sync',
}
HEALTH = ('https://sports-cave-image-factory.onrender.com/_stcore/health',
          'https://sports-cave-os-webhooks.onrender.com/healthz')
SENSITIVE = {'render.yaml', 'requirements.txt', 'sports_cave_server.py', 'run_migrations.py',
             '.gitattributes', '.gitmodules',
             'crm_lifecycle_runtime.py', 'crm_lifecycle_definition.py', 'crm_automation_publication.py',
             'crm_automation_runtime.py', 'crm_engine.py', 'crm_worker.py'}
INBOX_HOLD = ('app.py', 'support_email*', 'components/support_email/*', 'tests/*email*',
              'tests/fixtures/email*', 'docs/EMAIL_INBOX*', 'docs/email-inbox*')


class Stop(RuntimeError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def excluded(name):
    p = PurePosixPath(name.lower())
    return (any(part in {'.git', '.venv', 'venv', 'node_modules', '__pycache__', 'tmp',
                        'input', 'output', 'data', 'test-results', '.render', '.shopify'}
                or part.startswith('.tmp') for part in p.parts)
            or p.name.startswith('.env') or p.name in {'secrets.toml', 'credentials.json',
                'token.json', 'client_secret.json', 'service-account.json'}
            or p.suffix in {'.pyc', '.db', '.sqlite', '.log', '.zip', '.patch'}
            or any(part.endswith('-evidence') for part in p.parts)
            or name.startswith(('shopify_theme_reviews/', 'supabase/.temp/')))


def safe_path(root, name):
    if not isinstance(name, str) or '\\' in name or ':' in name or '\n' in name or '\r' in name:
        raise Stop('Manifest paths must be exact repository-relative forward-slash paths.')
    parts = PurePosixPath(name)
    if parts.is_absolute() or '..' in parts.parts or str(parts) != name or name == '.':
        raise Stop(f'Unsafe path: {name!r}')
    path = root / name
    if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
        raise Stop(f'Path leaves repository or is a symlink: {name}')
    if excluded(name):
        raise Stop(f'Local/generated/secret path cannot be deployed: {name}')
    if name in SENSITIVE or name.startswith(('migrations/', 'supabase/migrations/', '.streamlit/',
                                             '.github/', 'shopify_theme/')) or path.suffix == '.sql':
        raise Stop(f'Production-sensitive change requires separate review/approval: {name}. '
                   'This routine helper cannot apply migrations, change infrastructure or unlock sending.')
    return path


class Git:
    def __init__(self, root, env=None):
        self.root = Path(root)
        self.env = dict(os.environ, GIT_TERMINAL_PROMPT='0', **(env or {}))

    def run(self, *args, input=None, allow=(0,)):
        r = subprocess.run(['git', *args], cwd=self.root, env=self.env,
                           input=input, capture_output=True)
        if r.returncode not in allow:
            operation = next(a for a in args if not a.startswith('-'))
            hint = {'fetch': 'Check GitHub authentication/network and that origin/main exists.',
                    'push': 'Commit is retained locally. Check authentication/branch protection; '
                            'rerun the SAME manifest after resolving it. Never force-push.',
                    'commit': 'Check Git identity and repository hooks; no push was performed.'}.get(operation, '')
            # Remote errors may contain credential-bearing URLs; do not echo them.
            raise Stop(f'git {operation} failed (exit {r.returncode}). {hint}')
        return r.stdout

    def text(self, *args):
        return self.run(*args).decode('utf-8').strip()


def verify_repository(git, expected_origin=None):
    if Path(git.text('rev-parse', '--show-toplevel')).resolve() != git.root.resolve():
        raise Stop('Run the helper from its main repository, not a nested or temporary checkout.')
    if not (git.root / 'sports_cave_server.py').is_file():
        raise Stop('Sports Cave application root not found.')
    if git.text('branch', '--show-current') != 'main':
        raise Stop('Production deploys main. Detached HEAD/other branch refused.')
    accepted = {expected_origin} if expected_origin else ORIGINS
    for args in [('remote', 'get-url', 'origin'), ('remote', 'get-url', '--push', 'origin')]:
        if git.text(*args) not in accepted:
            raise Stop('origin fetch/push must point to sportscave1/sports-cave-image-factory.')
    if (git.text('config', '--get', 'branch.main.remote') != 'origin' or
            git.text('config', '--get', 'branch.main.merge') != 'refs/heads/main'):
        raise Stop('main must track origin/main; inspect git branch -vv and set the correct upstream.')
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'REVERT_HEAD', 'rebase-merge', 'rebase-apply'):
        path = Path(git.text('rev-parse', '--git-path', marker))
        if (path if path.is_absolute() else git.root / path).exists():
            raise Stop('Finish the existing merge/rebase/cherry-pick first. Nothing was staged.')
    if git.run('ls-files', '-u'):
        raise Stop('Unresolved index conflicts. Resolve them before deployment.')
    if git.run('diff', '--cached', '--name-only'):
        raise Stop('Existing staged work is preserved. Review/unstage it before using a manifest.')


def fetch(git):
    git.run('fetch', 'origin', 'refs/heads/main:refs/remotes/origin/main')
    return git.text('rev-parse', '--verify', 'refs/remotes/origin/main^{commit}')


def read_manifest(path, mode):
    if not path.is_file():
        raise Stop(f'No approved release manifest: {path}. Prepare exact ready paths with -Prepare -Paths; '
                   'no files will be guessed or staged.')
    try:
        m = json.loads(path.read_text(encoding='utf-8-sig'))
        assert m['version'] == 1 and m['mode'] == mode
        assert isinstance(m['files'], list)
        assert isinstance(m['tests'], list) and isinstance(m['imports'], list)
        assert re.fullmatch('[0-9a-f]{40}', m['base'])
        assert isinstance(m['message'], str) and m['message'].strip()
    except (ValueError, KeyError, AssertionError, TypeError):
        raise Stop('Invalid deployment manifest; regenerate with -Prepare.') from None
    return m


def prepare(root, manifest, mode, paths, tests, imports, message, expected_origin=None, completed_inbox=False):
    git = Git(root); verify_repository(git, expected_origin)
    remote = fetch(git)
    if git.text('rev-parse', 'HEAD') != remote:
        raise Stop('Synchronize/review local history before preparing a release. No automatic merge.')
    if not paths or len(paths) != len(set(paths)):
        raise Stop('-Prepare requires a nonempty, duplicate-free list of exact approved file paths.')
    records = []
    for name in paths:
        if any(fnmatchcase(name, pattern) for pattern in INBOX_HOLD) and not completed_inbox:
            raise Stop(f'Active Email Inbox work is held: {name}. Only the user may authorize '
                       '-Prepare -IncludeCompletedInbox after that project is complete and tested.')
        path = safe_path(root, name)
        if path.exists() and not path.is_file():
            raise Stop(f'Select files individually, not directories: {name}')
        if not path.exists():
            git.run('cat-file', '-e', f'HEAD:{name}')
        records.append({'path': name, 'sha256': digest(path.read_bytes()) if path.exists() else None})
    m = dict(version=1, mode=mode, base=remote, message=message, files=records,
             tests=tests, imports=imports, completed_inbox_approved=completed_inbox)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(m, indent=2)+'\n', encoding='utf-8')
    print(f'Prepared {manifest}: {len(records)} exact files. No commit/push. Review before deployment.')


def selected_bytes(root, m):
    selected = {}
    for entry in m['files']:
        name, sha = entry['path'], entry['sha256']
        if any(fnmatchcase(name, pattern) for pattern in INBOX_HOLD) and not m.get('completed_inbox_approved'):
            raise Stop(f'Active Email Inbox work is excluded: {name}. Completion never automatically authorizes deployment.')
        path = safe_path(root, name)
        if name in selected:
            raise Stop(f'Duplicate manifest entry: {name}')
        data = path.read_bytes() if path.is_file() else None
        if (digest(data) if data is not None else None) != sha:
            raise Stop(f'Approved file changed since manifest preparation: {name}. Review and re-prepare.')
        selected[name] = data
    return selected


def verify_attributes(git, paths):
    # Git clean filters must come from committed attributes, not unfinished local work.
    attributes = {PurePosixPath('.gitattributes')}
    for name in paths:
        for parent in PurePosixPath(name).parents:
            attributes.add(parent/'.gitattributes')
    for name in attributes:
        path = git.root/str(name)
        saved = git.run('show', 'HEAD:'+str(name), allow=(0, 128))
        current = path.read_bytes() if path.is_file() else b''
        if current.replace(b'\r\n', b'\n') != saved.replace(b'\r\n', b'\n'):
            raise Stop(f'Uncommitted Git attributes affect release selection: {name}. Review separately.')


def export_tree(git, tree, target):
    """Export Git blobs, not local unapproved files; no registered worktree or inherited secrets."""
    records = git.run('ls-tree', '-rz', '--full-tree', tree).split(b'\0')
    process = subprocess.Popen(['git', 'cat-file', '--batch'], cwd=git.root, env=git.env,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    try:
        for record in records:
            if not record:
                continue
            meta, rawname = record.split(b'\t', 1); mode, typ, oid = meta.split()
            name = rawname.decode('utf-8')
            if excluded(name) or typ != b'blob':
                continue
            if mode not in (b'100644', b'100755') or '..' in PurePosixPath(name).parts:
                raise Stop(f'Unsupported candidate entry: {name}')
            process.stdin.write(oid+b'\n'); process.stdin.flush()
            header = process.stdout.readline().split(); size = int(header[2])
            content = process.stdout.read(size); assert process.stdout.read(1) == b'\n'
            path = target / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(content)
    finally:
        process.stdin.close(); process.stdout.close(); process.wait()


def command(args, cwd, env):
    result = subprocess.run(args, cwd=cwd, env=env)
    if result.returncode:
        raise Stop(f'Validation failed: {args[0]} (exit {result.returncode}). No push performed.')


def validate(candidate, paths, manifest):
    # No production secrets/config are passed into import/smoke test processes.
    env = {k: v for k, v in os.environ.items() if k.upper() in
           {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT', 'LOCALAPPDATA'}}
    env.update(PYTHONPATH=str(candidate), PYTHONDONTWRITEBYTECODE='1', PYTHONIOENCODING='utf-8')
    profile = candidate.parent/'smoke-profile'
    profile.mkdir(exist_ok=True)
    env['USERPROFILE'] = str(profile)  # Isolated Streamlit config, no user's secrets.
    for name in paths:
        file = candidate / name
        if not file.is_file():
            continue
        if file.suffix == '.py':
            try: compile(file.read_bytes(), name, 'exec')
            except SyntaxError as exc: raise Stop(f'Python syntax error: {name}:{exc.lineno}: {exc.msg}') from None
        elif file.suffix in ('.js', '.cjs', '.mjs'):
            command(['node', '--check', str(file)], candidate, env)
        elif file.suffix == '.json':
            try: json.loads(file.read_text(encoding='utf-8-sig'))
            except ValueError: raise Stop(f'Invalid JSON: {name}') from None
    smoke = Path(__file__).with_name('sports_cave_deploy_smoke.py')
    command([sys.executable, str(smoke), '--candidate', str(candidate),
             '--manifest-json', json.dumps(manifest)], candidate, env)


class Render:
    def __init__(self, token=None, timeout=900):
        self.token = token if token is not None else os.getenv('RENDER_API_KEY')
        self.timeout = timeout

    def get(self, path):
        request = urllib.request.Request('https://api.render.com/v1/'+path,
                     headers={'Authorization': 'Bearer '+self.token, 'Accept': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, ValueError) as exc:
            raise Stop(f'Render read-only API unavailable ({type(exc).__name__}); no deployment success claimed.') from None

    def preflight(self):
        if not self.token:
            raise Stop('RENDER_API_KEY is missing in this terminal. Set it securely once, then rerun. '
                       'Codex connector authentication is separate. No commit/push performed. '
                       '-PushWithoutRenderVerification explicitly permits push-only with exit code 2.')
        for identity, name in SERVICES.items():
            service = self.get('services/'+identity)
            if (service.get('id') != identity or service.get('name') != name or
                service.get('branch') != 'main' or service.get('repo') not in ORIGINS or
                service.get('autoDeploy') != 'yes' or service.get('autoDeployTrigger') != 'commit'):
                raise Stop(f'Render configuration mismatch for {name}. Check existing service repo/branch/auto-deploy; '
                           'no replacement service or duplicate deploy will be created.')
            if service.get('suspended') == 'suspended':
                raise Stop(f'Render service suspended: {name}')

    def wait(self, sha):
        until = time.monotonic()+self.timeout
        last = None
        while True:
            statuses = {}
            for identity, name in SERVICES.items():
                rows = self.get(f'services/{identity}/deploys?limit=20')
                deploys = [row.get('deploy', row) for row in rows]
                matching = next((d for d in deploys if d.get('commit', {}).get('id') == sha), None)
                status = matching.get('status') if matching else 'awaiting_auto_deploy'
                statuses[name] = status
                if status in {'build_failed', 'update_failed', 'pre_deploy_failed', 'canceled', 'deactivated'}:
                    raise Stop(f'PUSHED BUT NOT LIVE: {name}: {status}, commit {sha}. Inspect Render logs; do not push again blindly.')
            if statuses != last:
                print('Render: '+json.dumps(statuses), flush=True); last = statuses
            if all(value == 'live' for value in statuses.values()):
                for url in HEALTH:
                    try:
                        with urllib.request.urlopen(url, timeout=30) as response:
                            if response.status != 200: raise Stop('Render live, but application health failed.')
                            if 'webhooks' in url and json.load(response).get('git_sha') != sha:
                                raise Stop('Webhook health SHA differs from expected release.')
                    except urllib.error.URLError:
                        raise Stop('Render live, but health check unavailable; deployment not fully verified.') from None
                print(f'DEPLOYED AND HEALTHY: {sha} on all four existing services.'); return
            if time.monotonic() >= until:
                raise Stop(f'PUSHED, RENDER UNCONFIRMED: timeout for {sha}. Rerun -VerifyOnly; no duplicate deploy needed.')
            time.sleep(10)


def deploy(root, manifest_path, mode='normal', dry_run=False, unverified=False,
           expected_origin=None, validator=validate, render=None):
    git = Git(root); verify_repository(git, expected_origin)
    remote = fetch(git); head = git.text('rev-parse', 'HEAD')
    m = read_manifest(manifest_path, mode)
    selected = selected_bytes(root, m)
    verify_attributes(git, selected)
    if not selected:
        if head != remote: raise Stop('Empty manifest but local history differs. Inspect git log main...origin/main.')
        print('NOTHING APPROVED TO DEPLOY. Unfinished work remains untouched.'); return 'NOTHING'
    git.run('cat-file', '-e', m['base']+'^{commit}')
    if remote != m['base']:
        # Idempotent invocation after this exact manifest was successfully pushed.
        if head == remote and git.text('rev-parse', 'HEAD^') == m['base']:
            retry = True
        else:
            raise Stop('Remote branch advanced or manifest base is stale. Review/reconcile incoming commits, '
                       'then re-prepare. No automatic merge, rebase or overwrite.')
    else:
        retry = head != remote
    if retry and git.text('rev-parse', 'HEAD^') != m['base']:
        raise Stop('Non-fast-forward/unapproved local history. Inspect git log --left-right main...origin/main.')
    print('EXACT DEPLOYMENT FILES:', flush=True)
    for name, data in selected.items(): print(('  DELETE ' if data is None else '  ')+name, flush=True)
    if not dry_run and not unverified:
        render = render or Render()
        if isinstance(render, Render) and not render.token:
            print('Render API credentials unavailable in this terminal. Git push will trigger existing '
                  'auto-deploy; final result will be UNVERIFIED (exit 2), not deployment success.', flush=True)
            unverified = True
        else:
            render.preflight()
    with tempfile.TemporaryDirectory(prefix='sports-cave-deploy-') as scratch:
        temp = Path(scratch); candidate = temp/'candidate'; candidate.mkdir()
        private_index = temp/'index'
        staged = Git(root, {'GIT_INDEX_FILE': str(private_index)})
        staged.run('read-tree', m['base'])
        for name, data in selected.items():
            if data is None:
                staged.run('update-index', '--force-remove', '--', name)
            else:
                existing = staged.run('ls-files', '-s', '--', name).split()
                mode_bits = existing[0].decode() if existing else '100644'
                if mode_bits not in ('100644', '100755'): raise Stop(f'Symlink/submodule refused: {name}')
                # Apply the same committed .gitattributes/clean rules as git add,
                # while retaining the user's exact working bytes and manifest hashes.
                oid = staged.run('hash-object', '-w', '--path='+name, '--stdin', input=data).decode().strip()
                staged.run('update-index', '--add', '--cacheinfo', mode_bits, oid, name)
        tree = staged.text('write-tree')
        if retry and tree != git.text('rev-parse', 'HEAD^{tree}'):
            raise Stop('Existing local commit includes changes outside this manifest. No push.')
        if tree == git.text('rev-parse', m['base']+'^{tree}'):
            print('NOTHING TO DEPLOY: selected contents already committed.'); return 'NOTHING'
        export_tree(git, tree, candidate)
        validator(candidate, selected, m)
        staged.run('-c', 'core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol',
                   'diff', '--cached', '--check', m['base'])
        if dry_run:
            print('DRY RUN PASSED: exact candidate tested; real index, branch and working files unchanged.'); return 'DRY_RUN'
        # Fence concurrent edits and remote advances after potentially lengthy tests.
        if selected_bytes(root, m) != selected: raise Stop('Selected source changed during checks.')
        verify_attributes(git, selected)
        if fetch(git) != remote or git.text('rev-parse', 'HEAD') != head:
            raise Stop('Git history changed during validation; rerun after review.')
        if git.run('diff', '--cached', '--name-only'):
            raise Stop('Another task staged work during validation; index preserved, deployment stopped.')
        if not retry:
            index = Path(git.text('rev-parse', '--git-path', 'index'))
            if not index.is_absolute(): index = root/index
            lock = Path(str(index)+'.lock')
            # Standard Git index lock prevents concurrent staging from being lost.
            try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError: raise Stop('Git index is busy. Another task may be staging; retry when it finishes.') from None
            try:
                if git.run('diff', '--cached', '--name-only'):
                    raise Stop('Another task staged work. Preserved without committing.')
                committing = Git(root, {'GIT_INDEX_FILE': str(private_index), 'GIT_WORK_TREE': str(candidate)})
                committing.run('commit', '-m', m['message'])
                head = git.text('rev-parse', 'HEAD')
                staged.run('read-tree', head)
                with os.fdopen(fd, 'wb') as handle:
                    fd = None
                    handle.write(private_index.read_bytes())
                os.replace(lock, index) # Index only; working files are never written.
                if git.text('rev-parse', 'HEAD^{tree}') != tree:
                    raise Stop('A commit hook changed the candidate. Commit retained locally; review before any push.')
            finally:
                if fd is not None: os.close(fd)
                if lock.exists(): lock.unlink()
        if head != remote:
            git.run('push', 'origin', 'HEAD:refs/heads/main')
            if fetch(git) != head: raise Stop('Push verification mismatch; inspect GitHub before continuing.')
        print(f'PUSHED: {head}. This is not yet Render deployment success.', flush=True)
    if unverified:
        print('RENDER UNVERIFIED: push-only requested. Check Render or rerun -VerifyOnly.'); return 'UNVERIFIED'
    render.wait(head)
    return 'LIVE'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=('normal', 'full'), default='normal')
    p.add_argument('--manifest'); p.add_argument('--dry-run', action='store_true')
    p.add_argument('--prepare', action='store_true'); p.add_argument('--path', action='append', default=[])
    p.add_argument('--test', action='append', default=[]); p.add_argument('--import-module', action='append', default=[])
    p.add_argument('--message', default='Deploy approved Sports Cave OS updates')
    p.add_argument('--verify-only', action='store_true')
    p.add_argument('--include-completed-inbox', action='store_true')
    p.add_argument('--push-without-render-verification', action='store_true')
    args = p.parse_args(); root = Path(__file__).resolve().parents[1]
    try:
        if any(os.getenv(k) for k in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR')):
            raise Stop('Unset custom Git directory/index overrides before running deployment.')
        manifest = root / (args.manifest or f'deploy/{args.mode}.json')
        if args.verify_only:
            git = Git(root); verify_repository(git); remote = fetch(git)
            if git.text('rev-parse', 'HEAD') != remote: raise Stop('Local/GitHub SHAs differ; inspect before verification.')
            render = Render(); render.preflight(); render.wait(remote); return 0
        if args.prepare:
            prepare(root, manifest, args.mode, args.path, args.test, args.import_module,
                    args.message, completed_inbox=args.include_completed_inbox); return 0
        if args.include_completed_inbox or args.path or args.test or args.import_module:
            raise Stop('Selection/Inbox approval options are only valid with -Prepare. Deploy the reviewed manifest afterward.')
        result = deploy(root, manifest, args.mode, args.dry_run, args.push_without_render_verification)
        return 2 if result == 'UNVERIFIED' else 0
    except (Stop, OSError, ValueError, KeyError, TypeError) as exc:
        print(f'DEPLOYMENT STOPPED: {exc}', file=sys.stderr); return 1


if __name__ == '__main__':
    raise SystemExit(main())
