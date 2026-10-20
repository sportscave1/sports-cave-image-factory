"""Loopback-only synthetic Product Uploads interaction fixture; no app data."""
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HTML = """<!doctype html><title>Isolated Product Uploads fixture</title>
<h1>Product Uploads fixture</h1>
<label>Choose PSD <input type=file id=psd></label><p id=source>No source</p>
<label>Product name <input id=product></label>
<label for=category>Category</label><select id=category><option value=sport>Sport</option><option value=art>Art</option></select>
<label>Approved <input type=checkbox></label>
<button data-testid=stBaseButton-primary id=generate disabled>Generate Mockups</button>
<p id=generated></p><div id=output></div>
<script>
const psd=document.querySelector('#psd'), source=document.querySelector('#source'),
generate=document.querySelector('#generate'), generated=document.querySelector('#generated'), output=document.querySelector('#output');
for(let i=0;i<127;i++){const b=document.createElement('button');b.dataset.testid='stBaseButton-primary';b.textContent='Unrelated '+i;document.body.append(b);}
psd.onchange=()=>{source.textContent=psd.files[0].name;generate.disabled=false};
generate.onclick=()=>{
  generated.textContent='Mockups generated: 1';
  setTimeout(()=>{
    const f=document.createElement('iframe');f.title='Black frame prompt';
    f.srcdoc=`<button data-testid="stBaseButton-primary" onclick="navigator.clipboard.writeText('Synthetic black frame prompt').then(()=>document.querySelector('p').textContent='Copied')">Copy Black Frame Prompt</button><p></p><label>Note <input></label>`;
    output.replaceChildren(f);
  },450);
};
</script>"""

def fixture_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=HTML.encode()
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',18970),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return server,thread
