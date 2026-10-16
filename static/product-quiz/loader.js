/* Stable lightweight loader. No theme styles, iframe or network on button placement load. */
(() => {
  'use strict';
  const base = new URL('.', document.currentScript.src).href;
  const registry = window.SportsCaveQuizLoader ||= {bases:new Map(),hosts:new WeakSet()};
  const json = async url => {const r=await fetch(url,{credentials:'omit',signal:AbortSignal.timeout(10000)});if(!r.ok)throw Error('Quiz unavailable');return r.json();};
  const runtime = async () => {
    let promise=registry.bases.get(base);
    if(!promise){promise=json(base+'manifest.json').then(async manifest=>{
      if(!/^[a-f0-9]{24}$/.test(manifest.version)||!/^runtime\/[a-f0-9]{24}\.js$/.test(manifest.runtime)||!/^config\/[a-f0-9]{24}\.json$/.test(manifest.config))throw Error('Invalid quiz version');
      await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src=base+manifest.runtime;s.onload=resolve;s.onerror=reject;document.head.append(s);});
      return {manifest,config:await json(base+manifest.config)};
    }).catch(error=>{registry.bases.delete(base);throw error;});registry.bases.set(base,promise);}
    return promise;
  };
  function scan(){
    document.querySelectorAll('[data-sports-cave-quiz]').forEach(host=>{
      if(registry.hosts.has(host))return;
      registry.hosts.add(host);
      const mode=host.dataset.sportsCaveQuiz;
      if(!['button','inline'].includes(mode))return;
      const shadow=host.attachShadow({mode:'open'});
      const style=document.createElement('style');style.textContent=':host{display:block}button,a{font:600 14px system-ui;color:#f5f0e6;background:#0b0b0c;border:1px solid #c6a76b;border-radius:6px;padding:12px 20px;cursor:pointer;text-decoration:none}button:focus-visible,a:focus-visible{outline:3px solid #c6a76b;outline-offset:3px}';shadow.append(style);
      const fallback=()=>{shadow.querySelectorAll('button,a,p').forEach(e=>e.remove());const a=document.createElement('a');a.href='/collections/'+(/^[a-z0-9-]+$/.test(host.dataset.collection||'')?host.dataset.collection:'all');a.textContent='Browse editions';shadow.append(a);};
      let loading=false,instance;
      const open=async()=>{if(instance){instance.open();return;}if(loading)return;loading=true;button.disabled=true;button.textContent='Opening…';try{
        const data=await runtime();
        instance=await window.SportsCaveQuizRuntime.mount({host,shadow,base,mode,launcher:button,...data});
        button.textContent=data.config.appearance.title;button.disabled=false;
      }catch{fallback();}finally{loading=false;}};
      const button=document.createElement('button');button.type='button';button.textContent='Find your edition';button.addEventListener('click',open);shadow.append(button);
      if(mode==='inline'){
        const observer=new IntersectionObserver(entries=>{if(entries.some(e=>e.isIntersecting)){observer.disconnect();open();}});observer.observe(host);
      }
    });
  }
  scan();
  if(!registry.listener){registry.listener=true;document.addEventListener('shopify:section:load',scan);}
})();
