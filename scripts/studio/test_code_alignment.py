"""Real Edge layout regression for the existing source editor; no companion access."""
import json, threading, sys, statistics, time
from pathlib import Path
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
HTML='''<!doctype html><meta charset="utf-8"><title>V9 isolated alignment acceptance</title><link rel="stylesheet" href="/editor.css"><link rel="stylesheet" href="/workspace.css">
<style>body{margin:0;background:#191a18}.ws-dev{height:100vh!important;width:760px}#editor-panel{height:100vh!important;display:flex;flex-direction:column}#ed-code{flex:1;min-height:0}.code-wrap{flex:1!important;height:auto!important}</style>
<main class="ws-v6 ws-dev" data-mode="source"><section id="editor-panel"></section></main>
<aside style="position:fixed;left:780px;top:20px;color:white"><button id="jump">Long Python selection</button><button id="html">HTML</button><button id="css">CSS</button><button id="save">Save All (memory only)</button><pre id="metrics"></pre></aside>
<script type="module">
import * as editor from '/code-editor.js';window.editor=editor;
const sources={};for(const path of ['app.py','components/sign_in/presentation.html','components/sports_cave_top_bar/index.html','orders_page.css'])sources[path]=await (await fetch('/source/'+path)).text();
window.sources=sources;window.saved=[];let revision=0;
const request=async(_,d)=>{if(d.action==='source-open')return {path:d.path,source:sources[d.path],editable:d.path!=='app.py',complete:true,language:d.path.split('.').at(-1),revision,hash:'test-'+revision,history:[]};
if(d.action==='editor-save-all'){window.saved.push(d);revision++;for(const f of d.files)sources[f.path]=f.source;return {revision,paths:d.files.map(f=>f.path)};}throw Error(d.action);};
await editor.mount(document.querySelector('#editor-panel'),request,()=>{}, {files:Object.keys(sources).map(path=>({path,available:true})),path:'app.py'});window.ready=true;
document.querySelector('#jump').onclick=()=>editor.selectComponent('test',{path:'app.py',line:10218,end_line:10302});
document.querySelector('#html').onclick=()=>editor.selectFile('components/sign_in/presentation.html');document.querySelector('#css').onclick=()=>editor.selectFile('orders_page.css');document.querySelector('#save').onclick=()=>editor.command('save');
setInterval(()=>{document.querySelector('#metrics').textContent=JSON.stringify(Object.fromEntries(['ed-source','ed-highlight','ed-lines'].map(id=>{const e=document.getElementById(id),s=getComputedStyle(e);return [id,{scrollTop:e.scrollTop,scrollHeight:e.scrollHeight,clientWidth:e.clientWidth,clientHeight:e.clientHeight,font:s.font}]})),null,2)},1000);
</script>'''

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  path=self.path.split('?')[0]
  if path=='/':body=HTML.encode();kind='text/html'
  elif path in ['/editor.css','/workspace.css','/code-editor.js']:
   body=(ROOT/'scripts/studio/ui'/path[1:]).read_bytes();kind='text/javascript' if path.endswith('.js') else 'text/css'
  elif path in ['/source/app.py','/source/components/sign_in/presentation.html','/source/components/sports_cave_top_bar/index.html','/source/orders_page.css']:
   body=(ROOT/path[len('/source/'):]).read_bytes();kind='text/plain'
  else:self.send_error(404);return
  self.send_response(200);self.send_header('Content-Type',kind+'; charset=utf-8');self.end_headers();self.wfile.write(body)

def server():
 s=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=s.serve_forever,daemon=True).start();return s

CHECK=r'''() => {
const f=document.querySelector('#ed-source'),m=document.querySelector('#ed-measure'),p=document.querySelector('.ed-paint'),h=document.querySelector('#ed-highlight'),g=document.querySelector('#ed-lines');
const lines=f.value.split('\n'),first=Number(p.dataset.firstLine)-1,base=lines.slice(0,first).reduce((n,l)=>n+l.length+1,0);
function point(root,at){const walk=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;while(n=walk.nextNode()){if(at<n.length){const r=document.createRange();r.setStart(n,at);r.setEnd(n,at+1);return r.getBoundingClientRect();}at-=n.length;}throw Error('Missing rendered character');}
const scale=m.getBoundingClientRect().width/f.clientWidth,scroll=f.scrollTop*scale;
let error=0,checked=0,offset=0;
for(const line of lines.slice(first,first+g.children.length)){
 if(line.length){for(const at of [0,Math.floor(line.length/2),line.length-1]){const a=point(m,base+offset+at),b=point(p,offset+at);error=Math.max(error,Math.abs(a.top-scroll-b.top),Math.abs(a.left-f.scrollLeft*scale-b.left));checked++;}}
 offset+=line.length+1;
}
const style=getComputedStyle(f,'::selection');
return {error,checked,heightError:Math.abs(f.scrollHeight-Math.max(f.clientHeight,m.offsetHeight)),sourceLength:f.value.length,syntaxNodes:h.querySelectorAll('*').length,gutterLines:g.children.length,firstLine:first+1,scrollTop:f.scrollTop,scrollLeft:f.scrollLeft,selectionColor:style.color,overlayScroll:h.scrollTop,gutterScroll:g.scrollTop};
}'''

def check(page,label,results):
 page.evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
 result=page.evaluate(CHECK);results[label]=result
 print(label,round(result['error'],3),result['heightError'],flush=True)
 assert result['error']<1.6,(label,result)
 assert result['heightError']<=2,(label,result)
 assert result['overlayScroll']==result['gutterScroll']==0,(label,result)
 assert result['syntaxNodes']<1200,(label,result)
 assert result['selectionColor']=='rgba(0, 0, 0, 0)',(label,result)

if __name__=='__main__':
 s=server()
 if '--serve' in sys.argv:
  (ROOT.parent/'alignment-qa.json').write_text(json.dumps({'url':f'http://127.0.0.1:{s.server_port}','pid':__import__('os').getpid()}))
  print(f'Isolated fixture: http://127.0.0.1:{s.server_port}',flush=True)
  threading.Event().wait()
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(channel='msedge',headless=True);page=b.new_page(viewport={'width':1680,'height':1000})
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)));results={};timings=[]
   page.goto(f'http://127.0.0.1:{s.server_port}');page.wait_for_function('window.ready')
   for wrap in [False,True]:
    page.locator('#ed-wrap').set_checked(wrap)
    for width in [760,470,950]:
     page.evaluate('(w)=>document.querySelector("main").style.width=w+"px"',width)
     for line in [1,10218,16230]:
      start=time.perf_counter();page.evaluate('(line)=>editor.selectComponent("test",{path:"app.py",line,end_line:line+2})',line)
      check(page,f'python-wrap{wrap}-width{width}-line{line}',results);timings.append((time.perf_counter()-start)*1000)
   page.locator('#ed-wrap').uncheck()
   page.evaluate("editor.selectComponent('horizontal',{path:'app.py',line:500,end_line:502})")
   page.evaluate("document.querySelector('#ed-source').scrollLeft=800")
   check(page,'horizontal-scroll',results)
   for zoom in [0.9,1.1,1.25,1.5]:
    page.evaluate('(z)=>document.body.style.zoom=z',zoom)
    page.evaluate("editor.selectComponent('zoom',{path:'app.py',line:10218,end_line:10220})")
    check(page,f'zoom-{zoom}',results)
   page.evaluate('document.body.style.zoom=1')
   page.evaluate("editor.selectFile('components/sports_cave_top_bar/index.html')")
   check(page,'complete-151k-html',results)
   page.evaluate("editor.selectFile('components/sign_in/presentation.html')")
   original=page.locator('#ed-source').input_value();replacement=original+'\n<!-- tabs\t\twide Ω 日本語 '+('long unbroken value '*90)+' -->\n'
   page.locator('#ed-source').fill(replacement);page.locator('#ed-wrap').check();check(page,'html-typing-tabs-unicode-wrap',results)
   page.evaluate("editor.selectFile('orders_page.css')")
   css=page.locator('#ed-source').input_value();page.locator('#ed-source').fill(css+'\n/* alignment QA */\n');check(page,'css-typing',results)
   page.evaluate("editor.selectFile('components/sign_in/presentation.html')");assert page.locator('#ed-source').input_value()==replacement
   page.evaluate("editor.command('undo')");assert page.locator('#ed-source').input_value()==original
   page.evaluate("editor.command('redo')");assert page.locator('#ed-source').input_value()==replacement
   check(page,'switch-undo-redo-retains-layout',results)
   page.evaluate("editor.command('save')");assert len(page.evaluate('saved'))==1 and len(page.evaluate('saved[0].files'))==2
   check(page,'save-all-two-independent-buffers',results)
   page.evaluate("editor.selectComponent('long Python',{path:'app.py',line:10218,end_line:10302})")
   check(page,'final-long-python-wrapped',results)
   page.screenshot(path=str(ROOT/'docs/final-editor-evidence/alignment-fixed.png'))
   assert not errors,errors
   output={'passed':True,'cases':results,'browser_errors':errors,'selection_and_layout_median_ms':statistics.median(timings),'save_all':'two in-memory files in one batch; no disk writes'}
   (ROOT/'docs/final-editor-evidence/alignment-tests.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
   print(json.dumps({'passed':True,'cases':len(results),'median_ms':statistics.median(timings)}))
   b.close()
 finally:s.shutdown();s.server_close()
