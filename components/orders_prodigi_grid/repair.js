(function(root){
  'use strict';
  const pending=new Set(),requests=new Map(),errors=new Map();
  function state(row){
    const a=row.review?.artwork;
    if(row.detached||!a||['Submitted','Complete','Certificate pending','Submission uncertain'].includes(row.review?.status)
      ||String(row.cells?.prodigi||'').toLowerCase()==='complete'
      ||!/^gid:\/\/shopify\/Product\/[1-9][0-9]*$/.test(a.product_gid)||String(a.allocation_id)!==String(row.review?.allocation_id))return null;
    if(a.active)errors.delete(a.product_gid);
    const active=a.active||pending.has(a.product_gid);
    if(!a.repairable&&!active)return null;
    return {...a,active,canSubmit:!active&&a.repairable,label:active?'PSD repairing':'PSD repair',
      message:errors.get(a.product_gid)||(pending.has(a.product_gid)?'PSD repair is being added to the queue.':a.message)};
  }
  async function submit(row,changed){
    const current=state(row);if(!current?.canSubmit)return;
    const pid=current.product_gid;
    if(!requests.has(pid))requests.set(pid,crypto.randomUUID());
    pending.add(pid);errors.delete(pid);changed();
    const abort=new AbortController(),deadline=setTimeout(()=>abort.abort(),15000);
    try{
      const response=await fetch('/api/auto-editions/repair',{method:'POST',credentials:'same-origin',
        headers:{'Content-Type':'application/json'},signal:abort.signal,
        body:JSON.stringify({product_gid:pid,allocation_id:current.allocation_id,request_id:requests.get(pid)})});
      const result=await response.json();if(!response.ok||!result.ok||!result.repair)throw Error(result.error||'Repair request was not acknowledged.');
      const d=result.repair,active=['Queued','Diagnosing','Waiting','Codex queued','Codex repairing'].includes(d.state);
      row.review={...row.review,status:active?'PSD repairing':'PSD repair',can_restart:false,can_reset:false,
        updated_at:d.changed_at,message:d.message,artwork:{...row.review.artwork,active,repairable:!active,
          state:d.state,message:d.message,request_id:d.request_id,updated_at:d.changed_at}};
      requests.delete(pid);
    }catch(error){
      errors.set(pid,'PSD repair was not queued: '+(error.name==='AbortError'?'Connection timed out. Click PSD repair to check the same request again.':error.message));
    }finally{clearTimeout(deadline);pending.delete(pid);changed();}
  }
  const api={state,submit};if(typeof module!=='undefined')module.exports=api;else root.OrdersArtworkRepair=api;
})(typeof globalThis!=='undefined'?globalThis:this);
