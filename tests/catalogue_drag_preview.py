"""Standalone, offline host for mouse-testing the actual section component.

Some browser drivers cannot drag within cross-document Streamlit iframes.
This serves the same unmodified component with a local acknowledgement host.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]/'components'/'crm_sections'
HOST='''<script>
const sections=[{id:'html-1',type:'html',html_number:1,visible:true,html:''},
 {id:'cat',type:'catalogue',visible:true,products:[{id:'p1',title:'Brock',edition:{}},{id:'p2',title:'Warne',edition:{}}],
 settings:{columns:2,display:{image:true,title:true,price:true,limit:true,next:true,remaining:true,cta:true},cta:'View the Edition'}}];
let rows=sections;
window.addEventListener('message',e=>{
 if(e.data.type==='streamlit:componentReady')postMessage({type:'streamlit:render',args:{sections:rows}});
 if(e.data.type==='streamlit:setComponentValue'){
  const v=e.data.value;
  if(v.type==='order')rows=v.ids.map(id=>rows.find(s=>s.id===id));
  if(v.type==='product_order'){const s=rows.find(s=>s.id===v.id);s.products=v.ids.map(id=>s.products.find(p=>p.id===id));}
  document.getElementById('receipt').textContent=JSON.stringify(v);
  postMessage({type:'streamlit:render',args:{sections:rows,ack:v.event}});
 }
});
</script>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        name=self.path.lstrip('/') or 'index.html'
        if name not in ('index.html','composer.js','style.css'):self.send_error(404);return
        text=(ROOT/name).read_text(encoding='utf-8')
        if name=='index.html':
            text=text.replace('<body>','<body style="max-width:380px;padding:20px">'+HOST+'<p>✓ Header · fixed</p>')
            text=text.replace('<script src="composer.js">','<p>✓ Footer · fixed</p><output id="receipt"></output><script src="composer.js">')
        self.send_response(200);self.send_header('Content-Type','text/html' if name.endswith('html') else 'text/javascript' if name.endswith('js') else 'text/css');self.end_headers();self.wfile.write(text.encode())

if __name__=='__main__':HTTPServer(('127.0.0.1',8516),Handler).serve_forever()
