"""Generate offline browser inputs and reproducible baseline sources."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from support_email_render import sanitize_received_html, reader_document
from tests.test_support_email_v2 import WorkspaceTests

BASE = '59b609728b182c6c997f02ed0a8786fff0483095'
target = ROOT / 'tmp/conversation-before'
target.mkdir(parents=True, exist_ok=True)
for path in ['components/support_email/mail.js', 'support_email_render.py']:
    (target / Path(path).name).write_bytes(subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT))
spec = importlib.util.spec_from_file_location('before_reader', target / 'support_email_render.py')
before = importlib.util.module_from_spec(spec)
spec.loader.exec_module(before)
markup = '<div style="font-size:20px;line-height:1px;height:12px">' + ''.join(
    '<p style="margin-bottom:-15px">Readable line %d with quoted replies and signature</p>' % i
    for i in range(45)) + '</div><table width="1800"><tr><td>' + ('https://example.test/very-long-link' * 15) + '</td><td>Table signature</td></tr></table><img src="https://private.example.test/pixel"><blockquote>Quoted HTML reply</blockquote>'
(ROOT / 'tmp/conversation-documents.json').write_text(json.dumps({
    'before': before.reader_document(before.sanitize_received_html(markup)),
    'after': reader_document(sanitize_received_html(markup))}), encoding='utf-8')
fixture = WorkspaceTests()
fixture.setUp()
try:
    (ROOT / 'tmp/conversation-model.json').write_text(json.dumps(fixture.w.model()), encoding='utf-8')
finally:
    fixture.doCleanups()
