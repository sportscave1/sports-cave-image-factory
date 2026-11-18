/* Collect only named originals from the response to this exact queued prompt. */
(() => {
  'use strict';
  const names=['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'];
  const chat=/^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/;
  function locate(job,name,response,recover=false) {
    if(!chat.test(location.href)||!names.includes(name)||!/^[a-f0-9-]{36}$/.test(job))throw Error('Invalid ad artifact request');
    const messages=[...document.querySelectorAll('[data-message-author-role]')];
    const start=messages.findIndex(node=>node.dataset.messageAuthorRole==='user' && node.textContent.includes('Sports Cave automatic ad job '+job));
    if(start<0 && !recover)throw Error('Original queued prompt is not loaded. Press Play to resume this saved chat.');
    if(recover && messages.some(node=>node.dataset.messageAuthorRole==='user' &&
      /Sports Cave automatic ad job [a-f0-9-]{36}/.test(node.textContent) && !node.textContent.includes('Sports Cave automatic ad job '+job)))throw Error('This chat contains a different queued job; review its attachments.');
    const matches=[],seen=new Set();
    for(const message of messages.slice(start+1)) {
      if(message.dataset.messageAuthorRole==='user'){if(recover)continue;break;}
      if(message.dataset.messageAuthorRole!=='assistant')continue;
      const id=message.dataset.messageId;
      if(!id || (response && response!==id))continue;
      const container=message.closest('article') || message;
      for(const link of container.querySelectorAll('a,button')) {
        const labels=[link.getAttribute('download'),link.textContent,link.getAttribute('aria-label'),link.getAttribute('title')].filter(Boolean).map(text=>text.trim());
        if(!seen.has(link) && labels.some(label=>label===name || label.split(/\s+/)[0]===name || label==='Download '+name)) {
          seen.add(link);matches.push({link,response:id});
        }
      }
    }
    if(matches.length!==1){
      if(!matches.length && recover && messages[0])messages[0].scrollIntoView({block:'start'});
      throw Error(matches.length?'Ambiguous ad attachment; original files retained':'Waiting for '+name+' in the saved chat');
    }
    return matches[0];
  }
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id===chrome.runtime.id && message?.type==='project:ad-blob') {
      try {locate(message.job,message.name,message.response,message.recover);}catch(error){reply({error:error.message});return;}
      if(!String(message.url).startsWith('blob:https://chatgpt.com/'))return;
      (async()=>{
        const response=await fetch(message.url),blob=await response.blob();
        if(!response.ok || !blob.size || blob.size>20*1024*1024)throw Error('Invalid artifact download');
        const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';
        for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
        reply({data:btoa(binary)});
      })().catch(error=>reply({error:error.message}));
      return true;
    }
    if(sender.id!==chrome.runtime.id || message?.type!=='project:ad-artifact')return;
    try {
      const found=locate(message.job,message.name,message.response,message.recover);
      // Use the site's existing authenticated download action, including sandbox links.
      found.link.click();
      reply({clicked:true,response:found.response,chat:location.href});
    } catch(error){reply({clicked:false,reason:error.message});}
  });
})();
