(function(root){
  'use strict';
  const PAGE_SIZE=50;
  function category(row){if(row.review?.customer_hold)return 'attention';if(row.review?.artwork?.active)return 'progress';if(row.review?.artwork?.repairable)return 'attention';if(row.review?.status==='Submitted')return 'ready';if(row.review?.status==='Complete')return 'complete';if(String(row.cells?.prodigi||'').toLowerCase()==='complete')return 'complete';if(row.state?.tone==='success')return 'ready';if(row.review&&!row.review.can_restart)return 'progress';return 'attention';}
  function fulfilmentLabel(row){
    const q=row.review||{},s=row.state||{};
    if(q.status==='Customer hold')return 'Customer hold';
    const supplier={in_production:'In production',partially_shipped:'Partially shipped',shipped:'Shipped',completed:'Completed',cancelled:'Cancelled',failed:'Failed',on_hold:'On hold'};
    const label=q.status==='Complete'||s.tone==='complete'?'✓ Complete':q.status==='Submitted'?'Submitted':(q.has_error??q.can_restart)?'× Needs attention':['Waiting','Queued','Preparing JPG'].includes(q.status)?'Queued':q.status==='Ready for manual payment'?(q.submission_enabled?'Submitting':'Ready · submit paused'):q.status||'Queued';
    return supplier[q.supplier_status]||label;
  }
  function filtered(rows,filter){return filter==='all'?rows:rows.filter(r=>category(r)===filter);}
  function pageRows(rows,page){return rows.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);}
  function togglePage(ids,rows,checked){const next=new Set(ids);for(const r of rows)checked?next.add(r.id):next.delete(r.id);return next;}
  function groupKey(row){return row.review?.order_url||String(row.cells?.order||'').replace(/^â§‰\s*/,'').trim()||row.id;}
  function orderGroups(rows){const groups=new Map();for(const row of rows){const key=groupKey(row);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}return [...groups.values()].flat();}
  function siblings(rows,row){const key=groupKey(row);return rows.filter(r=>groupKey(r)===key);}
  function visible(rows,filter,query=''){return orderGroups(filtered(rows,filter).filter(r=>Object.values(r.cells||{}).join(' ').toLowerCase().includes(query.toLowerCase())));}
  function preserveReview(old,fresh){
    const prior=old?.review,next=fresh.review;
    if(!old?.detached&&prior?.updated_at&&(!next?.updated_at||Date.parse(prior.updated_at)>=Date.parse(next.updated_at))){
      fresh={...fresh,review:prior};
      if(prior.status==='Complete')fresh={...fresh,cells:{...fresh.cells,prodigi:'Complete'},certificate:'/api/orders/certificate?allocation_id='+prior.allocation_id};
    }
    return fresh;
  }
  function mergeDelta(rows,delta,selection,opened){
    if(!delta||!Array.isArray(delta.order)||!Array.isArray(delta.rows)||!Array.isArray(delta.removed)||delta.order.length>2000||new Set(delta.order).size!==delta.order.length)throw Error('Invalid Orders update');
    const old=new Map(rows.map(r=>[r.id,r])),next=new Map(old),changed=new Set(),selected=new Set(selection);
    const newIds=new Set();
    for(const item of delta.rows){
      if(!item||typeof item.id!=='string'||newIds.has(item.id)||!delta.order.includes(item.id)||!/^[a-f0-9]{64}$/.test(item.revision))throw Error('Invalid Orders row');
      newIds.add(item.id);const prior=old.get(item.id),fresh=preserveReview(prior,item);
      if(prior&&JSON.stringify({...prior,revision:fresh.revision})===JSON.stringify(fresh)){next.set(item.id,{...prior,revision:fresh.revision});}
      else{next.set(item.id,fresh);changed.add(item.id);}
    }
    if(delta.order.some(id=>!next.has(id))||delta.removed.some(id=>delta.order.includes(id)))throw Error('Missing Orders row');
    // Transfer local review only across one exact immutable unit, never a name.
    for(const id of delta.removed){
      const prior=old.get(id);if(!prior?.unit_key)continue;
      const before=rows.filter(r=>r.unit_key===prior.unit_key),after=delta.order.map(k=>next.get(k)).filter(r=>r.unit_key===prior.unit_key);
      if(before.length===1&&after.length===1&&after[0].id!==id){if(selected.delete(id))selected.add(after[0].id);if(opened===id)opened=after[0].id;}
    }
    const result=delta.order.map(id=>next.get(id));
    for(const id of delta.removed){const prior=old.get(id);if(!prior||(!selected.has(id)&&opened!==id))continue;
      const detached=prior.detached?prior:{...prior,detached:true,state:{label:'Outside current results',tone:'muted',action:'',url:''},review:{...prior.review,status:'Outside current results',can_restart:false,can_reset:false,can_merge_restart:false,message:'This edition is outside the current results. Search its order to refresh it.'}};
      result.push(detached);if(detached!==prior)changed.add(id);
    }
    return {rows:result,selected,opened,changed};
  }
  function anchoredPage(rows,page,anchor){const index=anchor?rows.findIndex(r=>r.id===anchor):-1;return Math.min(index>=0?Math.floor(index/PAGE_SIZE):page,Math.max(0,Math.ceil(rows.length/PAGE_SIZE)-1));}
  function statusIds(rows,opened,filter,page,query=''){
    rows=rows.filter(r=>!r.detached);
    const active=rows.find(r=>r.id===opened),priority=[...(active?[active,...siblings(rows,active)]:[]),...pageRows(visible(rows,filter,query),page),...rows];
    return [...new Set(priority.map(r=>r.review?.allocation_id).filter(v=>/^[1-9][0-9]*$/.test(v||'')))].slice(0,200);
  }
  const api={PAGE_SIZE,category,fulfilmentLabel,filtered,pageRows,togglePage,orderGroups,siblings,visible,preserveReview,mergeDelta,anchoredPage,statusIds};
  if(typeof module!=='undefined')module.exports=api;else root.OrdersGridCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
