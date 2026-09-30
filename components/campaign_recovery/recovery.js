/* Emergency per-tab checkpoint. The backend remains authoritative. */
(() => {
 let args=null,record=null,timer=null,inflight=null,inflightCopy=null,storageKey='',scope='',stopped=false;
 const clone=value=>JSON.parse(JSON.stringify(value));
 const persist=()=>{try{sessionStorage.setItem(storageKey,JSON.stringify(record));}catch{/* Quota/privacy mode must not break editing. */}};
 const emit=()=>{
  clearTimeout(timer);if(!record||!args||inflight||stopped)return;
  inflight=crypto.randomUUID();inflightCopy=clone(record);
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{event:inflight,record}},'*');
 };
 const changed=()=>{
  stopped=false;record.updated=Date.now();persist();clearTimeout(timer);
  const status=parent.document.getElementById('sc-campaign-save-status');if(status)status.textContent='Saving…';
  timer=setTimeout(emit,750);
 };
 const ensure=()=>{if(!record)record={scope,base:clone(args.editor),editor:clone(args.editor)};};
 const input=e=>{
  if(!args)return;
  const node=e.target;if(!node.closest('.st-key-crm-composer-controls'))return;
  const label=node.getAttribute('aria-label');
  if(!['Campaign name','Subject','Preview text'].includes(label))return;
  ensure();if(label==='Campaign name')record.editor.name=node.value;
  else record.editor.document.content[label==='Subject'?'subject':'preheader']=node.value;
  record.editor.document.copy_reviewed=false;changed();
 };
 const section=e=>{
  if(!args)return;const {id,html,cta}=e.detail||{};
  const source=(args.editor.document.middle_sections||[]).find(s=>s.id===id);if(!source)return;
  ensure();const target=record.editor.document.middle_sections.find(s=>s.id===id);if(!target)return;
  if(typeof html==='string'&&['html','image'].includes(target.type)){
   target.html=html;if(target.html_number===1)record.editor.document.custom_html=html;
  }
  if(typeof cta==='string'&&target.type==='catalogue')target.settings.cta=cta;
  record.editor.document.copy_reviewed=false;changed();
 };
 const flush=()=>{clearTimeout(timer);if(record){persist();emit();}};
 const waitForRecovery=()=>new Promise((resolve,reject)=>{
  const started=Date.now();flush();
  const check=()=>{
   if(stopped||Date.now()-started>10000)return reject(new Error('Draft changes could not be synchronized. Retry after saving.'));
   if(!record&&!inflight)return resolve();
   setTimeout(check,30);
  };check();
 });
 parent.scCampaignFlushRecovery=waitForRecovery;
 const discard=()=>{clearTimeout(timer);record=null;inflight=null;inflightCopy=null;stopped=true;try{sessionStorage.removeItem(storageKey);}catch{}};
 parent.addEventListener('sc-campaign-discard',discard);
 const visible=()=>{if(parent.document.hidden)flush();else if(record&&!stopped)emit();};
 parent.document.addEventListener('input',input,true);
 parent.addEventListener('sc-campaign-pending',section);
 parent.document.addEventListener('visibilitychange',visible);
 parent.addEventListener('pagehide',flush);
 parent.addEventListener('sc-recovery-flush',flush);
 parent.addEventListener('blur',flush);
 addEventListener('pagehide',()=>{
  if(parent.scCampaignFlushRecovery===waitForRecovery)delete parent.scCampaignFlushRecovery;
  flush();parent.removeEventListener('sc-campaign-discard',discard);parent.document.removeEventListener('input',input,true);
  parent.removeEventListener('sc-campaign-pending',section);
  parent.document.removeEventListener('visibilitychange',visible);
  parent.removeEventListener('sc-recovery-flush',flush);
  parent.removeEventListener('pagehide',flush);parent.removeEventListener('blur',flush);
 });
 addEventListener('message',e=>{
  if(e.source!==parent||e.data.type!=='streamlit:render')return;
  args=e.data.args;scope=args.scope;storageKey='sc-campaign-recovery:'+scope;
  if(inflight&&args.ack===inflight){
   inflight=null;stopped=!!args.failed;
   if(!stopped&&JSON.stringify(record)===JSON.stringify(inflightCopy)){record=null;sessionStorage.removeItem(storageKey);}
   inflightCopy=null;
  }
  if(!record){try{record=JSON.parse(sessionStorage.getItem(storageKey));}catch{record=null;}}
  if(record){
   const equal=record.editor.name===args.editor.name&&JSON.stringify(record.editor.document)===JSON.stringify(args.editor.document);
   if(equal&&args.confirmed&&!args.failed){record=null;sessionStorage.removeItem(storageKey);stopped=false;}
   else if(!inflight&&!stopped)emit();
  }
  const status=parent.document.getElementById('sc-campaign-save-status');
  if(status&&!record&&!args.failed)status.textContent=args.editor.id?'Saved':'Ready · changes save automatically';
  parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:0},'*');
 });
 parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
})();
