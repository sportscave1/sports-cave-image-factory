"""Credential-free Phase 8 simulator. Real post-save UI; simulated chat/store.

No provider imports, outbound HTTP, uploads, generation, PSD or edition mutations.
The retained Phase 7 receipt/prompt is read-only. Only local evidence is written.
"""
import argparse
import hashlib
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[2]
CONVERSATION = '6ae2d62d-1338-83ec-8619-6ea3635a7fa0'
KEY = '195312b8-dc17-49a1-a34e-3ed7c09a2073'


class Scenario:
    def __init__(self, evidence, output):
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.prompt = (Path(evidence) / 'prompt.txt').read_text(encoding='utf-8').replace('\r\n', '\n')
        self.receipt = json.loads((Path(evidence) / 'receipt.json').read_text(encoding='utf-8'))['receipt']
        if self.receipt['failures'] or len(self.receipt['successes']) != 8:
            raise ValueError('Complete retained save receipt required')
        for item in self.receipt['successes']:
            if item['metadata']['id'] not in self.prompt or item['metadata']['name'] not in self.prompt:
                raise ValueError('Prompt/receipt mismatch')
        if self.receipt['save_token'] not in self.prompt or '\nUpload to Draft\n' not in self.prompt:
            raise ValueError('Draft save identity missing')
        self.digest = hashlib.sha256(self.prompt.encode()).hexdigest()
        self.row = dict(id=KEY, mode='DRAFT', name='Retained Phase 7 local evidence', state='Ready',
                        basic_validated=True, saved_source_version=self.digest)

    def validate(self, data):
        if data.get('conversation') != CONVERSATION:
            raise ValueError('Wrong conversation; nothing submitted')
        if data.get('ready') is not True:
            raise ValueError('Composer not ready; nothing submitted')
        if data.get('prompt', '').replace('\r\n', '\n') != self.prompt:
            raise ValueError('Complete saved prompt mismatch; nothing submitted')

    def recover_acknowledgement(self, conversation, prompt_sha256):
        """Read-only reconciliation. Missing or inconsistent proof never permits resend."""
        if conversation != CONVERSATION or prompt_sha256 != self.digest:
            raise ValueError('Wrong conversation or prompt; recovery refused')
        try:
            attempt = json.loads((self.output/'attempt.json').read_text(encoding='utf-8'))
            result = json.loads((self.output/'result.json').read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise ValueError('Outcome unknown; do not resend') from error
        for record, state in ((attempt, 'attempted'), (result, 'completed')):
            if not isinstance(record, dict) or any((
                record.get('conversation') != conversation,
                record.get('prompt_sha256') != prompt_sha256,
                record.get('state') != state,
                record.get('simulated') is not True,
            )):
                raise ValueError('Inconsistent acknowledgement; do not resend')
        if (type(result.get('submissions')) is not int or result['submissions'] != 1
                or result.get('psd_attached') is not False
                or type(result.get('edition_changes')) is not int or result['edition_changes'] != 0
                or type(result.get('production_jobs')) is not int or result['production_jobs'] != 0
                or result.get('draft_id') != 'local-draft-'+KEY
                or result.get('business_outcome') != 'SIMULATED ONLY — no Shopify product created'):
            raise ValueError('Unsafe or ambiguous result; do not resend')
        return result

    def submit(self, data):
        self.validate(data)
        # Durable write-before-effect; unknown result/restart never authorizes resending.
        attempt = dict(conversation=CONVERSATION, prompt_sha256=self.digest, state='attempted', simulated=True)
        with (self.output / 'attempt.json').open('x', encoding='utf-8') as stream:
            json.dump(attempt, stream)
            stream.flush()
            import os
            os.fsync(stream.fileno())
        result = dict(attempt, state='completed', draft_id='local-draft-'+KEY,
                      business_outcome='SIMULATED ONLY — no Shopify product created',
                      submissions=1, psd_attached=False, edition_changes=0, production_jobs=0)
        (self.output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        return result


def handler(scenario):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, data, mime='application/json', status=200):
            if not isinstance(data, bytes):
                data = json.dumps(data).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime+'; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'self'")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == '/api/product-uploads/state':
                return self.reply(dict(enabled=True, upload=scenario.row))
            if parsed.path == '/api/product-uploads/mapping-status':
                if parse_qs(parsed.query).get('id') != [KEY]:
                    return self.reply(dict(error='Wrong upload'), status=400)
                with (scenario.output/'mapping-requests.jsonl').open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(dict(id=KEY, method='GET', no_writes=True))+'\n')
                return self.reply(dict(mapping=dict(state='Available in local Edition Ops',
                    reason='Simulator only. No PSD attachment or edition changes.', url='/?page=edition_ops')))
            assets = {'/browser-identity.js': 'windows-screen-recorder/edge-adapter/browser-identity.js',
                      '/app.js': 'components/product_uploads/app.js',
                      '/mapping.js': 'components/product_uploads/mapping.js'}
            if parsed.path in assets:
                return self.reply((ROOT/assets[parsed.path]).read_bytes(), 'text/javascript')
            if parsed.path == '/chat':
                body = '''<!doctype html><meta charset="utf-8"><title>Local Phase 8 chat simulator</title>
<style>body{font:18px system-ui;margin:30px}textarea{width:95%;height:230px}button,a{margin:10px;padding:10px}pre{white-space:pre-wrap}</style>
<h1>Local follow-up simulator</h1><p>No ChatGPT or Shopify connection. Existing conversation: CONVERSATION</p>
<p>Prior image generation is retained, never repeated. Paste the retained post-save prompt below.</p>
<textarea aria-label="Local follow-up prompt" id="prompt"></textarea><p id="ready">Waiting for complete prompt</p>
<button id="send" disabled>Submit once to local simulator</button><textarea id="result" readonly aria-label="Local submission result"></textarea>
<a href="/?page=product_uploads">Return to post-save Mapping</a>
<script>const prompt=document.getElementById('prompt'),send=document.getElementById('send');let pending=false;
const payload=()=>({conversation:'CONVERSATION',ready:true,prompt:prompt.value});
prompt.oninput=async()=>{send.disabled=true;const r=await fetch('/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});const d=await r.json();document.getElementById('ready').textContent=r.ok?'Ready — complete prompt verified':d.error;send.disabled=!r.ok||pending};
send.onclick=async()=>{if(pending)return;pending=true;send.disabled=true;try{const r=await fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload())});document.getElementById('result').value=JSON.stringify(await r.json(),null,2)}catch(e){document.getElementById('result').value='Outcome unknown; do not resend'} };</script>'''.replace('CONVERSATION', CONVERSATION)
                body += '<script src="/browser-identity.js"></script>'
                return self.reply(body.encode(), 'text/html')
            if parsed.path != '/':
                return self.reply(dict(error='Unknown route'), status=404)
            if parse_qs(parsed.query).get('page') == ['edition_ops']:
                body = '<!doctype html><title>Local Phase 8 Edition Ops</title><h1>Edition Ops — local simulator</h1><p>Mapping destination verified. No PSD attached. No edition changes. No jobs.</p><a href="/?page=product_uploads">Return to retained post-save page</a>'
            else:
                body = (ROOT/'components/product_uploads/index.html').read_text(encoding='utf-8')
                body = body.replace('<main>', '<main><p><b>LOCAL PHASE 8 SIMULATOR</b> — retained save evidence; no cloud writes.</p><a href="/chat">Existing local follow-up conversation</a>')
            body += '<script src="/browser-identity.js"></script>'
            return self.reply(body.encode(), 'text/html')

        def do_POST(self):
            if self.headers.get('Origin') != 'http://127.0.0.1:18963':
                return self.reply(dict(error='Local origin required'), status=403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1048576:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(length))
                if self.path == '/api/product-uploads/prompt':
                    if data.get('id') != KEY or data.get('source_version') != scenario.digest:
                        raise ValueError('Wrong saved revision')
                    return self.reply(dict(prompt=scenario.prompt))
                if self.path == '/api/product-uploads/copied':
                    return self.reply(dict(upload=scenario.row))
                if self.path == '/validate':
                    scenario.validate(data)
                    if (scenario.output/'attempt.json').exists():
                        raise ValueError('Submission already attempted; do not resend')
                    return self.reply(dict(ready=True))
                if self.path == '/submit':
                    return self.reply(scenario.submit(data))
                raise ValueError('Operation disabled in local simulator')
            except (ValueError, FileExistsError) as error:
                return self.reply(dict(error=str(error)), status=409)
    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    ThreadingHTTPServer(('127.0.0.1', 18963), handler(Scenario(args.evidence, args.output))).serve_forever()
