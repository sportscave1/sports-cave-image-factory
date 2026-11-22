(function(root){
  'use strict';
  const PAGE_SIZE=50;
  function category(row){if(row.review?.status==='Submitted')return 'ready';if(row.review?.status==='Complete')return 'complete';if(String(row.cells?.prodigi||'').toLowerCase()==='complete')return 'complete';if(row.state?.tone==='success')return 'ready';if(row.review&&!row.review.can_restart)return 'progress';return 'attention';}
  function filtered(rows,filter){return filter==='all'?rows:rows.filter(r=>category(r)===filter);}
  function pageRows(rows,page){return rows.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);}
  function togglePage(ids,rows,checked){const next=new Set(ids);for(const r of rows)checked?next.add(r.id):next.delete(r.id);return next;}
  function groupKey(row){return row.review?.order_url||String(row.cells?.order||'').replace(/^⧉\s*/,'').trim()||row.id;}
  function orderGroups(rows){const groups=new Map();for(const row of rows){const key=groupKey(row);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(row);}return [...groups.values()].flat();}
  function siblings(rows,row){const key=groupKey(row);return rows.filter(r=>groupKey(r)===key);}
  const api={PAGE_SIZE,category,filtered,pageRows,togglePage,orderGroups,siblings};
  if(typeof module!=='undefined')module.exports=api;else root.OrdersGridCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
