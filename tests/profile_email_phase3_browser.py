"""Loopback static component only. All data synthetic; no running app preview."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tests.profile_email_phase2_browser import fixture

ROOT = Path(__file__).resolve().parents[1]


def main():
    page = '''<!doctype html><html lang="en"><meta charset="utf-8"><title>Phase 3 inbox checks</title>
    <style>body{font:14px Segoe UI,Arial;margin:16px;background:#edf2ef;color:#223b32}h1{font-size:21px;margin:6px 0}
    button{padding:7px 10px;margin:3px;border:1px solid #b4c6bc;border-radius:5px;background:white;color:#254b3a}
    .controls{display:flex;gap:6px;flex-wrap:wrap}p{margin:7px 0}iframe{display:block;background:white;height:720px;border:1px solid #bdc9c1;max-width:100%;margin-top:10px}</style>
    <h1>Professional inbox · Phase 3 local candidate</h1><p>Synthetic fixture · No live mailbox, customer data, SMTP or external actions</p>
    <div class="controls"><button data-state="connected">Connected</button><button data-state="syncing">Syncing</button>
    <button data-state="reconnecting">Reconnecting</button><button data-state="attention">Needs attention</button>
    <button id="desktop">Desktop</button><button id="mobile">Mobile 375</button><button id="refresh">Schedule refresh</button>
    <button id="badge">Confirm automatic reply</button><button id="loading">Loading message</button><button id="loaded">Show message</button></div>
    <p id="activity"></p><p><span id="size">Desktop component viewport</span> · <span id="refresh-status">Ready</span></p>
    <iframe id="component" title="Synthetic professional inbox" style="width:100%"></iframe><script src="/workbench.js"></script></html>'''
    assets = {'/': ('text/html', page.encode()),
              '/fixture.json': ('application/json', json.dumps(fixture(), default=str).encode()),
              '/workbench.js': ('text/javascript', (ROOT/'tests/email_phase3_workbench.js').read_bytes())}
    files = {'/workbench.js': ROOT/'tests/email_phase3_workbench.js'}
    for name in ('index.html', 'style.css', 'draft_journal.js', 'mail_tools.js', 'mail.js'):
        files['/component/'+name] = ROOT/'components/support_email'/name
        assets['/component/'+name] = ('text/html' if name.endswith('.html') else 'text/css' if name.endswith('.css') else 'text/javascript',
                                     (ROOT/'components/support_email'/name).read_bytes())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            resource = assets.get(self.path.split('?')[0])
            if resource is None:
                self.send_error(404)
                return
            kind, data = resource
            if self.path.split('?')[0] in files:
                data = files[self.path.split('?')[0]].read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', kind+'; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    print('http://127.0.0.1:'+str(server.server_port), flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
