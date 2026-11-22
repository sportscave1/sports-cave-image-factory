'use strict';
// Positive DOM evidence wakes immediately; one fallback timer covers properties
// which do not generate mutations. Every observer/timer is released on exit.
async function prodigiObserveReady(check,{timeout=120000,interval=1000,root}={}) {
  const first=check();if(first)return first;
  root=root||(typeof document!=='undefined'?document.documentElement:null);
  return new Promise((resolve,reject)=>{
    let observer,timer,deadline,finished=false,queued=false;
    function done(error,value){if(finished)return;finished=true;if(observer)observer.disconnect();clearTimeout(timer);clearTimeout(deadline);error?reject(error):resolve(value);}
    function inspect(){if(finished)return;try{const value=check();if(value)done(null,value);}catch(error){done(error);}}
    function changed(){if(queued||finished)return;queued=true;queueMicrotask(()=>{queued=false;inspect();});}
    function poll(){inspect();if(!finished)timer=setTimeout(poll,interval);}
    if(root&&typeof MutationObserver==='function'){
      observer=new MutationObserver(changed);observer.observe(root,{childList:true,subtree:true,attributes:true,characterData:true});
    }
    // A sleeping tab may deliver its deadline before queued mutation/poll tasks.
    // Re-read current positive evidence once before declaring a timeout.
    deadline=setTimeout(()=>{inspect();if(!finished)done(new Error('The expected Prodigi control did not finish loading.'));},timeout);
    timer=setTimeout(poll,interval);inspect();
  });
}
if(typeof module!=='undefined')module.exports={prodigiObserveReady};
