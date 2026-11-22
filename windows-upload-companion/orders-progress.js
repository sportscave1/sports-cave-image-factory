'use strict';
let ordersProgressState=null;
function ordersRuntimeVersion(){return typeof chrome.runtime.getManifest==='function'?chrome.runtime.getManifest().version:'1.7.42';}
function ordersProgressBegin(plan){
  const kind=plan.kind==='product'?'product':plan.kind==='qa'?'qa':plan.kind===undefined?'artwork':null;
  if(!kind||! /^(product:)?prodigi_prepare:\d+$/.test(plan.key))return;
  ordersProgressState={plan,kind,stage:'received',sequence:0,started:Date.now(),sending:false,pending:false,attempt:0,next_at:0};
  void ordersProgressSend();
}
async function ordersProgressSend(){
  const s=ordersProgressState;if(!s)return;
  if(s.sending){s.pending=true;return;}
  s.sending=true;s.pending=false;
  try{
    const token=(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
    if(!token)return;
    await fetch(osOrigin+'/api/orders-companion/progress',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
      body:JSON.stringify({key:s.plan.key,token:s.plan.token,kind:s.kind,stage:s.stage,sequence:++s.sequence,
        elapsed_ms:Math.min(3600000,Math.max(0,Date.now()-s.started)),version:ordersRuntimeVersion(),attempt:s.attempt,retry_in_ms:Math.min(5000,Math.max(0,s.next_at-Date.now()))}),credentials:'omit',signal:AbortSignal.timeout(5000)});
  }catch{}finally{s.sending=false;if(s.pending&&ordersProgressState===s)void ordersProgressSend();}
}
function ordersProgressStage(stage){
  const s=ordersProgressState;if(!s)return;
  if(/^product-row-/.test(stage))stage='product-row';
  if(stage!=='retrying'){s.attempt=0;s.next_at=0;}
  if(s.stage===stage)return;s.stage=stage;void ordersProgressSend();
}
function ordersProgressRetry(attempt,delay){if(!ordersProgressState)return;ordersProgressState.attempt=attempt;ordersProgressState.next_at=Date.now()+delay;ordersProgressStage('retrying');}
function ordersProgressEnd(){ordersProgressState=null;}
