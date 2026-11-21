/* Collect only named originals from the response to this exact queued prompt. */
(() => {
  'use strict';
  const names=['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'];
  let downloadAttempt=null;
  // A click is not a receipt: Work can reject an expired attachment with a
  // toast without ever creating a browser download. Observe only new errors.
  new MutationObserver(records=>{
    if(!downloadAttempt)return;
    for(const record of records)for(const node of record.addedNodes) {
      const text=(node.textContent||'').trim();
      if(text.length<300 && /Failed to download (?:file|ad_copy\.csv|collector-hallway\.jpg|architectural-wall\.jpg|man-cave\.jpg)/i.test(text))
        downloadAttempt.error='ChatGPT could not download '+downloadAttempt.name;
    }
  }).observe(document.documentElement,{childList:true,subtree:true});
  function downloadBridge(action,job,name,url) {
    return new Promise((resolve,reject)=>{
      const nonce=crypto.randomUUID();
      const listener=event=>{
        if(event.source!==window || event.origin!==location.origin ||
          event.data?.channel!=='sc-ad-download-reply' || event.data.nonce!==nonce)return;
        clearTimeout(timer);window.removeEventListener('message',listener);
        event.data.error ? reject(Error(event.data.error)) : resolve(event.data);
      };
      const timer=setTimeout(()=>{window.removeEventListener('message',listener);reject(Error('Reload this saved chat to enable attachment transfer'));},5000);
      window.addEventListener('message',listener);
      window.postMessage({channel:'sc-ad-download-request',action,job,name,url,nonce},location.origin);
    });
  }
  const chat=/^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/;
  async function locate(job,name,response,recover=false,boundChat='',repair='') {
    if(!chat.test(location.href)||!names.includes(name)||!/^[a-f0-9-]{36}$/.test(job))throw Error('Invalid ad artifact request');
    const messages=[...document.querySelectorAll('[data-message-author-role],h4[data-conversation-role]')]
      .filter(node=>!node.matches('h4') || !node.closest('[data-message-author-role]'))
      .map(node=>({node,role:node.dataset.messageAuthorRole||node.dataset.conversationRole,
        body:node.matches('h4') ? node.nextElementSibling : node}));
    let start=messages.findIndex(turn=>turn.role==='user' && turn.body?.textContent.includes('Sports Cave automatic ad job '+job));
    // Resume may follow an explicit repair in this same job's saved chat.
    // Already received files remain pinned to their original response IDs.
    if(recover && !response)messages.forEach((turn,index)=>{
      if(turn.role==='user' && turn.body?.textContent.includes('Sports Cave automatic ad job '+job))start=index;
    });
    if(repair) {
      start=messages.findIndex(turn=>turn.role==='user' && turn.body?.textContent.includes('SC_AD_REPAIR: '+repair) &&
        turn.body.textContent.includes('Sports Cave automatic ad job '+job));
      if(start<0)throw Error('Waiting for the saved attachment repair response');
    }
    // The server records this exact chat only after the send journal confirms
    // submission. Long briefs appear as Pasted text, hiding their job marker.
    const users=messages.filter(turn=>turn.role==='user');
    if(start<0 && boundChat===location.href && users.length===1 &&
      users[0].body?.querySelector('button[aria-label^="Pasted text("]'))start=messages.indexOf(users[0]);
    if(start<0 && !recover)throw Error('Original queued prompt is not loaded. Press Play to resume this saved chat.');
    if(messages.some(turn=>turn.role==='user' &&
      /Sports Cave automatic ad job [a-f0-9-]{36}/.test(turn.body?.textContent||'') && !turn.body.textContent.includes('Sports Cave automatic ad job '+job)))throw Error('This chat contains a different queued job; review its attachments.');
    if(document.querySelector('[data-testid="stop-button"],button[aria-label="Stop generating"],button[aria-label="Stop streaming"],button[aria-label="Stop response"],button[aria-label="Stop"]'))
      throw Error('ChatGPT is still generating; waiting for finished attachments');
    const matches=[],seen=new Set();
    for(const message of messages.slice(start+1)) {
      if(message.role==='user'){if(recover && !repair)continue;break;}
      if(message.role!=='assistant' || !message.body)continue;
      // Work's headings have no message ID. Pin a content fingerprint rather
      // than a positional index, which changes when history is virtualized.
      const digest=message.node.dataset.messageId ? null : await crypto.subtle.digest('SHA-256',
        new TextEncoder().encode(message.body.textContent.replace(/\s+/g,' ').trim()));
      const id=message.node.dataset.messageId || 'work-'+Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
      if(!id || (response && response!==id))continue;
      const container=message.node.matches('h4') ? message.body : message.node.closest('article') || message.body;
      for(const link of container.querySelectorAll('a,button')) {
        const labels=[link.getAttribute('download'),link.textContent,link.getAttribute('aria-label'),link.getAttribute('title')].filter(Boolean).map(text=>text.trim());
        if(labels.some(label=>label===name || label.split(/\s+/)[0]===name || label==='Download '+name || label==='Open preview of '+name)) {
          let download=link;
          if(link.getAttribute('aria-label')?.startsWith('Open preview of ')) {
            download=null;
            // Work file cards open a viewer on their name button. The sibling
            // Download file action is the authenticated native download.
            for(let card=link.parentElement;card && container.contains(card);card=card.parentElement) {
              const previews=card.querySelectorAll('button[aria-label^="Open preview of "]');
              if(previews.length!==1)break;
              const actions=card.querySelectorAll('button[aria-label="Download file"],a[download]');
              if(actions.length===1){download=actions[0];break;}
              if(actions.length>1)break;
            }
          }
          if(download && !seen.has(download)){seen.add(download);matches.push({link:download,response:id});}
        }
      }
    }
    if(matches.length!==1){
      if(!matches.length && recover && messages[0])messages[0].node.scrollIntoView({block:'start'});
      throw Error(matches.length?'Ambiguous ad attachment; original files retained':'Waiting for '+name+' in the saved chat');
    }
    // A Work chat card can fail while its explicitly linked Library original
    // still downloads. Accept only the unique link in this file's own table row
    // within the same pinned assistant response, never an arbitrary Library file.
    const selected=matches[0],libraries=new Set();
    for(const message of messages.slice(start+1)) {
      if(message.role==='user'){if(recover && !repair)continue;break;}
      if(message.role!=='assistant' || !message.body?.contains(selected.link))continue;
      for(const row of message.body.querySelectorAll('tr')) {
        if(row.querySelector('td')?.textContent.trim()!==name)continue;
        for(const link of row.querySelectorAll('a[href]')) {
          const url=new URL(link.href,location.origin);
          if(url.origin==='https://chatgpt.com' && url.pathname==='/library' &&
            /^libfile_[a-f0-9]+$/.test(url.searchParams.get('file_id')||'') &&
            [...url.searchParams.keys()].every(k=>['file_id','account_id'].includes(k)) &&
            (!url.searchParams.has('account_id') || url.searchParams.get('account_id')==='personal')) {
            url.searchParams.delete('account_id');libraries.add(url.href);
          }
        }
      }
    }
    return {...selected,library:libraries.size===1?[...libraries][0]:undefined};
  }
  chrome.runtime.onMessage.addListener((message,sender,reply)=>{
    if(sender.id===chrome.runtime.id && message?.type==='project:ad-download-status') {
      const same=downloadAttempt && downloadAttempt.job===message.job &&
        downloadAttempt.name===message.name && downloadAttempt.response===message.response && message.chat===location.href;
      reply({error:same ? downloadAttempt.error||'' : ''});return;
    }
    if(sender.id===chrome.runtime.id && message?.type==='project:ad-blob') {
      if(!String(message.url).startsWith('blob:https://chatgpt.com/'))return;
      (async()=>{
        await locate(message.job,message.name,message.response,message.recover,message.chat,message.repair);
        let response;
        try {response=await fetch(message.url);} catch(error) {
          reply(await downloadBridge('read',message.job,message.name,message.url));return;
        }
        const blob=await response.blob();
        if(!response.ok || !blob.size || blob.size>20*1024*1024)throw Error('Invalid artifact download');
        const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';
        for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
        reply({data:btoa(binary)});
      })().catch(error=>reply({error:error.message}));
      return true;
    }
    if(sender.id!==chrome.runtime.id || message?.type!=='project:ad-artifact')return;
    (async()=>{
      const found=await locate(message.job,message.name,message.response,message.recover,message.chat,message.repair);
      await downloadBridge('arm',message.job,message.name);
      downloadAttempt={job:message.job,name:message.name,response:found.response};
      // Use the site's existing authenticated download action, including sandbox links.
      found.link.click();
      reply({clicked:true,response:found.response,chat:location.href,library:found.library});
    })().catch(error=>reply({clicked:false,reason:error.message}));
    return true;
  });
})();
