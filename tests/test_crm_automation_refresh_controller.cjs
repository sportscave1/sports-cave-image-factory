// Execute the actual rendered controller against a deterministic browser clock.
const {spawnSync}=require('node:child_process');const vm=require('node:vm');const assert=require('node:assert/strict');
const code=String.raw`import json
from streamlit.testing.v1 import AppTest
scripts={}
for key in ('auto-list-refresh','auto-kpi-refresh','auto-publication-refresh'):
 app=AppTest.from_string('from crm_automation_home import arm_section\narm_section('+repr(key)+',1)').run()
 scripts[key]=next(e.proto.body for e in app.get('html') if 'scAutoTimers' in e.proto.body)
print(json.dumps(scripts))`;
const result=spawnSync('.venv/Scripts/python.exe',['-c',code],{encoding:'utf8',env:{...process.env,PYTHONUTF8:'1'}});assert.equal(result.status,0,result.stderr);
const scripts=JSON.parse(result.stdout);let time=0,next=0,modal=false,mounted=true;const queue=new Map(),clicks=[];
const window={};const document={hidden:false,activeElement:null,getElementById:()=>mounted?{}:null,
 querySelectorAll:()=>[{getClientRects:()=>[]} , ...(modal?[{getClientRects:()=>[{}]}]:[])],
 querySelector:s=>s.startsWith('.st-key-')?{disabled:false,click:()=>clicks.push(s)}:(modal?{}:null)};
const context={window,document,getComputedStyle:()=>({visibility:'visible'}),Date:{now:()=>time},setTimeout:(fn,delay)=>{const id=++next;queue.set(id,{fn,due:time+delay});return id},clearTimeout:id=>queue.delete(id)};
function arm(key){vm.runInNewContext(scripts[key].replace(/^<script>/,'').replace(/<\/script>$/,''),context)}
function advance(ms){const end=time+ms;for(;;){let found=[...queue].filter(([,v])=>v.due<=end).sort((a,b)=>a[1].due-b[1].due)[0];if(!found)break;time=found[1].due;queue.delete(found[0]);found[1].fn()}time=end}
arm('auto-list-refresh');arm('auto-kpi-refresh');advance(1000);assert.equal(clicks.length,1,'Simultaneous fragment clicks were not serialized');
arm('auto-list-refresh');advance(1000);assert.equal(clicks.length,2,'Acknowledgement did not release the request gate');
queue.clear();window.scAutoRequest=null;clicks.length=0;modal=true;
arm('auto-publication-refresh');advance(35000);assert.equal(clicks.length,0);modal=false;advance(2000);assert.equal(clicks.length,1,'Refresh did not resume after a long dialog');
queue.clear();window.scAutoRequest=null;clicks.length=0;arm('auto-publication-refresh');mounted=false;advance(10000);assert.equal(clicks.length,0);assert.equal(queue.size,0);
console.log('Controller: serialization, acknowledgement, long-dialog resume and navigation disposal PASS');
