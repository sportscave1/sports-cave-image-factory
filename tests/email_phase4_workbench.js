// Synthetic host for the real inbox component. No mailbox, SMTP or write APIs.
const frame=document.getElementById('component');
let base,current,selected=null,actions=0,blocked=0,revision=1,sent=false;
function row(i){return {...base.threads[0],key:'fixture-thread-'+i,message_key:'fixture-message-'+i,
  subject:['Missing certificate for my collection','Packing slip not received','Thanks for the artwork'][i],
  customer:['Alex Fixture','Sam Fixture','Taylor Fixture'][i],email:'customer'+i+'@example.test',
  snippet:i===0?'Where can I access my certificate?':'Synthetic mailbox fixture',unread:false,
  companion:sent&&i===0?{status:'sent'}:null};}
function selection(i){
  const t=row(i),m={...base.messages[0],key:t.message_key,subject:t.subject,expanded:true,unread:false,
    sender:{name:t.customer,email:t.email},time:'25 Nov · 12:00 PM',companion:t.companion,
    html:'<p>Synthetic customer message. I received my artwork but the packing slip was missing. Where can I access my certificate?</p>',
    reader_document:'',quote:'',attachments:[],warnings:[]};
  return {selected:t.key,active_message:m.key,messages:[m]};
}
function post(){frame.contentWindow.postMessage({type:'streamlit:render',args:{model:current}},location.origin);}
function counter(){document.getElementById('activity').textContent=`Synthetic events: ${actions} · External actions: 0 · Blocked writes: ${blocked}`;}
async function initialise(){
  base=await(await fetch('/fixture.json')).json();
  current={...base,reader_scope:'phase4-synthetic',draft_scope:'phase4-synthetic',mailbox:'support@example.test',
    admin:false,can_diagnose:true,configured:true,smtp_configured:false,view:'mail',selected:null,active_message:null,messages:[],
    threads:[0,1,2].map(row),mailbox_version:'fixture-'+revision,refreshed:'25 Nov · 12:00 PM',
    sync_health:{state:'CONNECTED'},recovery:{},error:'',live_error:'',notice:'',ack:null,
    initial_load_pending:false,read_pending:false,history_pending:false,discovery_pending:false,live_pending:false,
    body_pending:null,read_mark_pending:null,body_completion:null,
    recoverable_drafts:[{draft_id:'fixture-saved',subject:'Saved draft example',recipients:'customer@example.test'}]};
  frame.src='/component/index.html';counter();
}
window.addEventListener('message',event=>{
  if(event.source!==frame.contentWindow||event.origin!==location.origin)return;
  if(event.data.type==='streamlit:componentReady'){post();return;}
  if(event.data.type!=='streamlit:setComponentValue')return;
  const value=event.data.value;actions++;counter();
  if(value.action==='open_thread'){
    const i=Number(value.thread_key.split('-').at(-1));selected=i;
    setTimeout(()=>{current={...current,...selection(i),ack:value.id};post();},80);return;
  }
  if(value.action==='settings'){current={...current,view:'settings',ack:value.id};post();return;}
  if(value.action==='close_panel'){current={...current,view:'mail',ack:value.id};post();return;}
  if(value.action==='mail_diagnostics'){
    const healthy=current.sync_health.state==='CONNECTED';
    current={...current,ack:value.id,admin_diagnostics:{counts:{accepted:1},unknown_count:0,copy_pending_count:0},
      admin_operations:{state:healthy?'healthy':'needs_attention',certificate_enabled:true,
        last_successful_poll_age_seconds:healthy?14:180,observed_at:'2026-11-25T04:00:00+00:00',
        alerts:healthy?[]:[{code:'poll_stale',severity:'critical',message:'The certificate worker has not completed a recent mailbox check. Check connection and worker logs; keep its cursor.'}],
        browser_selection:value.selection_metrics,process:{scope:'Synthetic fixture'}}};post();return;
  }
  if(value.action==='compose'){
    current={...current,view:'compose',draft:{id:'fixture-draft',mode:'new',to:'',cc:'',bcc:'',subject:'',
      html:'<p>Local fixture draft</p>',signature:'none',quote_html:'',include_quote:false,attachments:[],
      operation_id:'fixture-operation',edit_revision:0,storage_version:0},ack:value.id};post();return;
  }
  if(value.action==='close_composer')current={...current,view:'mail',draft:null};
  else if(!['live_check','sync_index','reconnect','autosave_draft','contact_search','search'].includes(value.action)){blocked++;counter();}
  current={...current,ack:value.id};post();
});
document.querySelectorAll('[data-state]').forEach(button=>button.onclick=()=>{
  const state=button.dataset.state;
  current={...current,error:'',live_error:'',notice:'',read_pending:false,recovery:{},sync_health:{state:'CONNECTED'}};
  if(state==='syncing')current={...current,read_pending:true,recovery:{state:'waiting',delay_ms:1000}};
  if(state==='reconnecting')current={...current,live_error:'Synthetic network interruption',sync_health:{state:'RECONNECTING',retry_after:15},recovery:{state:'waiting',delay_ms:15000}};
  if(state==='attention')current={...current,sync_health:{state:'RECONNECTING',category:'authentication'},recovery:{state:'stopped'}};
  post();
});
document.getElementById('mobile').onclick=()=>{frame.style.width='375px';document.getElementById('size').textContent='375 px component viewport';};
document.getElementById('desktop').onclick=()=>{frame.style.width='100%';document.getElementById('size').textContent='Desktop component viewport';};
document.getElementById('refresh').onclick=()=>{
  document.getElementById('refresh-status').textContent='Refresh scheduled in 3 seconds';
  setTimeout(()=>{current={...current,refreshed:'25 Nov · 12:01 PM',mailbox_version:'fixture-'+(++revision)};post();
    document.getElementById('refresh-status').textContent='Background refresh finished';},3000);
};
document.getElementById('badge').onclick=()=>{sent=true;current={...current,threads:[0,1,2].map(row),...(selected===0?selection(0):{})};post();};
document.getElementById('loading').onclick=()=>{
  selected=1;current={...current,...selection(1),messages:selection(1).messages.map(m=>({...m,expanded:false,body_loading:true}))};post();
};
document.getElementById('loaded').onclick=()=>{if(selected!==null){current={...current,...selection(selected)};post();}};
initialise();
