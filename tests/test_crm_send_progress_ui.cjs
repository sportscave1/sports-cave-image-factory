const assert=require('node:assert/strict'),vm=require('node:vm');
const {execFileSync}=require('node:child_process');
const py=`import json
from unittest.mock import patch
from crm_campaign_progress_ui import poll
with patch('crm_campaign_progress_ui.st.container'),patch('crm_campaign_progress_ui.st.button'),patch('crm_campaign_progress_ui.st.html') as html:
 poll('crm-history-poll',3)
 poll('crm-send-tray-poll',2.5)
 print(json.dumps([c.args[0] for c in html.call_args_list]))`;
const scripts=JSON.parse(execFileSync('.venv/Scripts/python.exe',['-c',py],{encoding:'utf8'}));
let dialog=null,mounted=true,clicks=0,timers=[];
const button={get isConnected(){return mounted},click(){clicks++}};
const document={querySelector:s=>s==='[role=dialog]'?dialog:mounted?button:null};
const window={};
const context=vm.createContext({window,document,setTimeout:(fn,ms)=>{timers.push({fn,ms});return timers.length},clearTimeout:()=>{}});
for(const html of scripts)vm.runInContext(html.match(/<script>([\s\S]*)<\/script>/)[1],context);
assert.equal(Object.keys(window.scCampaignTimers).length,2);
assert.deepEqual(timers.map(t=>t.ms),[3000,2500]);
timers[0].fn();assert.equal(clicks,1);
// Arbitrary AI/analytics modal: history and tray defer, no server event.
dialog={querySelector:()=>null};timers[0].fn();timers[1].fn();assert.equal(clicks,1);
// Sending dialog: history can update, tray stays paused behind the overlay.
dialog={querySelector:()=>({})};timers[0].fn();assert.equal(clicks,2);
timers[1].fn();assert.equal(clicks,2);
dialog=null;timers[1].fn();assert.equal(clicks,3);
mounted=false;const length=timers.length;timers[0].fn();assert.equal(clicks,3);assert.equal(timers.length,length);
console.log('Send progress timers: independent cadence, modal isolation, native events and unmounted stop passed.');
