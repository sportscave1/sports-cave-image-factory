/* Download only the original explicitly associated with a queued chat file. */
(() => {
  'use strict';
  let owner=null;
  const valid=m=>m.url===location.href && location.origin==='https://chatgpt.com' &&
    location.pathname==='/library' && /^libfile_[a-f0-9]+$/.test(new URL(location.href).searchParams.get('file_id')||'') &&
    /^[a-f0-9-]{36}$/.test(m.job||'') &&
    ['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'].includes(m.name);
  function bridge(action,m) {
    return new Promise((resolve,reject)=>{
      const nonce=crypto.randomUUID();
      const listener=e=>{
        if(e.source!==window || e.origin!==location.origin || e.data?.channel!=='sc-ad-download-reply' || e.data.nonce!==nonce)return;
        clearTimeout(timer);window.removeEventListener('message',listener);
        e.data.error?reject(Error(e.data.error)):resolve(e.data);
      };
      const timer=setTimeout(()=>{window.removeEventListener('message',listener);reject(Error('Library download bridge unavailable'));},5000);
      window.addEventListener('message',listener);
      window.postMessage({channel:'sc-ad-download-request',action,job:m.job,name:m.name,url:m.blob,nonce},location.origin);
    });
  }
  chrome.runtime.onMessage.addListener((m,sender,reply)=>{
    if(sender.id!==chrome.runtime.id || !['project:ad-library','project:ad-library-blob'].includes(m?.type))return;
    (async()=>{
      if(!valid(m))throw Error('Library original no longer matches the queued download');
      if(m.type==='project:ad-library-blob') {
        if(owner!==m.job+':'+m.name || !String(m.blob).startsWith('blob:https://chatgpt.com/'))throw Error('Library download must be retried');
        return bridge('read',m);
      }
      const buttons=[...document.querySelectorAll('button[aria-label="Download"]')].filter(b=>b.getClientRects().length && !b.disabled);
      if(buttons.length!==1)return {clicked:false};
      await bridge('arm',m);owner=m.job+':'+m.name;
      buttons[0].click();return {clicked:true};
    })().then(reply).catch(e=>reply({error:e.message}));return true;
  });
})();
