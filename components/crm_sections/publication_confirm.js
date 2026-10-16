// Native Streamlit owns the single modal, focus trap and Escape dismissal.
(()=>{
 const body=document.querySelector('.st-key-sc-publication-body');
 const dialog=body?.closest('[role="dialog"]');if(!dialog)return;
 dialog.setAttribute('data-sc-publication-dialog','');
 if(dialog.dataset.scPublicationBound)return;
 dialog.dataset.scPublicationBound='true';
 const origin=window.scAutomationPublishOrigin;
 delete window.scAutomationPublishOrigin;
 const cancel=()=>body.querySelector('.st-key-automation-publication-cancel button');
 cancel()?.focus({preventScroll:true});
 const controller=new AbortController();
 dialog.addEventListener('click',e=>{
  const button=e.target.closest('.st-key-automation-publication-confirm button');if(!button)return;
  if(dialog.dataset.scSubmitting){e.preventDefault();e.stopImmediatePropagation();return;}
  dialog.dataset.scSubmitting='true';
  // Let React accept the first click before disabling the native controls.
  queueMicrotask(()=>body.querySelectorAll('button').forEach(b=>b.disabled=true));
 },{capture:true,signal:controller.signal});
 const observer=new MutationObserver(()=>{
  if(!dialog.isConnected){
   controller.abort();observer.disconnect();
   // Native dismissal and fragment reconciliation may finish in the same frame.
   requestAnimationFrame(()=>{
    if(!origin)return; // Inline flow controls retain native focus restoration.
    const usable=b=>b?.isConnected&&!b.disabled&&b.getClientRects().length&&getComputedStyle(b).visibility!=='hidden';
    const target=usable(origin)?origin:[...document.querySelectorAll('.st-key-toolbar-publish button')].find(usable);
    target?.focus({preventScroll:true});
   });
  }else if(body.querySelector('[data-testid="stAlert"]'))delete dialog.dataset.scSubmitting;
 });
 observer.observe(document.body,{childList:true,subtree:true});
})();
