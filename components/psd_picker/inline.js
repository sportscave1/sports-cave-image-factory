// Cloud editions run in the parent document, independent of component rerenders.
(function install(){
 const script=parent.document.createElement('script');
 script.textContent='('+function(){
  if(window.SportsCaveAutoEditions)return;
  const jobs=new Map();
  const trace=(stage,id,ms,extra={})=>console.info('AUTO_EDITIONS_CLIENT_TIMINGS',JSON.stringify({stage,allocation:id,ms:Math.round(ms*10)/10,...extra}));
  const textHits=new WeakMap(),immediate=new Map();let clickedText=null;
  const gridSignature=canvas=>[...canvas.querySelectorAll('[role=gridcell]')].map(cell=>cell.textContent).join('|');
  function clearImmediate(id){immediate.get(id)?.remove();immediate.delete(id);}
  function immediateProgress(id){
   if(!clickedText?.canvas.isConnected)return;
   const {canvas,left,top}=clickedText,parent=canvas.parentElement,box=parent.getBoundingClientRect();
   const indicator=document.createElement('span');indicator.className='sc-edition-generating';indicator.textContent='Generating\u2026';indicator.setAttribute('role','status');
   indicator.style.cssText='position:absolute;pointer-events:none;background:white;font:12px system-ui;white-space:nowrap;z-index:2;left:'+(left-box.left)+'px;top:'+(top-box.top)+'px';
   indicator.editionCanvas=canvas;indicator.editionSignature=gridSignature(canvas);
   parent.append(indicator);immediate.set(id,indicator);clickedText=null;
  }
  document.addEventListener('pointerdown',event=>{
   clickedText=null;const canvas=event.target.closest?.('canvas');if(!canvas)return;
   const rect=canvas.getBoundingClientRect();
   for(const hit of (textHits.get(canvas)?.values()||[])){
    const left=rect.left+hit.x*rect.width/canvas.width,top=rect.top+hit.y*rect.height/canvas.height-10;
    if(event.clientX>=left-4&&event.clientX<=left+hit.width*rect.width/canvas.width+4&&event.clientY>=top-4&&event.clientY<=top+20)clickedText={canvas,left,top};
   }
  },true);
  // A scrolled/sorted table must never leave an indicator over a different unit.
  document.addEventListener('scroll',()=>{for(const id of immediate.keys())clearImmediate(id);},true);
  const url=(path,id,job)=>path+'?allocation_id='+encodeURIComponent(id)+(job?'&job_id='+encodeURIComponent(job):'');
  async function api(path,id,post=false,job){const began=performance.now();const r=await fetch(url(path,id,job),post?{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}:{});const d=await r.json();trace(path.split('/').pop(),id,performance.now()-began,{status:r.status,server:d.timings});if(!r.ok)throw Error(d.error||'Unavailable');return d;}
  function anchors(id){return [...document.querySelectorAll('a[href]')].filter(a=>{try{const u=new URL(a.href);return u.origin===location.origin&&['/auto-editions/download','/auto-editions/open','/auto-editions/view'].includes(u.pathname)&&u.searchParams.get('allocation_id')===id;}catch{return false;}});}
  function paint(id,row){const marker=immediate.get(id);if(marker&&!['Generating','Queued'].includes(row.status)){
   marker.classList.remove('sc-edition-generating');const markerLabel=row.status==='Ready'?'Open':'Retry';if(marker.textContent!==markerLabel)marker.textContent=markerLabel;
   marker.style.pointerEvents='auto';marker.style.cursor='pointer';marker.setAttribute('role','link');marker.tabIndex=0;
   const activate=()=>row.status==='Ready'?openSaved(url('/auto-editions/open',id,row.job_id)):start(url('/auto-editions/download',id)+'#Retry');
   marker.onclick=activate;marker.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();activate();}};
  }for(const a of anchors(id)){
   const saved=['Ready','Unavailable'].includes(row.status),busy=['Generating','Queued'].includes(row.status);
   const label=row.status==='Ready'?'Open':row.status==='Unavailable'?'Retry Open':row.status==='Blocked'?'Retry':busy?'Generating\u2026':'Download JPG';
   if(a.textContent!==label)a.textContent=label;a.classList.toggle('sc-edition-generating',busy);
   a.title=row.error||label;
   a.href=url(saved?'/auto-editions/open':'/auto-editions/download',id,saved?row.job_id:null)+'#'+(saved?'Open':row.status==='Blocked'?'Retry':busy?'Generating':'Download JPG');
  }}
  function showError(id,row){
   document.getElementById('sc-edition-error')?.remove();
   const box=document.createElement('div');box.id='sc-edition-error';box.setAttribute('role','alert');box.style.cssText='position:fixed;bottom:18px;right:18px;max-width:360px;padding:12px;background:white;border:1px solid #ccd2dc;border-radius:8px;font:13px system-ui;z-index:9999';
   const message=document.createElement('span');message.textContent=row.error||'Saved JPG unavailable. Retry Open.';box.append(message);
   const close=document.createElement('button');close.textContent='Dismiss';close.onclick=()=>box.remove();box.append(close);document.body.append(box);
  }
  function navigateSaved(id,row){if(!window.SportsCaveFilesWindow)throw Error('Files navigation is loading. Retry Open.');const began=performance.now();window.SportsCaveFilesWindow.open({allocation:id,job:row.job_id});trace('popup_handoff',id,performance.now()-began);}
  function initiateDownload(id,row){const key='sc-edition-attempt:'+row.job_id;if(sessionStorage.getItem(key))return;sessionStorage.setItem(key,'1');
   const a=document.createElement('a');a.href=url('/api/auto-editions/file',id,row.job_id);a.download=row.filename||'edition-TEST-NOT-PRINT-READY.jpg';document.body.append(a);a.click();a.remove();if(row.clickedAt)trace('download_initiated',id,performance.now()-row.clickedAt);
  }
  async function openSaved(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id'),job=u.searchParams.get('job_id');
   const row={status:'Ready',job_id:job};jobs.set(id,row);
   try{navigateSaved(id,row);paint(id,row);}
   catch(e){row.status='Unavailable';row.error=e.message;paint(id,row);showError(id,row);}
  }
  async function poll(id){const row=jobs.get(id);if(!row||row.polling)return;row.polling=true;
   try{const d=await api('/api/auto-editions/state',id,false,row.job_id);Object.assign(row,d);paint(id,row);
    if(d.status==='Ready'){if(sessionStorage.getItem('sc-edition-pending:'+id)){initiateDownload(id,row);navigateSaved(id,row);sessionStorage.removeItem('sc-edition-pending:'+id);}}
    else if(d.status==='Blocked'){sessionStorage.removeItem('sc-edition-pending:'+id);}
   }catch(e){row.status=row.job_id?'Unavailable':'Blocked';row.error=e.message;paint(id,row);showError(id,row);}finally{row.polling=false;}
  }
  async function start(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id');if(!/^\d+$/.test(id||''))return;
   const old=jobs.get(id);if(old?.status==='Generating'||old?.status==='Queued')return;
   if(old?.status==='Ready'){openSaved(url('/auto-editions/open',id,old.job_id));return;}
   const row={status:'Generating',clickedAt:performance.now()};jobs.set(id,row);paint(id,row);sessionStorage.setItem('sc-edition-pending:'+id,'1');
   immediateProgress(id);
   trace('inline_feedback',id,performance.now()-row.clickedAt);
   try{const d=await api(u.hash==='#Retry'?'/api/auto-editions/retry':'/api/auto-editions/start',id,true);Object.assign(row,d);sessionStorage.removeItem('sc-edition-attempt:'+d.job_id);paint(id,row);await poll(id);}
   catch(e){row.status='Blocked';row.error=e.message;paint(id,row);showError(id,row);sessionStorage.removeItem('sc-edition-pending:'+id);}
  }
  function hydrate(){for(const [id,node] of immediate)if(!node.isConnected||gridSignature(node.editionCanvas)!==node.editionSignature)clearImmediate(id);
   for(const cell of document.querySelectorAll('canvas [role=gridcell]')){const value=cell.textContent;if(!value.startsWith('/auto-editions/download?')||!value.endsWith('#Generating'))continue;const id=new URL(value,location.href).searchParams.get('allocation_id');if(id&&!jobs.has(id)){jobs.set(id,{status:'Generating'});poll(id);}}
   for(const a of document.querySelectorAll('a[href*="/auto-editions/"]')){const u=new URL(a.href),id=u.searchParams.get('allocation_id');if(!id||jobs.has(id))continue;
    if(['/auto-editions/open','/auto-editions/view'].includes(u.pathname)){jobs.set(id,{status:'Ready',job_id:u.searchParams.get('job_id')});}
    else if(u.hash==='#Generating'||sessionStorage.getItem('sc-edition-pending:'+id)){jobs.set(id,{status:'Generating'});poll(id);}}
   for(const [id,row] of jobs)paint(id,row);
   for(let i=0;i<sessionStorage.length;i++){const k=sessionStorage.key(i);if(k?.startsWith('sc-edition-pending:')){const id=k.split(':').pop();if(!jobs.has(id)){jobs.set(id,{status:'Generating'});poll(id);}}}
  }
  setInterval(()=>{for(const [id,row] of jobs)if(['Generating','Queued'].includes(row.status))poll(id);},2500);
  let scheduled=false;new MutationObserver(()=>{if(!scheduled){scheduled=true;setTimeout(()=>{scheduled=false;hydrate();},100);}}).observe(document.body,{childList:true,subtree:true});
  const style=document.createElement('style');style.textContent='.sc-edition-generating::before{content:"";display:inline-block;width:10px;height:10px;border:2px solid #bbb;border-top-color:#4f65a0;border-radius:50%;animation:sc-spin .8s linear infinite;margin-right:5px}@keyframes sc-spin{to{transform:rotate(360deg)}}';document.head.append(style);
  // Streamlit renders desktop LinkColumns on canvas. Add only a visual,
  // pointer-transparent activity indicator at the renderer's actual text bounds.
  // No column widths, row offsets or allocation identities are guessed.
  const context=CanvasRenderingContext2D.prototype,originalFill=context.fillText,originalClear=context.clearRect;
  const indicators=new WeakMap();
  context.clearRect=function(...args){textHits.delete(this.canvas);const items=indicators.get(this.canvas);if(items){for(const item of items.values())item.remove();items.clear();}return originalClear.apply(this,args);};
  context.fillText=function(text,x,y,...args){const result=originalFill.call(this,text,x,y,...args);if(text!=='Generating'){const old=indicators.get(this.canvas);old?.get(x+':'+y)?.remove();old?.delete(x+':'+y);}
   if(['Download JPG','Retry','Generating'].includes(text)&&this.canvas.closest('[data-testid="stDataFrame"]')){
    const transform=this.getTransform(),point=transform.transformPoint(new DOMPoint(x,y));let hits=textHits.get(this.canvas);if(!hits){hits=new Map();textHits.set(this.canvas,hits);}
    hits.set(x+':'+y,{x:point.x,y:point.y,width:this.measureText(text).width*transform.a});
   }
   if(text==='Generating'&&this.canvas.closest('[data-testid="stDataFrame"]')){
    const canvas=this.canvas,parent=canvas.parentElement,rect=canvas.getBoundingClientRect(),box=parent.getBoundingClientRect(),point=this.getTransform().transformPoint(new DOMPoint(x,y));
    const key=x+':'+y;let items=indicators.get(canvas);if(!items){items=new Map();indicators.set(canvas,items);}let indicator=items.get(key);
    if(!indicator){indicator=document.createElement('span');indicator.className='sc-edition-generating';indicator.textContent='Generating\u2026';indicator.setAttribute('role','status');parent.append(indicator);items.set(key,indicator);}
    indicator.style.cssText='position:absolute;pointer-events:none;background:white;font:12px system-ui;white-space:nowrap;z-index:2;left:'+(rect.left-box.left+point.x*rect.width/canvas.width)+'px;top:'+(rect.top-box.top+point.y*rect.height/canvas.height-9)+'px';
   }return result;
  };
  // Streamlit can retire the bridge iframe while a cloud job is running.
  // Keep cloud link handling in this document and treat its refresh callback
  // as optional; a stale iframe must not turn a saved JPG into an error.
  function cloudAction(value){try{const u=new URL(value,location.href);if(u.origin!==location.origin)return false;
   if(u.pathname==='/auto-editions/download'){start(u.href);return true;}
   if(['/auto-editions/open','/auto-editions/view'].includes(u.pathname)){openSaved(u.href);return true;}
  }catch{}return false;}
  const nativeOpen=window.open;window.open=function(value,...args){if(cloudAction(value))return null;return nativeOpen.call(this,value,...args);};
  document.addEventListener('click',event=>{const link=event.target.closest?.('a[href]');if(link&&cloudAction(link.href)){event.preventDefault();event.stopImmediatePropagation();}},true);
  window.SportsCaveAutoEditions={start,openSaved,connect(){hydrate();}};
 }.toString()+')();';parent.document.head.append(script);script.remove();
})();
