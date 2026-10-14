// Cloud editions run in the parent document, independent of component rerenders.
(function install(){
 const script=parent.document.createElement('script');
 script.textContent='('+function(){
  if(window.SportsCaveAutoEditions)return;
  const jobs=new Map();let notify=()=>{},openView=()=>{};
  const url=(path,id,job)=>path+'?allocation_id='+encodeURIComponent(id)+(job?'&job_id='+encodeURIComponent(job):'');
  async function api(path,id,post=false){const r=await fetch(url(path,id),post?{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'Unavailable');return d;}
  function anchors(id){return [...document.querySelectorAll('a[href]')].filter(a=>{if(a.classList.contains('sc-edition-again'))return false;try{const u=new URL(a.href);return u.origin===location.origin&&u.pathname.startsWith('/auto-editions/')&&u.searchParams.get('allocation_id')===id;}catch{return false;}});}
  function paint(id,row){for(const a of anchors(id)){if(!/\/(download|view)$/.test(new URL(a.href).pathname))continue;
   const label=row.status==='Ready'?'View':row.status==='Blocked'?'Retry':'Generating…';
   if(a.textContent!==label)a.textContent=label;a.classList.toggle('sc-edition-generating',label==='Generating…');
   a.title=row.status==='Blocked'?'Generation unavailable. Retry safely.':label;
   a.href=url(row.status==='Ready'?'/auto-editions/view':'/auto-editions/download',id,row.status==='Ready'?row.job_id:null)+'#'+(row.status==='Ready'?'View':row.status==='Blocked'?'Retry':'Generating');
   if(row.status==='Ready'&&!a.nextElementSibling?.classList.contains('sc-edition-again')){const b=document.createElement('a');b.className='sc-edition-again';b.textContent='Download';b.href=url('/auto-editions/download',id)+'#Download JPG';b.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();start(b.href);});b.style.cssText='font-size:11px;margin-left:7px';a.after(b);}
  }}
  function initiateDownload(id,row){const key='sc-edition-attempt:'+row.job_id;if(sessionStorage.getItem(key))return;sessionStorage.setItem(key,'1');
   const a=document.createElement('a');a.href=url('/api/auto-editions/file',id,row.job_id);a.download=row.filename||'edition-TEST-NOT-PRINT-READY.jpg';document.body.append(a);a.click();a.remove();
   // This records initiation only; it never asserts a successful local save.
  }
  async function poll(id){const row=jobs.get(id);if(!row||row.polling)return;row.polling=true;
   try{const d=await api('/api/auto-editions/state',id);Object.assign(row,d);paint(id,row);
    if(d.status==='Ready'){if(sessionStorage.getItem('sc-edition-pending:'+id)){initiateDownload(id,row);sessionStorage.removeItem('sc-edition-pending:'+id);}notify();}
    else if(d.status==='Blocked'){sessionStorage.removeItem('sc-edition-pending:'+id);notify();}
   }catch(e){row.status='Blocked';row.error=e.message;paint(id,row);}finally{row.polling=false;}
  }
  async function start(value){const u=new URL(value,location.href),id=u.searchParams.get('allocation_id');if(!/^\d+$/.test(id||''))return;
   const old=jobs.get(id);if(old?.status==='Generating'||old?.status==='Queued')return;
   const row={status:'Generating'};jobs.set(id,row);paint(id,row);sessionStorage.setItem('sc-edition-pending:'+id,'1');
   try{const d=await api(u.hash==='#Retry'?'/api/auto-editions/retry':'/api/auto-editions/start',id,true);Object.assign(row,d);sessionStorage.removeItem('sc-edition-attempt:'+d.job_id);paint(id,row);notify();await poll(id);}
   catch(e){row.status='Blocked';paint(id,row);sessionStorage.removeItem('sc-edition-pending:'+id);}
  }
  function hydrate(){for(const cell of document.querySelectorAll('canvas [role=gridcell]')){const value=cell.textContent;if(!value.startsWith('/auto-editions/download?')||!value.endsWith('#Generating'))continue;const id=new URL(value,location.href).searchParams.get('allocation_id');if(id&&!jobs.has(id)){jobs.set(id,{status:'Generating'});poll(id);}}
   for(const a of document.querySelectorAll('a[href*="/auto-editions/view"]')){const u=new URL(a.href),id=u.searchParams.get('allocation_id');if(id&&!sessionStorage.getItem('sc-edition-pending:'+id)&&(!jobs.has(id)||jobs.get(id).job_id!==u.searchParams.get('job_id')))jobs.set(id,{status:'Ready',job_id:u.searchParams.get('job_id')});}
   for(const a of document.querySelectorAll('a[href*="/auto-editions/download"]')){const u=new URL(a.href),id=u.searchParams.get('allocation_id');if(id&&(u.hash==='#Generating'||sessionStorage.getItem('sc-edition-pending:'+id))&&!jobs.has(id)){jobs.set(id,{status:'Generating'});poll(id);}}
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
  window.SportsCaveAutoEditions={start,connect(fn,view){notify=fn;openView=view;hydrate();}};
 }.toString()+')();';parent.document.head.append(script);script.remove();
})();
