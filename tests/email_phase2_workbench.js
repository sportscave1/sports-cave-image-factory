// Isolated component exercise. The host acknowledges synthetic selections only.
const frame=document.getElementById('component'),status=document.getElementById('status');
let base,ready=false,version='',ack='',results={},metrics=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const paint=()=>new Promise(resolve=>requestAnimationFrame(resolve));
const summary=values=>{const a=[...values].sort((a,b)=>a-b);return {n:a.length,p50_ms:a[Math.floor(a.length*.5)],p95_ms:a[Math.min(a.length-1,Math.floor(a.length*.95))],max_ms:a.at(-1)};};
function send(model){frame.contentWindow.postMessage({type:'streamlit:render',args:{model}},location.origin);}
function row(i){
  return {...base.threads[0],key:'synthetic-thread-'+i,message_key:'synthetic-message-'+i,identity:'synthetic-'+i,
    subject:'Synthetic certificate question '+i,customer:'Fixture customer '+i,email:'fixture'+i+'@example.test',unread:false};
}
function model(i,id){
  const t=row(i),m={...base.messages[0],key:t.message_key,subject:t.subject,expanded:true,unread:false,
    html:'<p>Synthetic private fixture body '+i+'</p>',reader_document:'',quote:'',attachments:[]};
  return {...base,reader_scope:'phase2-'+version,draft_scope:'phase2-'+version,view:'mail',
    selected:i===null?null:t.key,active_message:i===null?null:m.key,messages:i===null?[]:[m],
    threads:Array.from({length:100},(_,j)=>row(j)),ack:id,history_pending:false,discovery_pending:false};
}
window.addEventListener('message',event=>{
  if(event.source!==frame.contentWindow)return;
  if(event.data.type==='streamlit:componentReady'){
    frame.contentWindow.addEventListener('email-selection-timing',event=>metrics.push(event.detail));
    send(model(null,null));ready=true;
  }
  if(event.data.type==='streamlit:setComponentValue'){
    const value=event.data.value;
    if(value.action!=='open_thread')return; // No sends, writes, searches or external API.
    const i=Number(value.thread_key.split('-').at(-1));
    setTimeout(()=>{send(model(i,value.id));ack=value.id;},80);
  }
});
async function select(i,mode,measurements){
  const doc=frame.contentDocument,key='synthetic-thread-'+i;
  const button=[...doc.querySelectorAll('.conversation')].find(n=>n.dataset.key===key);
  const oldAck=ack,start=performance.now();button.click();
  const headerStart=performance.now();
  while(!doc.querySelector('.subject-header')?.textContent.includes(row(i).subject)){
    if(performance.now()-start>3000)throw Error('Header deadline');await paint();
  }
  await paint();measurements[mode+'_headers'].push(performance.now()-start);
  while(!doc.querySelector('.reading .message-body')?.textContent.includes('fixture body '+i)){
    if(performance.now()-start>3000)throw Error('Body deadline');await paint();
  }
  await paint();measurements[mode+'_body'].push(performance.now()-start);
  while(ack===oldAck){if(performance.now()-start>3000)throw Error('Acknowledgement deadline');await pause(5);}
  await paint();
}
async function run(which){
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try{
    base=await(await fetch('/fixture.json')).json();version=which;ready=false;metrics=[];ack='';
    frame.src='/'+which+'/index.html';
    while(!ready)await pause(20);
    await paint();await paint();
    const measurements={cold_headers:[],cold_body:[],cached_headers:[],cached_body:[]};
    for(let i=0;i<100;i++){status.textContent=which+': cold '+(i+1)+'/100';await select(i,'cold',measurements);}
    for(let i=0;i<100;i++){status.textContent=which+': cached '+(i+1)+'/100';await select(i%2?99:98,'cached',measurements);}
    results[which]={simulated_ack_ms:80,...Object.fromEntries(Object.entries(measurements).map(([k,a])=>[k,summary(a)])),
      component_metric_count:metrics.length,component_metrics:metrics};
    document.getElementById('results').textContent=JSON.stringify(results,null,2);
    status.textContent=which+' complete: 100 cold + 100 cached selections';
  }catch(error){status.textContent='FAILED: '+error.message;throw error;}
  finally{document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
document.getElementById('before').onclick=()=>run('before');
document.getElementById('after').onclick=()=>run('after');
