const assert=require('node:assert/strict'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const py=`import json
from unittest.mock import patch
from crm_campaign_home import arm_home_poll
state={'campaign_home_dispatch_active':True}
with patch('crm_campaign_home.st.session_state',state),patch('crm_campaign_home.st.html') as html:
 arm_home_poll()
 print(json.dumps(html.call_args.args[0]))`;
const html=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-c',py],{encoding:'utf8'}));
let dialog=null,mounted=true,clicks=0,timers=[];
const button={get isConnected(){return mounted},disabled:false,click(){clicks++}};
const document={hidden:false,querySelector:s=>s==='[role=dialog]'?dialog:mounted?button:null};
const window={};
const context=vm.createContext({window,document,setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length},clearTimeout:()=>{}});
vm.runInContext(html.match(/<script>([\s\S]*)<\/script>/)[1],context);
assert.equal(timers[0].ms,2500);
timers[0].fn();assert.equal(clicks,1);
dialog={};timers[0].fn();assert.equal(clicks,1);
dialog=null;document.hidden=true;timers[0].fn();assert.equal(clicks,1);assert.equal(timers.at(-1).ms,30000);
document.hidden=false;timers[0].fn();assert.equal(clicks,2);
mounted=false;const length=timers.length;timers[0].fn();assert.equal(clicks,2);assert.equal(timers.length,length);
console.log('Home progress timer: 2.5s cadence; dialog/hidden pause; unmounted stop passed.');
