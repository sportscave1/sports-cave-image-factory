"""Read-only Git inspection; writes a review packet, never stages or deploys."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs/email-inbox-outlook-v2d-evidence'
BASE = ROOT / 'tmp/email-v2d-before'
PHASE = ['support_email_tools.py', 'support_email_provider.py', 'support_email_reads.py',
         'support_email_store.py', 'support_email_durable.py', 'support_email_workspace.py',
         'components/support_email/mail_tools.js', 'components/support_email/mail.js',
         'components/support_email/style.css', 'components/support_email/index.html']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, encoding='utf-8')


patch = ''
for name in PHASE:
    old = (BASE/name).read_text(encoding='utf-8').splitlines(keepends=True) if (BASE/name).exists() else []
    new = (ROOT/name).read_text(encoding='utf-8').splitlines(keepends=True)
    patch += ''.join(difflib.unified_diff(old, new, fromfile='a/'+name if old else '/dev/null', tofile='b/'+name))
(OUT/'v2d-only.patch').write_text(patch, encoding='utf-8')

auth = git('diff', '--', 'app.py')
header, *hunks = auth.split('\n@@ ')
selected = [h for h in hunks if 'sc-email-draft-v2:' in h]
assert len(selected) == 1, 'Review shared authentication hunks before packaging'
(OUT/'email-auth-cleanup.patch').write_text(header+'\n@@ '+selected[0], encoding='utf-8')
(OUT/'email-readiness-route.patch').write_text(git('diff', '--', 'sports_cave_server.py'), encoding='utf-8')

files = sorted([*ROOT.glob('support_email*.py'), *(ROOT/'components/support_email').glob('*')])
manifest = {
    'status': 'Candidate only; user approval and staging outstanding. Not a deployment instruction.',
    'head': git('rev-parse', 'HEAD').strip(),
    'scope': 'Coherent local Email A-D source; shared app/server integration is patch-only.',
    'phase_v2d_files': PHASE,
    'email_source': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': digest(p)} for p in files if p.is_file()],
    'shared_file_conflict_detection_only': [{'path': p, 'sha256': digest(ROOT/p)} for p in ['app.py', 'sports_cave_server.py']],
    'review_patches': [{'path': p, 'sha256': digest(OUT/p)} for p in ['v2d-only.patch', 'email-auth-cleanup.patch', 'email-readiness-route.patch']],
    'existing_migrations_to_verify_not_apply': [
        '20260927020406_customer_support_workflow.sql', '20260927025319_customer_support_email_settings.sql',
        '20260930055619_support_email_inbox_snapshot.sql', '20261006063028_support_email_durable_delivery.sql'],
    'deployment_manifest': 'Current deploy/full.json is unrelated/unfinished and must not be used without separate review. Include new support_email_tools.py and components/support_email/mail_tools.js in any approved release.',
}
(OUT/'candidate-source-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
(OUT/'final-status.txt').write_text(git('status', '--short'), encoding='utf-8')
print(f'Candidate packet: {len(manifest["email_source"])} Email files; {len(PHASE)} V2D production files; no Git mutations.')
