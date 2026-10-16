/* Small buttons over the native grid's actual cell bounds. No row/column changes. */
(() => {
 const host=parent,doc=host.document;
 host.SportsCaveEditionReset?.destroy?.();
 const controller=new host.AbortController(),buttons=new Map(),spinners=new Map(),operations=new Map(),permissions=new Map(),inFlight=new Set();
 const requests=host.SportsCaveEditionResetRequests||(host.SportsCaveEditionResetRequests=new Map());
 for(const row of host.SportsCaveEditionStatusState?.rows||[]){permissions.set(row.product_gid,row.reset_allowed===true);operations.set(row.product_gid,row.review_operation?.label);}
 let frame=0,dialog=null,focusBefore=null,resize=null,watched=null;
 const style=doc.createElement('style');style.textContent=`
 .sc-auto-reset{position:fixed;width:20px;height:24px;padding:0;border:0;border-radius:3px;background:var(--background-color,#fff);color:#687387;font:15px system-ui;line-height:24px;text-align:center;cursor:pointer;z-index:2}
 .sc-auto-reset:hover{color:#243145;background:#eef1f5}.sc-auto-reset:disabled{opacity:.35;cursor:default}
 .sc-auto-reset.clipped::before{content:'…';position:absolute;left:-10px;width:10px;background:var(--background-color,#fff);color:#0068c9;font:12px system-ui;line-height:24px;pointer-events:none}
 dialog.sc-auto-reset-confirm{width:230px;max-width:90vw;padding:14px;border:1px solid #d5dae2;border-radius:8px;box-shadow:0 12px 35px #0002;color:#243145;font:13px system-ui}
 dialog.sc-auto-reset-confirm::backdrop{background:rgba(22,30,44,.18)}
 .sc-auto-reset-confirm p{margin:0 0 14px}.sc-auto-reset-confirm div{display:flex;justify-content:flex-end;gap:6px}
 .sc-auto-reset-confirm button{height:28px;padding:3px 10px;background:white;color:#243145;border:1px solid #ccd0d4;border-radius:4px;font:13px system-ui;cursor:pointer}
 .sc-review-spinner{position:fixed;width:10px;height:10px;border:2px solid #dadfdc;border-top-color:#b3963f;border-radius:50%;pointer-events:none;z-index:2;animation:sc-review-spin .9s linear infinite}@keyframes sc-review-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.sc-review-spinner{animation:none}}
 `;doc.head.append(style);
 function close(){dialog?.remove();dialog=null;if(focusBefore?.isConnected)focusBefore.focus({preventScroll:true});focusBefore=null;}
 function clear(){for(const button of buttons.values())button.remove();buttons.clear();for(const spinner of spinners.values())spinner.remove();spinners.clear();}
 function pidFrom(value){try{const url=new URL(value,host.location.href);const pid=url.searchParams.get('product_gid');return url.origin===host.location.origin&&url.pathname==='/auto-editions/status'&&/^gid:\/\/shopify\/Product\/[1-9][0-9]*$/.test(pid||'')?pid:null;}catch{return null;}}
 async function reset(pid){
  if(inFlight.has(pid))return;
  inFlight.add(pid);
  close();
  schedule();
  const key='sc-design-reset:'+pid;
  let id=requests.get(pid);try{id=id||host.sessionStorage.getItem(key);}catch{}
  if(!id)id=host.crypto.randomUUID();requests.set(pid,id);try{host.sessionStorage.setItem(key,id);}catch{}
  try{
   const response=await fetch('/api/auto-editions/status/reset',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({product_gid:pid,request_id:id})});
   if(response.ok){requests.delete(pid);try{host.sessionStorage.removeItem(key);}catch{}}
   else{let data={};try{data=await response.json();}catch{}throw Error(data.error||'Reset could not complete. Retry after the active operation finishes.');}
  }catch(error){
   close();dialog=doc.createElement('dialog');dialog.className='sc-auto-reset-confirm';dialog.setAttribute('aria-label','Reset unavailable');
   const text=doc.createElement('p');text.textContent=error.message||'Reset request interrupted. Retry uses the same saved request identity.';
   const button=doc.createElement('button');button.textContent='Close';button.onclick=close;dialog.append(text,button);doc.body.append(dialog);dialog.showModal();
  }finally{inFlight.delete(pid);host.SportsCaveEditionStatus?.refresh();schedule();}
 }
 function confirm(pid){
  if(dialog||!permissions.get(pid)||inFlight.has(pid))return;
  focusBefore=doc.activeElement;dialog=doc.createElement('dialog');dialog.className='sc-auto-reset-confirm';dialog.setAttribute('aria-label','Reset design?');
  const text=doc.createElement('p');text.textContent='Reset this design and clear its PSD mapping? You must enter the PSD name again using Add. Previous mapping and approval history will be retained.';
  const actions=doc.createElement('div'),cancel=doc.createElement('button'),accept=doc.createElement('button');
  cancel.textContent='Cancel';accept.textContent='Reset';cancel.onclick=close;accept.onclick=()=>reset(pid).catch(()=>{});
  actions.append(cancel,accept);dialog.append(text,actions);doc.body.append(dialog);dialog.showModal();
  dialog.addEventListener('cancel',event=>{event.preventDefault();close();});cancel.focus({preventScroll:true});
 }
 function adapter(canvas){
  // Use the bundled native Glide public getBounds/getCellContent surfaces.
  // Fiber lookup discovers the current ref; never guess row offsets or IDs.
  const key=Object.keys(canvas).find(k=>k.startsWith('__reactFiber'));
  let fiber=key&&canvas[key];
  // React may retain the previous alternate on the DOM node after a commit.
  // Resolve the committed branch before reading any row identity or geometry.
  if(fiber){let root=fiber;while(root.return)root=root.return;
   if(root.stateNode?.current&&root.stateNode.current!==root&&fiber.alternate)fiber=fiber.alternate;}
  for(let n=0;fiber&&n<25;n++,fiber=fiber.return){
   const props=fiber.memoizedProps,api=fiber.ref?.current;
   if(props?.columns&&typeof props.getCellContent==='function'&&typeof api?.getBounds==='function')return {props,api};
  }
  return null;
 }
 function buttonFor(key,pid,bounds,activate){
  let button=buttons.get(key);
  if(!button){button=doc.createElement('button');button.type='button';button.className='sc-auto-reset';button.textContent='↻';button.setAttribute('aria-label','Reset design');
   button.onpointerdown=e=>e.stopPropagation();doc.body.append(button);buttons.set(key,button);}
  button.onclick=e=>{e.preventDefault();e.stopPropagation();activate();};
  button.dataset.productGid=pid;button.disabled=!permissions.get(pid)||inFlight.has(pid);button.style.left=(bounds.x+bounds.width-22)+'px';button.style.top=(bounds.y+(bounds.height-24)/2)+'px';
  return button;
 }
 function paint(){
  frame=0;const workspace=doc.querySelector('.st-key-edition-workspace'),grid=workspace?.querySelector('[data-testid="stDataFrame"]');
  if(!grid||doc.hidden){clear();return;}
  if(watched!==grid){resize?.disconnect();resize=new host.ResizeObserver(schedule);resize.observe(grid);watched=grid;}
  const seen=new Set();let canvasIndex=0;
  for(const canvas of [grid.querySelector('canvas')].filter(Boolean)){
   const model=adapter(canvas);if(!model)continue;
   const {props,api}=model,column=props.columns.findIndex(c=>c.title==='Auto Editions'||/_column-auto_editions-/.test(c.id||''));
   if(column<0)continue;
   const viewport=canvas.getBoundingClientRect(),header=api.getBounds(column,-1),top=Math.max(viewport.top,header?header.y+header.height:viewport.top),start=Math.max(0,props.cellYOffset||0),max=Math.min(props.rows,start+Math.ceil(viewport.height/20)+4);
   for(let row=start;row<max;row++){
    const bounds=api.getBounds(column,row);
    if(!bounds||bounds.y<top||bounds.y+bounds.height>viewport.bottom||bounds.y<0||bounds.y+bounds.height>host.innerHeight||bounds.x+ bounds.width>viewport.right+1||bounds.x+ bounds.width<viewport.left+22)continue;
    const cell=props.getCellContent([column,row]),pid=pidFrom(cell?.data);if(!pid)continue;
    const key=canvasIndex+':'+row;seen.add(key);
    const button=buttonFor(key,pid,bounds,()=>{
     const current=adapter(canvas),box=current?.api.getBounds(column,row);
     if(!box||Math.abs(box.y-bounds.y)>1){schedule();return;}
     // Re-resolve on click so sorting/filtering can never reset a stale product.
     const selected=pidFrom(current.props.getCellContent([column,row])?.data);
     if(selected!==pid){schedule();return;}if(selected)confirm(selected);
    });
    if(operations.get(pid)==='Approving…'){
     let spinner=spinners.get(key);if(!spinner){spinner=doc.createElement('span');spinner.className='sc-review-spinner';spinner.setAttribute('role','status');spinner.setAttribute('aria-label','Approving');doc.body.append(spinner);spinners.set(key,spinner);}
     spinner.style.left=(bounds.x+bounds.width-40)+'px';spinner.style.top=(bounds.y+(bounds.height-14)/2)+'px';
    }else{spinners.get(key)?.remove();spinners.delete(key);}
    button.classList.toggle('clipped' ,canvas.getContext('2d').measureText(cell.displayData||'').width>bounds.width-38);
   }
   canvasIndex++;
  }
  for(const [key,button] of buttons)if(!seen.has(key)){button.remove();buttons.delete(key);}
  for(const [key,spinner] of spinners)if(!seen.has(key)){spinner.remove();spinners.delete(key);}
 }
 function schedule(){if(!frame)frame=host.requestAnimationFrame(paint);}
 addEventListener('message',event=>{
  if(event.source!==host||event.data?.type!=='streamlit:render')return;
  permissions.clear();operations.clear();for(const row of event.data.args?.rows||[]){permissions.set(row.product_gid,row.reset_allowed===true);operations.set(row.product_gid,row.review_operation?.label);}
  schedule();
 },{signal:controller.signal});
 doc.addEventListener('scroll',()=>{clear();schedule();},{capture:true,passive:true,signal:controller.signal});
 host.addEventListener('resize',schedule,{signal:controller.signal});
 doc.addEventListener('visibilitychange',schedule,{signal:controller.signal});
 doc.addEventListener('pointerup',schedule,{capture:true,passive:true,signal:controller.signal});
 doc.addEventListener('keydown',schedule,{capture:true,passive:true,signal:controller.signal});
 const observer=new host.MutationObserver(schedule);const scope=doc.querySelector('.st-key-edition-workspace');if(scope)observer.observe(scope,{childList:true,subtree:true});
 const lifecycle={paint,schedule,destroy(){close();clear();observer.disconnect();resize?.disconnect();controller.abort();style.remove();if(frame)host.cancelAnimationFrame(frame);}};
 host.SportsCaveEditionReset=lifecycle;
 addEventListener('pagehide',()=>{if(host.SportsCaveEditionReset===lifecycle)lifecycle.destroy();},{once:true});
 schedule();
})();
