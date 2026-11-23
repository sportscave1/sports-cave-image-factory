'use strict';
let feedTimer=null,feedRefreshing=false,feedAbort=null,feedVersion='',feedDelayed=false,feedFailures=0,feedRetryAt=0;

function viewportAnchor(){
  const wrap=document.querySelector('.scroll');
  if(!wrap)return null;
  const top=wrap.getBoundingClientRect().top;
  const row=Array.from(wrap.querySelectorAll('tr[data-unit-id]')).find(r=>r.getBoundingClientRect().bottom>top+40);
  return {id:row&&(page>0||wrap.scrollTop>0)?row.dataset.unitId:'',offset:row?row.getBoundingClientRect().top-top:0,scroll:wrap.scrollTop,focus:document.activeElement?.id};
}

function patchLiveListing(changed,anchor){
  const wrap=document.querySelector('.scroll'),body=wrap?.querySelector('tbody');
  if(!body){render();return;}
  const rows=args.rows||[],filtered=core.visible(rows,filter,query);
  page=core.anchoredPage(filtered,page,anchor?.id);
  const shown=core.pageRows(filtered,page),existing=new Map(Array.from(body.children).map(r=>[r.dataset.unitId,r]));
  const wanted=new Set(shown.map(r=>r.id));
  for(const old of Array.from(body.children))if(!wanted.has(old.dataset.unitId))old.remove();
  shown.forEach((data,index)=>{
    let element=existing.get(data.id);
    if(!element||changed.has(data.id)){const fresh=orderRow(data);if(element?.parentNode===body)element.replaceWith(fresh);element=fresh;}
    if(body.children[index]!==element)body.insertBefore(element,body.children[index]||null);
  });
  for(const b of document.querySelectorAll('.filter')){const id=b.dataset.filterId;if(id)b.querySelector('.count').textContent=String(core.filtered(rows,id).length);}
  const summary=document.querySelector('.summary');if(summary)summary.textContent=new Set(rows.filter(r=>!r.detached).map(r=>r.cells?.order)).size+' orders · '+rows.filter(r=>!r.detached).length+' units';
  const nav=document.querySelector('.pagination'),label=nav?.querySelector('span');
  if(label)label.textContent=filtered.length?(page*SIZE+1)+'–'+Math.min((page+1)*SIZE,filtered.length)+' of '+filtered.length:'0 orders';
  const prev=document.getElementById('orders-prev-page'),next=document.getElementById('orders-next-page');
  if(prev)prev.disabled=page===0;if(next)next.disabled=(page+1)*SIZE>=filtered.length;
  const all=document.getElementById('select-visible-orders');
  if(all){all.checked=shown.length>0&&shown.every(r=>selected.has(r.id));all.indeterminate=shown.some(r=>selected.has(r.id))&&!all.checked;}
  const current=document.querySelector('.drawer'),active=rows.find(r=>r.id===opened);
  if(current&&active&&(changed.has(opened)||changed.size&&core.siblings(rows,active).some(r=>changed.has(r.id)))){
    const scroll=current.querySelector('.drawer-body')?.scrollTop||0,replacement=drawer(active);current.replaceWith(replacement);replacement.querySelector('.drawer-body').scrollTop=scroll;
  }
  if(anchor?.id){const row=Array.from(body.children).find(r=>r.dataset.unitId===anchor.id);if(row)wrap.scrollTop+=row.getBoundingClientRect().top-wrap.getBoundingClientRect().top-anchor.offset;else wrap.scrollTop=anchor.scroll;}
  else if(anchor)wrap.scrollTop=anchor.scroll;
  rememberedScroll=wrap.scrollTop;remember();if(anchor?.focus)document.getElementById(anchor.focus)?.focus({preventScroll:true});
  updateFeedNotice();height();
}

function updateFeedNotice(){
  const nav=document.querySelector('.listing nav');if(!nav)return;
  let notice=document.getElementById('orders-update-notice');
  const delayed=feedDelayed||args.statusDelayed;
  if(delayed&&!notice){notice=node('span','Updates delayed · retrying','pending');notice.id='orders-update-notice';nav.append(notice);}
  else if(!delayed&&notice)notice.remove();
}

async function refreshFeed(){
  const context=args.feed;
  if(!context||feedRefreshing||document.hidden||!inView||Date.now()<feedRetryAt)return;
  feedRefreshing=true;const abort=new AbortController();feedAbort=abort;const deadline=setTimeout(()=>abort.abort(),12000);
  try{
    const known=Object.fromEntries((args.rows||[]).filter(r=>r.revision).map(r=>[r.id,r.revision]));
    const response=await fetch('/api/orders/feed',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:context.query,known}),signal:abort.signal});
    if(!response.ok)throw Error('Orders updates delayed');
    const result=await response.json();if(args.feed?.scope!==context.scope)return;
    if(!/^[a-f0-9]{64}$/.test(result.version))throw Error('Invalid Orders revision');
    const anchor=viewportAnchor(),beforeSelection=Array.from(selected).join(),merged=core.mergeDelta(args.rows||[],result,selected,opened);
    args.rows=merged.rows;selected=merged.selected;opened=merged.opened;feedVersion=result.version;feedDelayed=!!result.delayed;feedFailures=0;feedRetryAt=0;
    if(merged.changed.size||result.removed.length||result.order.join()!==(args.order||[]).join())patchLiveListing(merged.changed,anchor);else updateFeedNotice();
    args.order=result.order;
    if(beforeSelection!==Array.from(selected).join())selectionChanged();
    else if(!result.delayed&&args.feed.version!==result.version)event('feed',{scope:context.scope,version:result.version});
  }catch{
    if(args.feed?.scope===context.scope&&!document.hidden){feedDelayed=true;feedFailures=Math.min(3,feedFailures+1);feedRetryAt=Date.now()+Math.min(30000,5000*2**feedFailures);updateFeedNotice();}
  }finally{clearTimeout(deadline);feedRefreshing=false;if(feedAbort===abort)feedAbort=null;}
}

function pollFeed(){if(args.feed&&!feedTimer)feedTimer=setInterval(refreshFeed,5000);}
