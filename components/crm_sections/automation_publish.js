/* Automation-only save barrier. Publication itself stays on the server. */
(()=>{
 if(window.scAutomationPublishBarrier)return;
 window.scAutomationPublishBarrier=true;
 let busy=false,allowed=false,nativePending=false,command='Publish now';
 const button=(name=command)=>[...document.querySelectorAll('.st-key-automation-toolbar button')].find(b=>b.textContent.trim()===name);
 const match=e=>{const current=e.target.closest('.st-key-automation-toolbar button');if(!current||!['Publish now','Publish changes','Retry Publish','Save draft'].includes(current.textContent.trim()))return false;command=current.textContent.trim();return true;};
 const pending=()=>{const save=document.querySelector('.st-key-toolbar-save button');if(save)save.disabled=false;};
 window.addEventListener('sc-campaign-pending',pending);
 document.addEventListener('input',e=>{if(e.target.closest('.st-key-crm-composer-controls')){nativePending=true;pending();}});
 // Keep the input focused until the command has captured the click.
 document.addEventListener('pointerdown',e=>{if(match(e)&&!e.target.closest('button').disabled)e.preventDefault();},true);
 document.addEventListener('click',async e=>{
  if(allowed||!match(e))return;
  e.preventDefault();e.stopImmediatePropagation();
  if(busy||button()?.disabled)return;
  busy=true;
  const requested=command;
  const scope=document.querySelector('.st-key-crm-composer-controls');
  const note=document.createElement('span');note.setAttribute('role','status');note.textContent='Saving latest edits…';
  button().parentElement.append(note);
  try{
   document.activeElement?.blur();
   await window.scCampaignFlushSections?.();
   // Native fields save on blur. Wait for their fragment update to settle,
   // then click the current command, rather than a detached React node.
   if(nativePending&&scope)await new Promise((resolve,reject)=>{
    const start=Date.now();let last=Date.now();
    const observer=new MutationObserver(()=>last=Date.now());observer.observe(scope,{subtree:true,childList:true,attributes:true});
    const check=()=>{
     if(Date.now()-start>10000){observer.disconnect();reject(new Error('Save timed out'));return;}
     const running=[...scope.querySelectorAll('[data-stale="true"]')].some(el=>el.getClientRects().length&&getComputedStyle(el).visibility!=='hidden');
     if(!running&&Date.now()-last>=500){observer.disconnect();resolve();return;}
     setTimeout(check,30);
    };check();
   });
   nativePending=false;
   const current=button(requested);if(requested==='Save draft'&&current?.disabled){note.remove();return;}if(!current||current.disabled)throw new Error('Command changed');
   note.remove();allowed=true;try{current.click();}finally{allowed=false;}
  }catch{note.textContent='Save your latest edits, then retry publishing.';}
  finally{busy=false;}
 },true);
})();
