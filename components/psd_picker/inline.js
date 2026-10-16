// Cloud editions run in the parent document, independent of component rerenders.
(function install(){
 const script=parent.document.createElement('script');
 script.textContent='('+function(){
  if(window.SportsCaveAutoEditions)return;
  const jobs=new Map(),requests=new Map();let departed=false;
  const saved=key=>{try{return sessionStorage.getItem(key);}catch{return null;}};
  const remember=(key,value)=>{try{sessionStorage.setItem(key,value);}catch{}};
  const forget=key=>{try{sessionStorage.removeItem(key);}catch{}};
  const trace=(stage,id,ms,extra={})=>console.info('AUTO_EDITIONS_CLIENT_TIMINGS',JSON.stringify({stage,allocation:id,ms:Math.round(ms*10)/10,...extra}));
  const textHits=new WeakMap(),immediate=new Map();let clickedText=null;
  const gridSignature=canvas=>[...canvas.querySelectorAll('[role=gridcell]')].map(cell=>cell.textContent).join('|');
  function clearImmediate(id){immediate.get(id)?.remove();immediate.delete(id);}
  function immediateProgress(id){
   if(!clickedText?.canvas.isConnected)return;
   const {canvas,left,top}=clickedText,parent=canvas.parentElement,box=parent.getBoundingClientRect();
   const indicator=document.createElement('span');indicator.className='sc-edition-generating';indicator.textContent='Preparing JPG\u2026';indicator.setAttribute('role','status');
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
  async function api(path,id,post=false,job){
   const began=performance.now(),controller=new AbortController();requests.set(controller,id);
   const timer=setTimeout(()=>controller.abort(),20000);
   try{const r=await fetch(url(path,id,job),{credentials:'same-origin',signal:controller.signal,...(post?{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}:{})});
    const d=await r.json();trace(path.split('/').pop(),id,performance.now()-began,{status:r.status,server:d.timings});if(!r.ok)throw Error(d.error||'Unavailable');return d;
   }catch(error){if(error.name==='AbortError'&&!departed)throw Error('JPG preparation request timed out. Retry to check the same download.');throw error;}
   finally{clearTimeout(timer);requests.delete(controller);}
  }
  function feedback(id,row){
   if(!row.feedback){document.getElementById('sc-jpg-progress-'+id)?.remove();return;}
   let container=document.getElementById('sc-jpg-progress');if(!container){container=document.createElement('div');container.id='sc-jpg-progress';container.style.cssText='position:fixed;bottom:18px;right:18px;max-width:340px;display:flex;flex-direction:column;gap:6px;z-index:9999;pointer-events:none';document.body.append(container);}
   let node=document.getElementById('sc-jpg-progress-'+id);if(!node){node=document.createElement('div');node.id='sc-jpg-progress-'+id;node.setAttribute('role','status');node.setAttribute('aria-live','polite');node.style.cssText='background:white;border:1px solid #ccd2dc;border-radius:6px;padding:8px 10px;font:13px system-ui';container.append(node);}
   if(node.textContent!==row.feedback)node.textContent=row.feedback;
   node.classList.toggle('sc-edition-generating',!!row.starting||!!row.transferring||['Generating','Queued'].includes(row.status));
   if(row.feedback==='Download started'){clearTimeout(row.feedbackTimer);row.feedbackTimer=setTimeout(()=>{row.feedback='';node.remove();},10000);}
  }
  function anchors(id){return [...document.querySelectorAll('a[href]')].filter(a=>{try{const u=new URL(a.href);return u.origin===location.origin&&['/auto-editions/download','/auto-editions/open','/auto-editions/view'].includes(u.pathname)&&u.searchParams.get('allocation_id')===id;}catch{return false;}});}
  function paint(id,row){
   const busy=row.starting||row.transferring||['Generating','Queued'].includes(row.status),label=busy?(row.transferring?'Downloading\u2026':'Preparing JPG\u2026'):row.downloadError?'Retry':row.status==='Ready'?'Open':row.status==='Unavailable'?'Retry Open':row.status==='Blocked'?'Retry':'Download JPG';
   const marker=immediate.get(id);if(marker){
    marker.classList.toggle('sc-edition-generating',!!busy);if(marker.textContent!==label)marker.textContent=label;
    marker.style.pointerEvents=busy?'none':'auto';marker.style.cursor=busy?'default':'pointer';marker.setAttribute('role',busy?'status':'link');marker.tabIndex=busy?-1:0;
    const activate=()=>row.status==='Ready'&&!row.downloadError?openSaved(url('/auto-editions/open',id,row.job_id)):start(url('/auto-editions/download',id)+'#Retry');
    marker.onclick=activate;marker.onkeydown=e=>{if(e.key==='Enter'&&!busy){e.preventDefault();activate();}};
   }
   for(const a of anchors(id)){
    const retained=['Ready','Unavailable'].includes(row.status)&&!row.downloadError;
    if(a.textContent!==label)a.textContent=label;a.classList.toggle('sc-edition-generating',!!busy);a.setAttribute('aria-disabled',String(!!busy));a.setAttribute('aria-busy',String(!!busy));
    a.title=row.error||row.feedback||label;
    a.href=url(retained?'/auto-editions/open':'/auto-editions/download',id,retained?row.job_id:null)+'#'+(retained?'Open':row.status==='Blocked'||row.downloadError?'Retry':busy?'Generating':'Download JPG');
   }
   feedback(id,row);
  }
  function showError(id,row){
   document.getElementById('sc-edition-error')?.remove();
   const box=document.createElement('div');box.id='sc-edition-error';box.dataset.allocation=id;box.setAttribute('role','alert');box.style.cssText='position:fixed;bottom:18px;right:18px;max-width:360px;padding:12px;background:white;border:1px solid #ccd2dc;border-radius:8px;font:13px system-ui;z-index:9999';
   const message=document.createElement('span');message.textContent=row.error||'Saved JPG unavailable. Retry Open.';box.append(message);
   const retry=document.createElement('button');retry.textContent=row.downloadError?'Retry download':row.openError?'Retry Open':'Retry';retry.onclick=()=>{box.remove();if(row.openError)openSaved(url('/auto-editions/open',id,row.job_id));else start(row.retryURL||url('/auto-editions/download',id)+'#Retry');};box.append(retry);
   const close=document.createElement('button');close.textContent='Dismiss';close.onclick=()=>box.remove();box.append(close);document.body.append(box);
  }
  function navigateSaved(id,row){if(!window.SportsCaveFilesWindow)throw Error('Files navigation is loading. Retry Open.');const began=performance.now();window.SportsCaveFilesWindow.open({allocation:id,job:row.job_id});trace('popup_handoff',id,performance.now()-began);}
  async function initiateDownload(id,row){
   if(row.delivery)return row.delivery;
   const key='sc-edition-handoff:'+row.job_id;if(saved(key))return;
   row.transferring=true;row.downloadError=false;row.error='';row.feedback='Downloading\u2026';paint(id,row);
   row.delivery=new Promise((resolve,reject)=>{
    const token=Array.from(crypto.getRandomValues(new Uint8Array(16)),n=>n.toString(16).padStart(2,'0')).join(''),cookie='sc-jpg-'+token;
    const frame=document.createElement('iframe');frame.name='sc-jpg-'+token;frame.hidden=true;frame.setAttribute('aria-hidden','true');frame.title='JPG download delivery';
    let finished=false,timer,poll;
    const clearCookie=()=>{document.cookie=cookie+'=; Max-Age=0; Path=/; SameSite=Strict'+(location.protocol==='https:'?'; Secure':'');};
    const failMessage=()=>{try{const text=frame.contentDocument?.body?.textContent||'';if(text.length<4096)return JSON.parse(text).error;}catch{}return null;};
    const finish=error=>{if(finished)return;finished=true;clearTimeout(timer);clearInterval(poll);frame.onload=null;frame.remove();clearCookie();delete row.cancelDelivery;
     if(error)reject(error);else{remember(key,'1');resolve();}
    };
    row.cancelDelivery=()=>finish(new DOMException('Download cancelled on navigation','AbortError'));
    frame.onload=()=>{const error=failMessage();if(error)finish(Error(error));};
    timer=setTimeout(()=>finish(Error('JPG download did not start in time. Retry download. Check the browser download list before retrying.')),120000);
    poll=setInterval(()=>{const entry=document.cookie.split('; ').find(v=>v.startsWith(cookie+'='));if(!entry)return;
     if(entry.slice(cookie.length+1)==='started')finish();else finish(Error(failMessage()||'JPG transfer failed. Retry download.'));
    },100);
    document.body.append(frame);
    const a=document.createElement('a');a.href=url('/api/auto-editions/file',id,row.job_id)+'&download_token='+token;a.target=frame.name;a.download=row.filename||'edition-TEST-NOT-PRINT-READY.jpg';document.body.append(a);a.click();a.remove();
   });
   try{await row.delivery;if(departed)return;row.feedback='Download started';if(row.clickedAt)trace('download_initiated',id,performance.now()-row.clickedAt);}
   catch(error){row.downloadError=!(departed||row.cancelled);row.feedback='';forget(key);throw error;}
   finally{row.transferring=false;row.delivery=null;document.getElementById('sc-jpg-progress-'+id)?.remove();if(!departed)paint(id,row);}
  }
  async function openSaved(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id'),job=u.searchParams.get('job_id');
   if(jobs.get(id)?.transferring||jobs.get(id)?.starting)return;
   const row={status:'Ready',job_id:job};jobs.set(id,row);
   try{navigateSaved(id,row);paint(id,row);}
   catch(e){row.status='Unavailable';row.openError=true;row.error=e.message;paint(id,row);showError(id,row);}
  }
  async function poll(id){const row=jobs.get(id);if(!row||row.polling||row.starting)return;row.polling=true;
   try{if(row.deadline&&performance.now()>row.deadline)throw Error('JPG preparation is taking longer than expected. Retry to check the same job.');const d=await api('/api/auto-editions/state',id,false,row.job_id);if(departed||row.cancelled)return;Object.assign(row,d);paint(id,row);
    if(d.status==='Ready'){if(row.clickedAt)trace('ready_observed',id,performance.now()-row.clickedAt);if(row.pending||saved('sc-edition-pending:'+id)){await initiateDownload(id,row);if(departed||row.cancelled)return;row.pending=false;forget('sc-edition-pending:'+id);try{navigateSaved(id,row);}catch(e){row.status='Unavailable';row.openError=true;row.error='Download started. '+e.message;paint(id,row);showError(id,row);}}else{row.feedback='';paint(id,row);}}
    else if(d.status==='Blocked'){row.feedback='';row.error='JPG preparation is blocked. Review the artwork, then retry.';forget('sc-edition-pending:'+id);paint(id,row);showError(id,row);}
   }catch(e){if(departed||row.cancelled)return;row.feedback='';forget('sc-edition-pending:'+id);row.status=row.downloadError?'Ready':'Blocked';row.requestError=!row.downloadError;row.error=e.message;paint(id,row);showError(id,row);}finally{row.polling=false;}
  }
  async function start(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id');if(!/^\d+$/.test(id||''))return;
   const old=jobs.get(id);if(old?.starting||old?.transferring||old?.status==='Generating'||old?.status==='Queued')return;
   if(old?.downloadError){try{await initiateDownload(id,old);if(departed||old.cancelled)return;forget('sc-edition-pending:'+id);try{navigateSaved(id,old);}catch(e){old.status='Unavailable';old.openError=true;old.error='Download started. '+e.message;paint(id,old);showError(id,old);}}catch(e){if(!departed&&!old.cancelled){old.error=e.message;paint(id,old);showError(id,old);}}return;}
   if(old?.status==='Ready'){openSaved(url('/auto-editions/open',id,old.job_id));return;}
   const row={status:'Generating',starting:true,pending:true,feedback:'Preparing JPG\u2026',ownerPage:new URLSearchParams(location.search).get('page'),retryURL:value,clickedAt:performance.now(),deadline:performance.now()+360000};jobs.set(id,row);paint(id,row);remember('sc-edition-pending:'+id,'1');
   immediateProgress(id);
   trace('inline_feedback',id,performance.now()-row.clickedAt);
   try{const d=await api(u.hash==='#Retry'&&!old?.requestError?'/api/auto-editions/retry':'/api/auto-editions/start',id,true);if(departed||row.cancelled)return;Object.assign(row,d);row.starting=false;forget('sc-edition-handoff:'+d.job_id);paint(id,row);await poll(id);}
   catch(e){if(departed||row.cancelled)return;row.starting=false;row.feedback='';row.status='Blocked';row.requestError=true;row.error=e.message;paint(id,row);showError(id,row);forget('sc-edition-pending:'+id);}
  }
  function hydrate(){
   for(const [id,row] of jobs)if(row.ownerPage!==undefined&&row.ownerPage!==new URLSearchParams(location.search).get('page')){row.cancelled=true;row.cancelDelivery?.();clearTimeout(row.feedbackTimer);forget('sc-edition-pending:'+id);clearImmediate(id);document.getElementById('sc-jpg-progress-'+id)?.remove();const error=document.getElementById('sc-edition-error');if(error?.dataset.allocation===id)error.remove();jobs.delete(id);for(const [controller,requestId] of requests)if(requestId===id)controller.abort();}
   for(const [id,node] of immediate)if(!node.isConnected||gridSignature(node.editionCanvas)!==node.editionSignature)clearImmediate(id);
   for(const cell of document.querySelectorAll('canvas [role=gridcell]')){const value=cell.textContent;if(!value.startsWith('/auto-editions/download?')||!value.endsWith('#Generating'))continue;const id=new URL(value,location.href).searchParams.get('allocation_id');if(id&&!jobs.has(id)){jobs.set(id,{status:'Generating',feedback:'Preparing JPG\u2026',ownerPage:new URLSearchParams(location.search).get('page'),deadline:performance.now()+360000});poll(id);}}
   for(const a of document.querySelectorAll('a[href*="/auto-editions/"]')){const u=new URL(a.href),id=u.searchParams.get('allocation_id');if(!id||jobs.has(id))continue;
    if(['/auto-editions/open','/auto-editions/view'].includes(u.pathname)){jobs.set(id,{status:'Ready',job_id:u.searchParams.get('job_id')});}
    else if(u.hash==='#Generating'||saved('sc-edition-pending:'+id)){jobs.set(id,{status:'Generating',feedback:'Preparing JPG\u2026',ownerPage:new URLSearchParams(location.search).get('page'),deadline:performance.now()+360000});poll(id);}}
   for(const [id,row] of jobs)paint(id,row);
   try{for(let i=0;i<sessionStorage.length;i++){const k=sessionStorage.key(i);if(k?.startsWith('sc-edition-pending:')){const id=k.split(':').pop();if(!jobs.has(id)){jobs.set(id,{status:'Generating',feedback:'Preparing JPG\u2026',ownerPage:new URLSearchParams(location.search).get('page'),deadline:performance.now()+360000});poll(id);}}}}catch{}
  }
  const polling=setInterval(()=>{for(const [id,row] of jobs)if(['Generating','Queued'].includes(row.status))poll(id);},750);
  let scheduled=false;const observer=new MutationObserver(()=>{if(!scheduled){scheduled=true;setTimeout(()=>{scheduled=false;hydrate();},100);}});observer.observe(document.body,{childList:true,subtree:true});
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
    if(!indicator){indicator=document.createElement('span');indicator.className='sc-edition-generating';indicator.textContent='Preparing JPG\u2026';indicator.setAttribute('role','status');parent.append(indicator);items.set(key,indicator);}
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
  addEventListener('pagehide',()=>{departed=true;clearInterval(polling);observer.disconnect();for(const controller of requests.keys())controller.abort();for(const [id,row] of jobs){row.cancelled=true;forget('sc-edition-pending:'+id);row.cancelDelivery?.();clearTimeout(row.feedbackTimer);}},{once:true});
  window.SportsCaveAutoEditions={start,openSaved,connect(){hydrate();}};
 }.toString()+')();';parent.document.head.append(script);script.remove();
})();
