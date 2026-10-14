// Cloud editions run in the parent document, independent of component rerenders.
(function install(){
 const script=parent.document.createElement('script');
 script.textContent='('+function(){
  if(window.SportsCaveAutoEditions)return;
  const jobs=new Map();let notify=()=>{};
  const nativeOpen=window.open.bind(window);
  const url=(path,id,job)=>path+'?allocation_id='+encodeURIComponent(id)+(job?'&job_id='+encodeURIComponent(job):'');
  async function api(path,id,post=false,job){const r=await fetch(url(path,id,job),post?{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'Unavailable');return d;}
  function anchors(id){return [...document.querySelectorAll('a[href]')].filter(a=>{try{const u=new URL(a.href);return u.origin===location.origin&&u.pathname.startsWith('/auto-editions/')&&u.searchParams.get('allocation_id')===id;}catch{return false;}});}
  function paint(id,row){for(const a of anchors(id)){
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
  function reserve(id){try{return nativeOpen('about:blank','sc-edition-file-'+id);}catch{return null;}}
  function navigateSaved(id,row){if(row.popup&&!row.popup.closed){row.popup.location.replace(url('/auto-editions/open',id,row.job_id));row.popup=null;}}
  function initiateDownload(id,row){const key='sc-edition-attempt:'+row.job_id;if(sessionStorage.getItem(key))return;sessionStorage.setItem(key,'1');
   const a=document.createElement('a');a.href=url('/api/auto-editions/file',id,row.job_id);a.download=row.filename||'edition-TEST-NOT-PRINT-READY.jpg';document.body.append(a);a.click();a.remove();
  }
  async function openSaved(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id'),job=u.searchParams.get('job_id');
   const row={status:'Ready',job_id:job,popup:reserve(id)};jobs.set(id,row);
   try{await api('/api/auto-editions/location',id,false,job);navigateSaved(id,row);paint(id,row);}
   catch(e){row.popup?.close();row.popup=null;row.status='Unavailable';row.error=e.message;paint(id,row);showError(id,row);}
  }
  async function poll(id){const row=jobs.get(id);if(!row||row.polling)return;row.polling=true;
   try{const d=await api('/api/auto-editions/state',id);Object.assign(row,d);paint(id,row);
    if(d.status==='Ready'){if(sessionStorage.getItem('sc-edition-pending:'+id)){initiateDownload(id,row);navigateSaved(id,row);sessionStorage.removeItem('sc-edition-pending:'+id);}notify();}
    else if(d.status==='Blocked'){row.popup?.close();row.popup=null;sessionStorage.removeItem('sc-edition-pending:'+id);notify();}
   }catch(e){row.popup?.close();row.popup=null;row.status=row.job_id?'Unavailable':'Blocked';row.error=e.message;paint(id,row);showError(id,row);}finally{row.polling=false;}
  }
  async function start(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id');if(!/^\d+$/.test(id||''))return;
   const old=jobs.get(id);if(old?.status==='Generating'||old?.status==='Queued')return;
   const row={status:'Generating',popup:reserve(id)};jobs.set(id,row);paint(id,row);sessionStorage.setItem('sc-edition-pending:'+id,'1');
   notify();
   try{const d=await api(u.hash==='#Retry'?'/api/auto-editions/retry':'/api/auto-editions/start',id,true);Object.assign(row,d);sessionStorage.removeItem('sc-edition-attempt:'+d.job_id);paint(id,row);notify();await poll(id);}
   catch(e){row.popup?.close();row.popup=null;row.status='Blocked';row.error=e.message;paint(id,row);showError(id,row);sessionStorage.removeItem('sc-edition-pending:'+id);}
  }
  function hydrate(){for(const cell of document.querySelectorAll('canvas [role=gridcell]')){const value=cell.textContent;if(!value.startsWith('/auto-editions/download?')||!value.endsWith('#Generating'))continue;const id=new URL(value,location.href).searchParams.get('allocation_id');if(id&&!jobs.has(id)){jobs.set(id,{status:'Generating'});poll(id);}}
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
  context.clearRect=function(...args){const items=indicators.get(this.canvas);if(items){for(const item of items.values())item.remove();items.clear();}return originalClear.apply(this,args);};
  context.fillText=function(text,x,y,...args){const result=originalFill.call(this,text,x,y,...args);if(text!=='Generating'){const old=indicators.get(this.canvas);old?.get(x+':'+y)?.remove();old?.delete(x+':'+y);}
   if(text==='Generating'&&this.canvas.closest('[data-testid="stDataFrame"]')){
    const canvas=this.canvas,parent=canvas.parentElement,rect=canvas.getBoundingClientRect(),box=parent.getBoundingClientRect(),point=this.getTransform().transformPoint(new DOMPoint(x,y));
    const key=x+':'+y;let items=indicators.get(canvas);if(!items){items=new Map();indicators.set(canvas,items);}let indicator=items.get(key);
    if(!indicator){indicator=document.createElement('span');indicator.className='sc-edition-generating';indicator.textContent='Generating\u2026';indicator.setAttribute('role','status');parent.append(indicator);items.set(key,indicator);}
    indicator.style.cssText='position:absolute;pointer-events:none;background:white;font:12px system-ui;white-space:nowrap;z-index:2;left:'+(rect.left-box.left+point.x*rect.width/canvas.width)+'px;top:'+(rect.top-box.top+point.y*rect.height/canvas.height-9)+'px';
   }return result;
  };
  window.SportsCaveAutoEditions={start,openSaved,connect(fn){notify=fn;hydrate();}};
 }.toString()+')();';parent.document.head.append(script);script.remove();
})();
