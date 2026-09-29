/* Never unlock disabled widgets or remove genuine modal backdrops. */
(() => {
 window.SportsCaveSessionRecovery?.destroy();
 const controller=new AbortController(),options={signal:controller.signal};
 let timer=null,attempt=0,busy=false,request=null,started=false;
 const connectionDialog=()=>[...document.querySelectorAll('[role="dialog"]')]
  .find(n=>n.querySelector('h2')?.textContent.trim()==='Connection error');
 const disconnected=()=>!!connectionDialog()&&[...document.querySelectorAll('[data-testid="stSidebar"] button')].some(n=>n.disabled);
 const cancel=()=>{clearTimeout(timer);timer=null;request?.abort();busy=false;started=false;attempt=0;};
 const recover=async()=>{
  timer=null;if(document.hidden||busy||!disconnected())return;
  busy=true;request=new AbortController();const timeout=setTimeout(()=>request.abort(),4000);
  try{
   // Same-origin liveness only. No page, Shopify, audience or template APIs.
   const base=new URL('.',location.href);
   const response=await fetch(new URL('_stcore/health',base),{cache:'no-store',signal:request.signal});
   if(response.ok&&disconnected()){
    const last=Number(sessionStorage.getItem('sc-session-reload')||0);
    if(Date.now()-last>60000){
     window.dispatchEvent(new Event('sc-recovery-flush'));
     sessionStorage.setItem('sc-session-reload',String(Date.now()));location.reload();return;
    }
   }
  }catch{/* Leave Streamlit's real connection error visible; no false success. */}
  finally{clearTimeout(timeout);busy=false;}
  if(disconnected()&&!document.hidden&&attempt<3)timer=setTimeout(recover,[1500,5000,15000][attempt++]);
 };
 const resume=()=>{
  if(document.hidden){cancel();return;}
  if(!disconnected()){cancel();return;}
  if(!started){started=true;attempt=0;timer=setTimeout(recover,1500);}
 };
 document.addEventListener('visibilitychange',resume,options);
 window.addEventListener('focus',resume,options);
 window.addEventListener('pageshow',resume,options);
 window.addEventListener('online',()=>{cancel();resume();},options);
 window.addEventListener('pagehide',cancel,options);
 const observer=new MutationObserver(resume);
 observer.observe(document.body,{childList:true,subtree:true});
 window.SportsCaveSessionRecovery={destroy(){cancel();controller.abort();observer.disconnect();}};
 resume();
})();
