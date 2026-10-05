/* Automation-only save barrier. Publication itself stays on the server. */
(()=>{
 if(window.scAutomationPublishBarrier)return;
 window.scAutomationPublishBarrier=true;
 let busy=false,allowed=false;
 const button=()=>[...document.querySelectorAll('.st-key-crm-automation-editor button')].find(b=>b.textContent.trim()==='Publish now');
 const match=e=>{const current=button();return !!current&&e.target.closest('button')===current;};
 // Keep the input focused until the command has captured the click.
 document.addEventListener('pointerdown',e=>{if(match(e)&&!e.target.closest('button').disabled)e.preventDefault();},true);
 document.addEventListener('click',async e=>{
  if(allowed||!match(e))return;
  e.preventDefault();e.stopImmediatePropagation();
  if(busy||button()?.disabled)return;
  busy=true;
  const scope=document.querySelector('.st-key-crm-automation-editor');
  const note=document.createElement('span');note.setAttribute('role','status');note.textContent='Saving latest edits…';
  button().parentElement.append(note);
  try{
   document.activeElement?.blur();
   await window.scCampaignFlushSections?.();
   // Native fields save on blur. Wait for their fragment update to settle,
   // then click the current command, rather than a detached React node.
   await new Promise((resolve,reject)=>{
    const start=Date.now();let last=Date.now();
    const observer=new MutationObserver(()=>last=Date.now());observer.observe(scope,{subtree:true,childList:true,attributes:true});
    const check=()=>{
     if(Date.now()-start>10000){observer.disconnect();reject(new Error('Save timed out'));return;}
     const running=document.querySelector('[data-testid="stStatusWidget"]')||scope.querySelector('[data-stale="true"]');
     if(!running&&Date.now()-last>=300){observer.disconnect();resolve();return;}
     setTimeout(check,30);
    };check();
   });
   const current=button();if(!current||current.disabled)throw new Error('Command changed');
   note.remove();allowed=true;try{current.click();}finally{allowed=false;}
  }catch{note.textContent='Save your latest edits, then retry publishing.';}
  finally{busy=false;}
 },true);
})();
