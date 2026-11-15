/* Never unlock disabled widgets or remove genuine modal backdrops. */
(() => {
 const version=3;
 if(window.SportsCaveSessionRecovery?.version===version)return;
 window.SportsCaveSessionRecovery?.destroy();
 const controller=new AbortController(),options={signal:controller.signal};
 let timer=null,attempt=0,busy=false,request=null,started=false,frame=null,epoch=0,destroyed=false;
 const connectionDialog=()=>[...document.querySelectorAll('[role="dialog"]')]
  .find(n=>n.querySelector('h2')?.textContent.trim()==='Connection error');
 const disconnected=()=>!!connectionDialog()&&[...document.querySelectorAll('[data-testid="stSidebar"] button')].some(n=>n.disabled);
 const cancel=()=>{epoch++;clearTimeout(timer);timer=null;request?.abort();busy=false;started=false;attempt=0;
  if(frame!==null){cancelAnimationFrame(frame);frame=null;}};
 const recover=async()=>{
  timer=null;if(destroyed||document.hidden||busy||!disconnected())return;
  const run=epoch,probe=new AbortController();
  busy=true;request=probe;const timeout=setTimeout(()=>probe.abort(),4000);
  try{
   // Same-origin liveness only. No page, Shopify, audience or template APIs.
   const base=new URL('.',location.href);
   const response=await fetch(new URL('_stcore/health',base),{cache:'no-store',signal:probe.signal});
   if(destroyed||run!==epoch||probe.signal.aborted||document.hidden)return;
   if(response.ok&&disconnected()){
    // Refresh drafts contain in-memory media and copy without the email
    // editor's browser checkpoint. A health response is not a restored session.
    // Keep Streamlit's real reconnect dialog; never silently discard the draft.
    const refresh=document.querySelector?.('.st-key-ads-refresh-page-marker');
    if(refresh){
     if(!document.getElementById('sc-refresh-recovery-warning')){
      const note=document.createElement('p');note.id='sc-refresh-recovery-warning';note.setAttribute('role','status');
      note.textContent='Creative Refresh connection interrupted. Automatic page reload is paused to protect your draft. Wait for reconnection; reload only if you accept losing unsaved work. Saved work can be reopened from Files.';
      connectionDialog().append(note);
     }
     return;
    }
    const last=Number(sessionStorage.getItem('sc-session-reload')||0);
    if(Date.now()-last>60000){
     window.dispatchEvent(new Event('sc-recovery-flush'));
     sessionStorage.setItem('sc-session-reload',String(Date.now()));location.reload();return;
    }
   }
  }catch{/* Leave Streamlit's real connection error visible; no false success. */}
  finally{clearTimeout(timeout);if(run===epoch)busy=false;}
  // Comparison whitespace prevents Streamlit's HTML sanitizer treating it as markup.
  if(!destroyed&&run===epoch&&disconnected()&&!document.hidden&&attempt < 3)timer=setTimeout(recover,[1500,5000,15000][attempt++]);
 };
 const resume=()=>{
  if(destroyed)return;
  if(document.hidden){cancel();return;}
  if(!disconnected()){cancel();return;}
  if(!started){started=true;attempt=0;timer=setTimeout(recover,1500);}
 };
 document.addEventListener('visibilitychange',resume,options);
 window.addEventListener('focus',resume,options);
 window.addEventListener('pageshow',resume,options);
 window.addEventListener('online',()=>{cancel();resume();},options);
 window.addEventListener('pagehide',cancel,options);
 // Streamlit sends many small DOM updates. Inspect once per paint, not per delta.
 const observer=new MutationObserver(()=>{
  if(!destroyed&&frame===null&&!document.hidden)frame=requestAnimationFrame(()=>{frame=null;resume();});
 });
 observer.observe(document.body,{childList:true,subtree:true});
 window.SportsCaveSessionRecovery={version,destroy(){destroyed=true;cancel();controller.abort();observer.disconnect();delete window.SportsCaveSessionRecovery;}};
 resume();
})();
