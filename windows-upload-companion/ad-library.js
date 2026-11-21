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
      if(!buttons.length && m.name.endsWith('.jpg')) {
        // Some Library image viewers expose the original image but no Download
        // action. Read only this exact file's displayed, full-resolution bytes.
        const file=new URL(location.href).searchParams.get('file_id');
        const expected='/api/library/files/'+file+'/content';
        const images=[...document.querySelectorAll('img')].filter(image=>{
          const source=new URL(image.currentSrc||image.src,location.origin);
          return image.alt.replace(/\(\d{8}-\d{6}\)(?=\.jpg$)/,'')===m.name &&
            image.naturalWidth>=1024 && image.naturalHeight>=1024 &&
            source.origin===location.origin && source.pathname===expected;
        });
        if(images.length!==1)return {clicked:false};
        const response=await fetch(images[0].currentSrc||images[0].src,
          {credentials:'same-origin',signal:AbortSignal.timeout(25000)});
        const final=new URL(response.url);
        if(!response.ok || final.origin!==location.origin || final.pathname!==expected)throw Error('Library original could not be verified');
        const reader=response.body.getReader(),chunks=[];let size=0;
        while(true){const part=await reader.read();if(part.done)break;size+=part.value.length;
          if(size>20*1024*1024){await reader.cancel();throw Error('Library original exceeds transfer limit');}chunks.push(part.value);}
        const bytes=new Uint8Array(size);let offset=0;
        for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
        if(bytes[0]!==255 || bytes[1]!==216 || bytes[2]!==255)throw Error('Library original is not the required JPEG');
        let binary='';for(let i=0;i<bytes.length;i+=32768)binary+=String.fromCharCode(...bytes.subarray(i,i+32768));
        return {data:btoa(binary)};
      }
      if(buttons.length!==1)return {clicked:false};
      await bridge('arm',m);owner=m.job+':'+m.name;
      buttons[0].click();return {clicked:true};
    })().then(reply).catch(e=>reply({error:e.message}));return true;
  });
})();
