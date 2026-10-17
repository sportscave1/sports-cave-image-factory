/* Status-only bridge for the existing native editor. No edit/ledger writes. */
(() => {
  const host=parent,doc=host.document;
  const send=(type,extra={})=>host.postMessage({isStreamlitMessage:true,type,...extra},'*');
  send('streamlit:componentReady',{apiVersion:1});send('streamlit:setFrameHeight',{height:0});
  host.SportsCaveEditionStatus?.destroy?.();
  const retained=host.SportsCaveEditionStatusState||{scroll:[],nonce:0};
  host.SportsCaveEditionStatusState=retained;
  const controller=new host.AbortController();
  let ids=[],baseline='',pending=null,inFlight=false,force=false,refreshAfter=false,lastPoll=0,timer,interactionUntil=0,pointerHeld=false,touchHeld=false;
  const root=()=>doc.querySelector('.st-key-edition-workspace');
  const grid=()=>root()?.querySelector('[data-testid="stDataFrame"]');
  const modal=()=>doc.querySelector('dialog[open],[role="dialog"]');
  const visible=()=>{const el=root();if(!el||doc.hidden)return false;const b=el.getBoundingClientRect();return b.bottom>0&&b.top<host.innerHeight;};
  const safe=()=>!pointerHeld&&!touchHeld&&Date.now()>=interactionUntil&&!modal()&&!doc.activeElement?.closest?.('input,textarea,[contenteditable="true"],[role="combobox"]');
  const fingerprint=rows=>JSON.stringify(rows);
  function scrollables(){const el=grid();return el?[doc.scrollingElement,doc.querySelector('[data-testid="stMain"]'),el,...el.querySelectorAll('*')].filter(n=>n&&(n.scrollHeight>n.clientHeight||n.scrollWidth>n.clientWidth)):[];}
  function capture(){retained.scroll=scrollables().map((n,index)=>({index,node:n,cls:n.className,top:n.scrollTop,left:n.scrollLeft}));}
  function restore(){const nodes=scrollables();for(const saved of retained.scroll){const n=saved.node?.isConnected?saved.node:nodes.find(n=>saved.cls&&n.className===saved.cls)||nodes[saved.index];if(n){n.scrollTop=saved.top;n.scrollLeft=saved.left;}}}
  function updateRows(rows){
    const previous=new Map((retained.rows||[]).map(r=>[r.product_gid,fingerprint(r)]));
    const changed=rows.filter(r=>previous.get(r.product_gid)!==fingerprint(r));
    retained.rows=rows;if(changed.length)host.SportsCaveEditionReset?.updateRows?.(changed);return changed.length;
  }
  function acceptBatch(operations,refresh=true){
    const byID=new Map(operations.map(r=>[r.product_gid,r]));
    const changed=updateRows((retained.rows||[]).map(row=>{
      const op=byID.get(row.product_gid);if(!op||op.hash!==row.preparation_hash||!['Review','Needs Review'].includes(row.status))return row;
      if(['Pending','Processing'].includes(op.state))return {...row,reset_allowed:op.state==='Processing'?false:row.reset_allowed,review_operation:{label:'Approving…',state:op.state,reason:op.reason||(op.state==='Pending'?'Queued for validation':''),job_id:op.job_id}};
      if(['Failed','Needs Attention','Skipped'].includes(op.state))return {...row,review_operation:{label:op.state==='Failed'?'Approval Failed':'Needs Review',state:op.state,reason:op.reason,job_id:op.job_id}};
      if(op.state==='Approved'&&op.current_hash===row.preparation_hash&&['Cloud Ready','Production Ready'].includes(op.current_status))return {...row,status:op.current_status,review_operation:undefined};
      return row;
    }));
    if(!changed||!refresh)return;force=true;lastPoll=0;if(inFlight)refreshAfter=true;else poll();
  }
  function flush(){
    if(!pending||!visible()||!safe()||force)return;
    if(!pending.unavailable&&Date.now()/1000-pending.snapshot.issued_at>85){force=true;poll();return;}
    const value=pending;pending=null;capture();retained.restoreUntil=Date.now()+5000;baseline=value.unavailable?'Unavailable':fingerprint(value.rows);
    send('streamlit:setComponentValue',{value:{...value,nonce:++retained.nonce},dataType:'json'});
  }
  async function poll(){
    if(inFlight||!ids.length||!visible()||Date.now()-lastPoll<2000)return;
    inFlight=true;lastPoll=Date.now();
    const request=new host.AbortController(),abort=()=>request.abort(),deadline=host.setTimeout(abort,10000);controller.signal.addEventListener('abort',abort,{once:true});
    try{
      const response=await fetch('/api/auto-editions/status',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_gids:ids}),signal:request.signal});
      const value=await response.json();if(!response.ok||!value.snapshot)throw Error('Unavailable');
      updateRows(value.rows);if(fingerprint(value.rows)!==baseline)pending=value;else pending=null;
      force=false;
    }catch(error){if(error.name!=='AbortError'&&baseline!=='Unavailable')pending={unavailable:true};force=false;}
    finally{host.clearTimeout(deadline);controller.signal.removeEventListener('abort',abort);inFlight=false;if(refreshAfter){refreshAfter=false;force=true;lastPoll=0;poll();}else flush();}
  }
  addEventListener('message',event=>{
    if(event.source!==host||event.data?.type!=='streamlit:render')return;
    const args=event.data.args||{};ids=args.product_gids||[];baseline=fingerprint(args.rows||[]);retained.rows=args.rows||[];
    restore();host.requestAnimationFrame(restore);
  },{signal:controller.signal});
  doc.addEventListener('scroll',event=>{if((grid()?.contains(event.target)||event.target===doc.scrollingElement||event.target===doc.querySelector('[data-testid="stMain"]'))&&Date.now()>=(retained.restoreUntil||0))capture();},{capture:true,passive:true,signal:controller.signal});
  doc.addEventListener('wheel',()=>{if(!modal()&&visible()){retained.restoreUntil=0;interactionUntil=Date.now()+500;host.requestAnimationFrame(capture);host.setTimeout(flush,550);}},{capture:true,passive:true,signal:controller.signal});
  doc.addEventListener('pointerdown',()=>{if(!modal()){pointerHeld=true;retained.restoreUntil=0;host.requestAnimationFrame(capture);}},{capture:true,passive:true,signal:controller.signal});
  for(const type of ['pointerup','pointercancel'])doc.addEventListener(type,()=>{pointerHeld=false;interactionUntil=Math.max(interactionUntil,Date.now()+150);host.setTimeout(flush,200);},{capture:true,passive:true,signal:controller.signal});
  doc.addEventListener('touchstart',()=>{if(!modal()){touchHeld=true;retained.restoreUntil=0;host.requestAnimationFrame(capture);}},{capture:true,passive:true,signal:controller.signal});
  for(const type of ['touchend','touchcancel'])doc.addEventListener(type,()=>{touchHeld=false;interactionUntil=Math.max(interactionUntil,Date.now()+150);host.setTimeout(flush,200);},{capture:true,passive:true,signal:controller.signal});
  doc.addEventListener('focusout',event=>{
    const editing=!!event.target.closest?.('input,textarea,[contenteditable="true"],[role="combobox"]');
    // Glide commits edited widget state asynchronously. Let that callback land
    // before a status change can replace the native editor's widget identity.
    if(editing)interactionUntil=Date.now()+1200;
    host.setTimeout(()=>{if(force)poll();else flush();},editing?1300:0);
  },{signal:controller.signal});
  host.addEventListener('message',event=>{
    if(event.origin!==host.location.origin)return;
    if(['sports-cave-psd-saved','sports-cave-auto-edition-updated'].includes(event.data?.type)){force=true;poll();}
  },{signal:controller.signal});
  doc.addEventListener('visibilitychange',()=>{if(!doc.hidden)poll();},{signal:controller.signal});
  const observer=new host.MutationObserver(()=>{restore();if(force&&!modal())poll();else flush();});
  const scope=root();if(scope)observer.observe(scope,{childList:true,subtree:true});
  timer=host.setInterval(()=>{const active=(retained.rows||[]).some(r=>r.status==='Uploading'||['Pending Approval','Approving…'].includes(r.review_operation?.label));if(force||active||Date.now()-lastPoll>=25000)poll();},3000);
  const lifecycle={poll,flush,safe,acceptBatch,refresh(){force=true;lastPoll=0;if(inFlight){refreshAfter=true;return;}poll();},destroy(){host.clearInterval(timer);controller.abort();observer.disconnect();}};
  host.SportsCaveEditionStatus=lifecycle;
  addEventListener('pagehide',()=>{if(host.SportsCaveEditionStatus===lifecycle)lifecycle.destroy();},{once:true});
})();
