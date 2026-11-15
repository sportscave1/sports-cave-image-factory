(()=>{
  // A sibling toolbar refresh must not overtake a user's next native widget
  // event (especially a confirmation). Coalesce it until interaction is quiet.
  if(!window.scFlowToolbarRefresh){
    let timer=null,pending=false,lastInput=0;
    const pump=()=>{
      timer=null;if(!pending)return;
      if(180>Date.now()-lastInput || document.querySelector('[role="dialog"],.st-key-flow-workspace [aria-expanded="true"][role="combobox"]')){
        timer=setTimeout(pump,180);return;
      }
      pending=false;document.querySelector('.st-key-toolbar-refresh button')?.click();
    };
    for(const kind of ['pointerdown','keydown','input'])document.addEventListener(kind,e=>{
      if(e.isTrusted && e.target.closest?.('.st-key-flow-workspace,[role="dialog"]'))lastInput=Date.now();
    },true);
    window.scFlowToolbarRefresh=()=>{pending=true;if(!timer)timer=setTimeout(pump,180);};
  }
  // Native input handles Enter and blur. Escape restores the original value
  // before clicking Cancel, so its blur event cannot persist discarded text.
  if(!window.scFlowRenameKeys){
    window.scFlowRenameKeys=true;
    document.addEventListener('keydown',event=>{
      const input=event.target.closest?.('.st-key-flow-rename-input input');
      if(!input || event.key!=='Escape')return;
      event.preventDefault();event.stopImmediatePropagation();
      const original=document.querySelector('[data-flow-rename-original]')?.dataset.flowRenameOriginal||'';
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,original);
      input.dispatchEvent(new Event('input',{bubbles:true}));
      document.querySelector('.st-key-flow-rename-cancel button')?.click();
    },true);
  }
  const input=document.querySelector('.st-key-flow-rename-input input');
  if(input && !input.dataset.renameReady){
    input.dataset.renameReady='true';
    input.focus();input.select();
  }
})();
