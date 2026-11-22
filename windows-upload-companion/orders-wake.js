'use strict';

// Level-triggered hints only. All actions still use ordersQueueTick and the
// existing server-issued permits. No jobs, customer data or supplier URLs arrive
// over this channel. The alarm remains independent if MV3 suspends this worker.
let ordersNotificationsRunning=false;
const ordersNotificationCursor='ordersNotificationCursor';
const ordersNotificationDelay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function ensureOrdersNotifications() {
  if(ordersNotificationsRunning)return;
  ordersNotificationsRunning=true;
  let failures=0,lastToken='';
  try {
    while(true) {
      try {
        const state=await chrome.storage.local.get(['staffQueueCredential',ordersNotificationCursor]);
        const token=state.staffQueueCredential;
        if(!token)return;
        // A native stage may be lengthy. Leave its existing keepalive alone and
        // defer hints until it finishes; committed readiness remains replayable.
        if(ordersTickRunning){await ordersNotificationDelay(1000);continue;}
        const rotated=lastToken && lastToken!==token;
        lastToken=token;
        const saved=rotated?'':state[ordersNotificationCursor];
        const after=typeof saved==='string' && /^[a-f0-9]{64}$/.test(saved)?saved:'';
        const response=await fetch(osOrigin+'/api/orders-companion/notifications?after='+after,{
          headers:{Authorization:'Bearer '+token},credentials:'omit',cache:'no-store',
          // Chrome can terminate a worker if a fetch response takes >30s.
          signal:AbortSignal.timeout(25000),
        });
        if(!response.ok)throw new Error('Orders notifications unavailable');
        const hint=await response.json();
        if(hint.enabled===false){await ordersNotificationDelay(30000);continue;}
        if(hint.enabled!==true || typeof hint.changed!=='boolean' || !/^[a-f0-9]{64}$/.test(hint.version) ||
          (!hint.changed && hint.version!==after))throw new Error('Invalid Orders notification');
        if(hint.changed) {
          const handled=await ordersQueueTick();
          if(!handled)throw new Error('Orders queue will retry');
          // A failed tick or credential change never consumes a notification.
          const current=(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
          if(current!==token)continue;
          await chrome.storage.local.set({[ordersNotificationCursor]:hint.version,
            ordersNotificationSeenAt:Date.now()});
        }
        failures=0;
        // Also bound traffic if an intermediary returns an idle reply early.
        await ordersNotificationDelay(500);
      } catch {
        failures=Math.min(failures+1,5);
        await ordersNotificationDelay(Math.min(30000,1000*2**failures)+Math.floor(Math.random()*500));
      }
    }
  } finally {ordersNotificationsRunning=false;}
}
