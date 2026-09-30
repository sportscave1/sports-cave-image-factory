const assert=require('node:assert/strict'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const py=`import ast,json,re
t=ast.parse(open('crm_campaign_send_ui.py',encoding='utf-8').read())
print(json.dumps([s for n in ast.walk(t) if isinstance(n,ast.Constant) and isinstance(n.value,str) for s in re.findall(r'<script>(.*?)</script>',n.value,re.S) if 'reviewDismiss' in s or 'scCampaignReviewPoll' in s]))`;
const scripts=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-c',py],{encoding:'utf8'}));
assert.equal(scripts.length,2);
let listener,bindings=0,closed=0,polls=0,timer,cleared=0,visible=true;
const nativeClose={click:()=>{closed++;visible=false;}};
const cancel={dataset:{},addEventListener:(_,fn,capture)=>{assert.equal(capture,true);listener=fn;bindings++;},closest:()=>({querySelector:()=>nativeClose})};
const document={querySelector:s=>!visible?null:s.includes('dismiss')?cancel:{click:()=>polls++}};
const context=vm.createContext({document,window:{},clearTimeout:()=>cleared++,setTimeout:fn=>{timer=fn;return 1;}});
for(let i=0;i<3;i++)for(const script of scripts)vm.runInContext(script,context);
assert.equal(bindings,1);assert.equal(cleared,3);
let prevented=0,stopped=0;listener({preventDefault:()=>prevented++,stopImmediatePropagation:()=>stopped++});
assert.equal(closed,1);assert.equal(prevented,1);assert.equal(stopped,1);
timer();assert.equal(polls,0); // A dismissed modal cannot keep polling.
visible=true;timer();assert.equal(polls,1);
console.log('Review UI: repeat script execution, native Cancel, no server click, one-shot polling and dismissal passed.');
