/* Keep the bytes of an explicitly requested download after ChatGPT revokes its
   temporary blob URL. No network, credentials, or persistent storage. */
(() => {
  'use strict';
  const files=new Set(['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg']);
  const cache=new Map();
  let armed=null;
  const original=URL.createObjectURL.bind(URL);
  const prune=()=>{for(const [url,item] of cache)if(item.expires<Date.now())cache.delete(url);};
  URL.createObjectURL=function(blob) {
    const url=original(blob);
    prune();
    if(armed && armed.expires>Date.now() && blob instanceof Blob && blob.size>0 && blob.size<=20*1024*1024) {
      if(cache.size>=4)cache.delete(cache.keys().next().value);
      cache.set(url,{blob,job:armed.job,name:armed.name,expires:Date.now()+180000});
      setTimeout(()=>cache.delete(url),180000);
    }
    return url;
  };
  window.addEventListener('message',async event=>{
    const m=event.data;
    if(event.source!==window || event.origin!==location.origin || m?.channel!=='sc-ad-download-request' ||
      !/^[a-f0-9-]{36}$/.test(m.job||'') || !files.has(m.name) || !/^[a-f0-9-]{36}$/.test(m.nonce||''))return;
    const reply=value=>window.postMessage({channel:'sc-ad-download-reply',nonce:m.nonce,...value},location.origin);
    prune();
    if(m.action==='arm') {
      armed={job:m.job,name:m.name,expires:Date.now()+45000};
      reply({ready:true});return;
    }
    if(m.action!=='read')return;
    const item=cache.get(m.url);
    if(!item || item.job!==m.job || item.name!==m.name){reply({error:'Original download bytes expired; retry the attachment'});return;}
    try {
      const bytes=new Uint8Array(await item.blob.arrayBuffer());let binary='';
      for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
      reply({data:btoa(binary)});
    }catch(error){reply({error:'Could not read the original attachment bytes'});}
  });
})();
