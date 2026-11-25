"""Loopback-only component workbench. Synthetic models; no application server."""
import json
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def fixture():
    from tests.test_support_email_v2 import WorkspaceTests
    case = WorkspaceTests()
    case.setUp()
    try:
        case.open()
        result = case.w.model()
        result.update(initial_load_pending=False, discovery_pending=False, history_pending=False,
                      read_pending=False, live_pending=False, smtp_configured=False, sync_health={},
                      body_pending=None, read_mark_pending=None, body_completion=None)
        return result
    finally:
        case.doCleanups()


def main():
    model = json.dumps(fixture(), default=str).encode()
    baseline = subprocess.check_output(['git','show','58d8446f:components/support_email/mail.js'], cwd=ROOT)
    assets = {
        '/results': ('text/html', (ROOT.parent/'.studio/runtime/20261125-email-speed-report.html').read_bytes()) if (ROOT.parent/'.studio/runtime/20261125-email-speed-report.html').is_file() else ('text/plain',b'Benchmark results not yet generated'),
        '/': ('text/html', b'<!doctype html><title>Email Phase 2 workbench</title><h1>Email Phase 2: synthetic component benchmark</h1><p>No live mailbox, database, credentials or SMTP. 100 cold and 100 cached selections per version; simulated 80 ms host acknowledgement.</p><button id="before">Run baseline</button> <button id="after">Run Phase 2</button><p id="status">Ready</p><pre id="results"></pre><iframe id="component" style="width:100%;height:680px;border:1px solid #ddd"></iframe><script src="/bench.js"></script>'),
        '/fixture.json': ('application/json', model),
        '/bench.js': ('text/javascript', Path(__file__).with_name('email_phase2_workbench.js').read_bytes()),
    }
    for version in ('before','after'):
        for name in ('index.html','style.css','draft_journal.js','mail_tools.js','mail.js'):
            data = baseline if version == 'before' and name == 'mail.js' else (ROOT/'components/support_email'/name).read_bytes()
            assets[f'/{version}/{name}'] = (
                'text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript', data)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            resource = assets.get(self.path.split('?')[0])
            if resource is None:
                self.send_error(404)
                return
            kind, data = resource
            self.send_response(200)
            self.send_header('Content-Type', kind+'; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    print('http://127.0.0.1:'+str(server.server_port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
