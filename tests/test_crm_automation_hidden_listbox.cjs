const {spawnSync}=require('node:child_process');const vm=require('node:vm');const assert=require('node:assert/strict');
const code=String.raw`import ast,json,subprocess
from streamlit.testing.v1 import AppTest
scripts={}
for version in ('before','after'):
 source=subprocess.check_output(['git','show','8447b3f:crm_automation_home.py'],encoding='utf-8') if version=='before' else open('crm_automation_home.py',encoding='utf-8').read()
 node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='arm_section')
 text=ast.get_source_segment(source,node)
 app=AppTest.from_string(('import streamlit as st\n'+text if version=='before' else 'from crm_automation_home import arm_section')+'\narm_section("auto-kpi-refresh",1)').run()
 scripts[version]=next(e.proto.body for e in app.get('html') if 'scAutoTimers' in e.proto.body)
print(json.dumps(scripts))`;
const r=spawnSync('.venv/Scripts/python.exe',['-c',code],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}});assert.equal(r.status,0,r.stderr);
const scripts=JSON.parse(r.stdout);
for(const version of ['before','after']){
 let queue=[],clicks=0,time=0;const hiddenListbox={getClientRects:()=>[],closest:()=>null};
 const document={addEventListener:()=>{},hidden:false,activeElement:null,getElementById:()=>({}),
  querySelector:s=>s.startsWith('.st-key-')?{disabled:false,click:()=>clicks++}:hiddenListbox,
  querySelectorAll:()=>[hiddenListbox]};
 const context={CSS:{escape:s=>s},window:{},document,Date:{now:()=>time},getComputedStyle:()=>({visibility:'visible'}),
  setTimeout:(fn,delay)=>{queue.push({fn,time:time+delay});return queue.length},clearTimeout:()=>{}};
 vm.runInNewContext(scripts[version].replace(/^<script>/,'').replace(/<\/script>$/,''),context);
 while(queue.length&&queue[0].time<=60000){const q=queue.shift();time=q.time;q.fn()}
 assert.equal(clicks,version==='before'?0:1);
 console.log(version,'hidden global-search listbox: refresh clicks in 60s =',clicks);
}
