(() => {
  const host=window.parent,storageKey='product-upload-generation-focus';
  if(host.sessionStorage.getItem(storageKey)===focusToken)return;
  let observer,timeout;
  const cleanup=()=>{observer?.disconnect();clearTimeout(timeout);};
  function focus(){
    const target=host.document.querySelector('.st-key-product-upload-generation');
    if(!target || target.getBoundingClientRect().height<40)return;
    cleanup();host.sessionStorage.setItem(storageKey,focusToken);
    host.requestAnimationFrame(()=>target.scrollIntoView({block:'start',behavior:host.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'}));
  }
  observer=new MutationObserver(focus);
  observer.observe(host.document.body,{childList:true,subtree:true});
  timeout=setTimeout(cleanup,5000);
  addEventListener('pagehide',cleanup,{once:true});
  focus();
})();
