/* Repair only a server-reserved attempt in the existing, bound ad chat. */
(() => {
  'use strict';
  const uuid=/^[a-f0-9-]{36}$/;
  const chat=/^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/;
  const files=['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'];
  let busy=false;
  // Work renders pasted newlines as paragraph spacing. Compare content, not
  // layout whitespace, while retaining every word and the exact job markers.
  const normalize=text=>String(text||'').replace(/\s+/g,' ').trim();
  const keyFor=m=>'sc-ad-repair:'+m.repair;
  function promptFor(m) {
    if(!Array.isArray(m.names) || !m.names.length || m.names.some(n=>!files.includes(n)))return '';
    return 'Sports Cave automatic ad job '+m.job+'\nSC_AD_REPAIR: '+m.repair+'\n'+
      'Repair the broken attachment downloads in this same chat. Restore ONLY these missing files: '+m.names.join(', ')+'. '+
      'Reuse the original approved files where possible; otherwise recreate them from the original brief, preserving artwork, copy, CSV schema, targeting and 1024x1024 JPEG dimensions. '+
      'If the original bytes exist, export fresh attachments instead of repeating failed attachment references. Include a table with the exact filename in its first column and its working original Library link as a fallback. '+
      'Verify each file exists and is readable, then attach working downloadable originals. Do not change or republish products, create ads, start another job or replace files already imported. The companion will continue the existing job. '+
      'End with SC_AD_READY: '+m.job;
  }
  const users=()=>[...document.querySelectorAll('[data-message-author-role="user"],h4[data-conversation-role="user"]')]
    .map(n=>(n.matches('h4')?n.nextElementSibling:n)?.textContent||'');
  const editor=()=>document.querySelector('#prompt-textarea[contenteditable="true"], [role="textbox"][contenteditable="true"][aria-label="Work with ChatGPT"]');
  const generating=()=>Boolean(document.querySelector('[data-testid="stop-button"],button[aria-label="Stop"],button[aria-label="Stop generating"],button[aria-label="Stop streaming"],button[aria-label="Stop response"]'));
  function status(m) {
    if(!uuid.test(m.job||'') || !uuid.test(m.repair||'') || m.chat!==location.href || !chat.test(m.chat))throw Error('Invalid repair destination');
    const turns=users(),marker='SC_AD_REPAIR: '+m.repair;
    if(turns.some(t=>/Sports Cave automatic ad job [a-f0-9-]{36}/.test(t) && !t.includes('Sports Cave automatic ad job '+m.job)))throw Error('Different job in saved chat');
    const found=turns.some(t=>t.includes(marker) && t.includes('Sports Cave automatic ad job '+m.job));
    const node=editor(),form=node?.closest('form');
    const available=!busy && !found && !generating() && Boolean(form) &&
      !form.querySelector('button[aria-label^="Remove "],button[data-testid*="attachment"]');
    const prompt=promptFor(m);
    return {found,ready:available && !node.innerText.trim(),
      staged:available && Boolean(prompt) && sessionStorage.getItem(keyFor(m))==='prepared' &&
        normalize(node.innerText)===normalize(prompt)};
  }
  chrome.runtime.onMessage.addListener((m,sender,reply)=>{
    if(sender.id!==chrome.runtime.id || !['project:ad-repair-status','project:ad-repair-send'].includes(m?.type))return;
    (async()=>{
      const current=status(m);
      if(m.type==='project:ad-repair-status' || current.found)return current;
      const prompt=promptFor(m),key=keyFor(m);
      const continuing=m.resume===true && current.staged;
      if(!prompt || (!continuing && (!current.ready || m.permit!==true || sessionStorage.getItem(key))))return {found:false};
      busy=true;
      try {
        if(!continuing) {
          const node=editor();node.focus();
          if(document.activeElement!==node || node.innerText.trim())return {found:false};
          sessionStorage.setItem(key,'prepared');
          document.execCommand('insertText',false,prompt);
        }
        const end=Date.now()+120000;
        let button;
        do {
          const currentNode=editor();
          if(location.href!==m.chat || generating() || status(m).found)return {found:status(m).found};
          if(normalize(currentNode?.innerText)!==normalize(prompt))return {found:false};
          button=currentNode?.closest('form')?.querySelector('button[data-testid="send-button"],button[aria-label="Send"]');
          if(button && !button.disabled && button.getAttribute('aria-disabled')!=='true')break;
          button=null;await new Promise(resolve=>setTimeout(resolve,100));
        }while(Date.now()<end);
        if(!button || location.href!==m.chat || generating())return {found:false};
        sessionStorage.setItem(key,'sending');
        button.click();
        const confirmation=Date.now()+10000;
        while(location.href===m.chat && !status(m).found && Date.now()<confirmation)
          await new Promise(resolve=>setTimeout(resolve,100));
        return {found:status(m).found};
      } finally {busy=false;}
    })().then(reply).catch(error=>reply({error:error.message}));
    return true;
  });
})();
