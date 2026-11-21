"""Real Edge against synthetic repair APIs; no accounts, PSDs or production."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
from playwright.sync_api import sync_playwright

def test_one_click_repair_progress_and_ready_link():
    state={'status':'Repair','requests':[]}
    html=Path('components/auto_editions/status.html').read_bytes()
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html)
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/api/auto-editions/repair':
                state['requests'].append(data);state['status']='Repairing';body={'ok':True}
            else:
                body={'rows':[dict(status=state['status'],reason='Synthetic diagnosis',checkpoint='Preparing',actions=['repair'] if state['status']=='Repair' else [],repair=dict(state='Waiting'))]}
            self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(json.dumps(body).encode())
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    output=Path('output/edition-repair');output.mkdir(parents=True,exist_ok=True)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='msedge',headless=True)
            try:
                for width in (1440,390):
                    state['status']='Repair';state['requests']=[]
                    page=browser.new_page(viewport=dict(width=width,height=900));errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(f'http://127.0.0.1:{server.server_port}/auto-editions/status?product_gid=gid%3A%2F%2Fshopify%2FProduct%2F987&allocation_id=42&repair=1')
                    page.wait_for_function("document.querySelector('#stage').textContent==='Repairing'")
                    assert len(state['requests'])==1 and state['requests'][0]['allocation_id']==42
                    assert 'repair=1' not in page.url
                    page.reload();page.wait_for_function("document.querySelector('#stage').textContent==='Repairing'")
                    assert len(state['requests'])==1
                    page.screenshot(path=str(output/f'repairing-{width}.png'),full_page=True)
                    state['status']='Cloud Ready';page.get_by_role('button',name='Refresh',exact=True).click()
                    page.get_by_role('link',name='Download JPG',exact=True).wait_for()
                    assert page.get_by_role('link',name='Download JPG',exact=True).get_attribute('href').endswith('allocation_id=42')
                    assert errors==[]
                    page.close()
            finally:browser.close()
    finally:server.shutdown();server.server_close();thread.join()
