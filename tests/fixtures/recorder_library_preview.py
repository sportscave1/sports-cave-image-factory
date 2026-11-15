"""Manual local UI fixture. Real panel assets, synthetic relay, no native input.

Run from the repository: python -B tests/fixtures/recorder_library_preview.py
This validates presentation only; adapter tests cover durable helper behavior.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Condition
from urllib.parse import urlsplit, parse_qs
import json
import time

ROOT = Path(__file__).resolve().parents[2]
changed = Condition()
seq = 1
connected = True
receipts = {}
state = dict(protocol=3, mode='idle', message='Windows recorder ready.', tasks=[
    dict(id='00000000-0000-4000-8000-000000000001', name='Combined Edge and Notepad',
         format='sports-cave.desktop', revision='synthetic', playback_available=True,
         updated_at=1792540800000, result='completed', steps=4, inputs=[]),
    dict(id='00000000-0000-4000-8000-000000000002', name='Product prompt copy',
         format='sports-cave.desktop', revision='synthetic', playback_available=True,
         updated_at=1792544400000, result='completed', steps=2, inputs=[]),
    dict(id='00000000-0000-4000-8000-000000000003', name='Older browser example',
         revision='synthetic', updated_at=1792454400000, steps=3, inputs=[])],
    desktop_capabilities=dict(format='sports-cave.desktop', version=1, action_versions=[2],
                              library_management=True, popup_reopen=True))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, content_type='application/json'):
        wire = json.dumps(body).encode() if content_type == 'application/json' else body
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(wire)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            self.wfile.write(wire)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        global seq, connected
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        if url.path.startswith('/__fixture/'):
            with changed:
                mode = url.path.rsplit('/', 1)[-1]
                connected = mode != 'offline'
                state.update(mode='idle' if mode == 'offline' else mode,
                             active_task_id=state['tasks'][0]['id'] if mode != 'idle' else None,
                             message='Continue in the Windows popup.' if mode != 'idle' else 'Windows recorder ready.')
                seq += 1
                changed.notify_all()
            return self.reply({'synthetic': True})
        if url.path.endswith('/state'):
            with changed:
                if query.get('after') == [str(seq)] and query.get('wait') != ['0']:
                    changed.wait(20)
                return self.reply(dict(compact=1, devices=[dict(id='synthetic-pc', name='Windows PC',
                    connected=connected, seq=seq, last_seen=time.time(), state=state)]))
        if url.path.endswith('/receipt'):
            return self.reply(receipts[query['id'][0]])
        asset = url.path.rsplit('/', 1)[-1]
        if asset in {'panel.js', 'panel.css'}:
            return self.reply((ROOT/'task_recorder'/asset).read_bytes(),
                              'text/javascript' if asset.endswith('.js') else 'text/css')
        return self.reply((ROOT/'task_recorder/panel.html').read_bytes(), 'text/html; charset=utf-8')

    def do_POST(self):
        global seq
        command = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        with changed:
            kind, payload = command['kind'], command['payload']
            result = dict(message='Windows popup opened (synthetic presentation check).')
            if kind == 'rename':
                next(t for t in state['tasks'] if t['id'] == payload['id'])['name'] = payload['name']
                result['name'] = payload['name']
            elif kind == 'delete':
                state['tasks'] = [t for t in state['tasks'] if t['id'] != payload['id']]
            elif kind == 'play':
                state.update(mode='starting', active_task_id=payload['id'], message='Press Play in the Windows popup.')
            receipts[command['id']] = dict(status='applied', receipt=result)
            seq += 1
            changed.notify_all()
            self.reply(receipts[command['id']])


if __name__ == '__main__':
    print('Synthetic UI only: http://127.0.0.1:19021/', flush=True)
    ThreadingHTTPServer(('127.0.0.1', 19021), Handler).serve_forever()
