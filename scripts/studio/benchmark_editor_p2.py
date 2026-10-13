"""Actual editor module in installed Edge; source-only diagnostic, no draft writes."""
import json,threading,sys,time,statistics,math,subprocess
from pathlib import Path
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2];phase=sys.argv[1]
baseline_editor=subprocess.check_output(['git','-C',str(root),'show','c646cf0a6c69a71a5b4ee16a4c3778805761131e:scripts/studio/ui/editor.js']) if phase=='before-native' else None
source=(root/'components/sports_cave_top_bar/index.html').read_text(encoding='utf-8')
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def do_GET(self):
        if self.path=='/favicon.ico':self.send_response(204);self.end_headers();return
        if self.path=='/':
            html='''<style>body{margin:0}#editor-panel{width:600px}.code-wrap{height:450px}</style><section id="editor-panel"></section><script type="module">import {mount} from '/editor.js';window.writes=0;window.bytes=0;const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){writes++;bytes+=v.length;return set.call(this,k,v)};const text=SOURCE;await mount(document.getElementById('editor-panel'),async (_,d)=>d.action==='editor-files'?{files:[{path:'header.html',available:true}]}:{path:'header.html',source:text,history:[],hash:'fixture',revision:0},async()=>{},{recoveryKey:'diagnostic'});window.ready=true;</script>'''.replace('SOURCE',json.dumps(source).replace('</', '<\\/'))
            data=html.encode();kind='text/html'
        else:
            data=baseline_editor if self.path=='/editor.js' and baseline_editor else (root/'scripts/studio/ui'/self.path.lstrip('/')).read_bytes();kind='text/javascript' if self.path.endswith('.js') else 'text/css'
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='msedge',headless=True);page=browser.new_page(viewport={'width':1100,'height':900});page.goto('http://127.0.0.1:'+str(server.server_port));page.wait_for_function('window.ready')
    result=page.evaluate('''async()=>{const f=document.getElementById('ed-source'),base=f.value,samples=[];for(let i=0;i<200;i++){const t=performance.now();f.setRangeText('x',f.value.length,f.value.length,'end');f.dispatchEvent(new Event('input',{bubbles:true}));samples.push(performance.now()-t);}await new Promise(r=>setTimeout(r,600));return {samples,chars:base.length,heap:performance.memory.usedJSHeapSize,writes,bytes,valueCorrect:f.value===base+'x'.repeat(200)};}''')
    cdp=browser.new_browser_cdp_session();idle=[]
    import psutil
    for _ in range(5):
        a=cdp.send('SystemInfo.getProcessInfo')['processInfo'];page.wait_for_timeout(2000);b=cdp.send('SystemInfo.getProcessInfo')['processInfo'];old={p['id']:p['cpuTime'] for p in a}
        idle.append({'cpu_one_core_percent':sum(max(0,p['cpuTime']-old.get(p['id'],p['cpuTime'])) for p in b)*50,'rss_bytes':sum(psutil.Process(int(p['id'])).memory_info().rss for p in b if psutil.pid_exists(int(p['id'])))})
    result['idle_samples']=idle
    before=page.locator('#ed-source').input_value()
    result['field_state']=page.locator('#ed-source').evaluate('(n)=>({disabled:n.disabled,readOnly:n.readOnly,box:n.getBoundingClientRect().toJSON(),visibility:getComputedStyle(n).visibility})')
    for _ in range(10):page.locator('#ed-undo').click()
    result['undo_ten_correct']=page.locator('#ed-source').input_value()==before[:-10]
    page.context.grant_permissions(['clipboard-read','clipboard-write']);page.evaluate('(text)=>navigator.clipboard.writeText(text)',source+'\n<!-- native paste -->');page.locator('#ed-source').focus();page.locator('#ed-source').press('Control+A');start=time.perf_counter();page.locator('#ed-source').press('Control+V');page.wait_for_timeout(500);result['native_paste_ms']=(time.perf_counter()-start)*1000;result['native_paste_correct']=page.locator('#ed-source').input_value()==source+'\n<!-- native paste -->'
    try:
        start=time.perf_counter();page.locator('#ed-source').fill(source+'\n<!-- real bulk input -->',timeout=8000);result['native_bulk_ms']=(time.perf_counter()-start)*1000
    except Exception as exc:result['bulk_error']=str(exc)[-2000:]
    v=result['samples'];result['idle_median']={key:statistics.median(row[key] for row in idle) for key in idle[0]}
    result['input_handler_ms']={'median':statistics.median(v),'p95':sorted(v)[math.ceil(.95*len(v))-1]}
    (root/'docs'/('v9-p2-editor-'+phase+'.json')).write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True);browser.close()
server.shutdown()
