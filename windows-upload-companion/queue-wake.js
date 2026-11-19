// Wake the paired queue after a Home enqueue has committed. The alarm remains
// the durable fallback if the tab closes or the request takes longer.
document.addEventListener('click',event=>{
  if(!event.isTrusted)return;
  const button=event.target.closest('button');
  if(!button || !/^add to queue$/i.test(button.textContent.trim()))return;
  for(const ms of [1000,4000])setTimeout(()=>{
    void chrome.runtime.sendMessage({type:'os:wake-designs'}).catch(()=>{});
  },ms);
},true);
document.addEventListener('sc-design-edit-queued',()=>{
  void chrome.runtime.sendMessage({type:'os:wake-designs'}).catch(()=>{});
});
