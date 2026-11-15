/* The existing component widget owns callbacks. Poll only this open picker. */
let discountTimer,discountSearchTimer,discountListSignature='';
function renderDiscountPicker(host,state,emit){
 clearTimeout(discountTimer);const opening=host.hidden&&state?.open;host.hidden=!state?.open;if(host.hidden)return;
 if(!host.dataset.ready){
  host.dataset.ready='1';host.setAttribute('aria-label','Add Discount');
  const heading=document.createElement('div');heading.className='discount-heading';
  const title=document.createElement('strong');title.textContent='Add Discount';
  const close=document.createElement('button');close.type='button';close.textContent='×';close.setAttribute('aria-label','Close discount selector');close.onclick=()=>{clearTimeout(discountSearchTimer);emit('discount_close');};heading.append(title,close);
  const tools=document.createElement('div');tools.className='discount-tools';
  const input=document.createElement('input');input.type='search';input.maxLength=100;input.placeholder='Search Shopify discounts';input.setAttribute('aria-label','Search Shopify discounts');
  const search=()=>{clearTimeout(discountSearchTimer);emit('discount_search',{term:input.value});};
  input.oninput=()=>{clearTimeout(discountSearchTimer);discountSearchTimer=setTimeout(search,350);};input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();search();}};
  const refresh=document.createElement('button');refresh.type='button';refresh.textContent='↻';refresh.setAttribute('aria-label','Refresh discounts');refresh.onclick=()=>emit('discount_refresh',{term:input.value});tools.append(input,refresh);
  const status=document.createElement('p');status.className='discount-status';status.setAttribute('role','status');
  const list=document.createElement('div');list.className='discount-results';list.setAttribute('aria-label','Shopify discount results');
  const pages=document.createElement('div');pages.className='discount-pages';
  host.append(heading,tools,status,list,pages);
 }
 const input=host.querySelector('input');if(document.activeElement!==input)input.value=state.term||'';
 if(opening)requestAnimationFrame(()=>requestAnimationFrame(()=>{
  // Reveal the explicitly opened picker inside the existing scrollable editor,
  // without moving the page or repeating this on search completion.
  try{const frame=window.frameElement,panel=frame?.closest('.st-key-crm-composer-controls');
   if(panel){const below=frame.getBoundingClientRect().top+host.getBoundingClientRect().bottom-panel.getBoundingClientRect().bottom+12;if(below>0)panel.scrollTop+=below;}
  }catch{}
  input.focus({preventScroll:true});
 }));
 const status=host.querySelector('.discount-status');status.textContent=state.error||state.notice||(state.pending?'Loading Shopify discounts…':state.loaded&&!state.rows.length?'No matching codes. For bulk groups, enter the exact code or browse the group by title.':state.group?'Searching codes in '+state.group.title:'Shopify confirms final eligibility at checkout.');status.setAttribute('role',state.error?'alert':'status');
 const signature=JSON.stringify([state.rows,state.pending,state.error]);
 if(signature!==discountListSignature){discountListSignature=signature;const list=host.querySelector('.discount-results'),scroll=list.scrollTop;list.replaceChildren();
  for(const row of state.rows||[]){const item=document.createElement('button');item.type='button';item.className='discount-result';item.disabled=!!(row.unavailable||state.pending||state.error);item.setAttribute('aria-label','Select discount '+row.code);item.title=row.unavailable||row.title;
   const code=document.createElement('strong');code.textContent=row.code;const detail=document.createElement('span');detail.textContent=row.value+' · '+row.label+' · '+row.status.toLowerCase().replace(/^./,c=>c.toUpperCase());item.append(code,detail);
   if(row.unavailable){const reason=document.createElement('small');reason.textContent=row.unavailable;item.append(reason);}
   item.onclick=()=>emit('discount_select',{id:row.id,code:row.code});list.append(item);
  }list.scrollTop=scroll;
 }
 const pages=host.querySelector('.discount-pages');pages.replaceChildren();
 const more=(label,type,extra={})=>{const b=document.createElement('button');b.type='button';b.textContent=label;b.disabled=!!state.pending;b.onclick=()=>emit(type,extra);pages.append(b);};
 if(state.group)more('All discounts','discount_browse');
 if(state.pageInfo?.hasNextPage)more('Load more','discount_next');
 for(const group of state.more_codes||[])more('Browse codes · '+group.title,'discount_codes',{id:group.id});
 if(state.pending)discountTimer=setTimeout(()=>emit('discount_poll'),500);
}
addEventListener('pagehide',()=>{clearTimeout(discountTimer);clearTimeout(discountSearchTimer);});
