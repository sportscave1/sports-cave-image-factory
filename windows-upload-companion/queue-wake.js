// Wake the paired queue after a Home enqueue has committed. The alarm remains
// the durable fallback if the tab closes or the request takes longer.
const wakeDesignQueue=()=>{
  // Reloading an unpacked extension invalidates scripts in existing tabs.
  // A synchronous missing-runtime error is not a rejected Promise.
  try {
    const runtime=globalThis.chrome?.runtime;
    if(runtime?.id && typeof runtime.sendMessage==='function')
      void runtime.sendMessage({type:'os:wake-designs'})?.catch(()=>{});
  } catch { /* The next page load and durable alarm restore contact. */ }
};
document.addEventListener('click',event=>{
  if(!event.isTrusted)return;
  const button=event.target?.closest?.('button');
  if(!button || !/^add to queue$/i.test(button.textContent.trim()))return;
  for(const ms of [1000,4000])setTimeout(()=>{
    wakeDesignQueue();
  },ms);
},true);
document.addEventListener('sc-design-edit-queued',()=>{
  wakeDesignQueue();
});
