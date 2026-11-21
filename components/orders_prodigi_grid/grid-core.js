(function(root){
  'use strict';
  const PAGE_SIZE=50;
  function category(row){if(row.state?.tone==='success')return 'ready';if(String(row.cells?.prodigi||'').toLowerCase()==='complete')return 'complete';return 'attention';}
  function filtered(rows,filter){return filter==='all'?rows:rows.filter(r=>category(r)===filter);}
  function pageRows(rows,page){return rows.slice(page*PAGE_SIZE,(page+1)*PAGE_SIZE);}
  function togglePage(ids,rows,checked){const next=new Set(ids);for(const r of rows)checked?next.add(r.id):next.delete(r.id);return next;}
  const api={PAGE_SIZE,category,filtered,pageRows,togglePage};
  if(typeof module!=='undefined')module.exports=api;else root.OrdersGridCore=api;
})(typeof globalThis!=='undefined'?globalThis:this);
