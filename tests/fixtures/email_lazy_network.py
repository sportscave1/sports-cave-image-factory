"""Loopback-only real Workspace/component harness; fabricated mail, all live I/O blocked.

Run with --port and optionally --source for the captured released baseline.
Never imports the application server or uses a production configuration.
"""
import argparse
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parents[2]
args = argparse.ArgumentParser()
args.add_argument('--port', type=int, default=8876)
args.add_argument('--source', type=Path, default=ROOT)
args = args.parse_args()
sys.path[:0] = [str(args.source), str(ROOT)]
from tests.test_support_email_v2 import WorkspaceTests
from support_email_workspace import reference_key
from support_email_provider import MailboxError


class Harness:
    def reset(self, count):
        if hasattr(self, 'fixture'):
            self.fixture.doCleanups()
        self.fixture = f = WorkspaceTests()
        f.setUp()
        base = deepcopy(f.imap.messages[0])
        f.imap.messages = []
        for i in range(count + 1):
            m = deepcopy(base)
            m.update(uid=str(i + 1), message_id=f'<network-{i}@example.test>',
                     references=('<network-0@example.test>',) if 0 < i < count else (),
                     subject='Long synthetic conversation' if i < count else 'Other conversation',
                     unread=False, flags=('\\Seen',), snippet=f'Synthetic preview {i}')
            f.imap.messages.append(m)
        def body(m):
            f.imap.calls.append(('body', m['uid']))
            time.sleep(.04)
            if self.fail:
                self.fail = False
                raise MailboxError('Synthetic body unavailable')
            text = 'Synthetic paragraph about a frame and its delivery. ' * 1300
            return dict(text=text, html=f'<h2>Message {m["uid"]}</h2><p>{text}</p>'
                        '<img src="https://private.example.test/pixel">', inline_images={},
                        attachments=[dict(section='3', filename='photo.jpg', content_type='image/jpeg', encoded_size=1048576)], warnings=[])
        self.fail = False
        f.imap.read_message = body
        f.state['cache'].clear()
        f.state.update(selected=None, conversation=[], active_message=None)
        f.w.load(force=True, previews=False)
        f.imap.calls.clear()
        return f.w.model()


harness = Harness()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, data, content_type='application/json'):
        payload = data if isinstance(data, bytes) else json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', content_type + '; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == '/reset':
            return self.send(harness.reset(int(parse_qs(url.query).get('count', ['24'])[0])))
        if url.path == '/trace':
            f = harness.fixture
            return self.send(dict(calls=f.imap.calls, cache_bytes=f.w.bodies.data['bytes']))
        if url.path == '/fail':
            harness.fail = True
            return self.send({})
        if url.path in ['/mail.js', '/style.css', '/draft_journal.js']:
            file = args.source / 'components/support_email' / url.path[1:]
            if not file.exists():
                file = ROOT / 'components/support_email' / url.path[1:]
            return self.send(file.read_bytes(), 'text/javascript' if file.suffix == '.js' else 'text/css')
        self.send(b'''<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/style.css"></head>
<body><div id="mail"></div><script src="/draft_journal.js"></script><script src="/mail.js"></script>
<script>window.addEventListener('message',async e=>{
 if(e.data.type==='streamlit:setComponentValue'){
  const r=await fetch('/event',{method:'POST',body:JSON.stringify(e.data.value)});
  window.currentModel=await r.json(); window.postMessage({type:'streamlit:render',args:{model:currentModel}},'*');
 }
});window.loadFixture=async n=>{currentModel=await (await fetch('/reset?count='+n)).json();
window.postMessage({type:'streamlit:render',args:{model:currentModel}},'*');};</script></body></html>''', 'text/html')

    def do_POST(self):
        event = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if event.get('action') not in {'open_thread', 'open_message', 'resolve_thread', 'load_visible_body',
                                     'load_conversation_body', 'collapse_message', 'mark_visible_read', 'compose', 'close_composer'}:
            raise AssertionError('Harness action is not read-only')
        harness.fixture.w.handle(event)
        self.send(harness.fixture.w.model())


if __name__ == '__main__':
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()
