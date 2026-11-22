'use strict';

// Independent Orders scheduler. Native actions follow exact server handoffs;
// Prodigi credentials, payments and submission fences remain in Sports Cave OS.
const ordersAlarm = 'sports-cave-orders-queue';
let ordersTickRunning = false;
let ordersContinuationTimer=null;
function continueOrdersSoon(delay=100){
  if(ordersContinuationTimer!==null||typeof setTimeout!=='function')return;
  ordersContinuationTimer=setTimeout(()=>{ordersContinuationTimer=null;if(ordersTickRunning)continueOrdersSoon(1000);else void ordersQueueTick();},delay);
}
async function ordersQueueTick() {
  if (ordersTickRunning) return false;
  ordersTickRunning = true;
  let continueReady=false;
  const keepAlive = setInterval(() => {
    void chrome.storage.local.get('staffQueueCredential').catch(() => {});
  }, 20000);
  try {
    const token = (await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
    if (!token) return false;
    const interrupted=(await chrome.storage.local.get('ordersBrowserPending')).ordersBrowserPending;
    if(interrupted && typeof prodigiReceipt==='function') {
      await prodigiReceipt(interrupted,'finish');
      await chrome.storage.local.remove('ordersBrowserPending');
    }
    // Drain a bounded chain without a 30-second alarm gap between stages.
    // The existing running guard and durable server permits still serialize it.
    for(let step=0;step<6;step++) {
    continueReady=false;
    const preferred=(await chrome.storage.local.get('ordersContinuationOrder')).ordersContinuationOrder;
    const response = await fetch(osOrigin + '/api/orders-companion/tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json',
        'X-Sports-Cave-Orders-Version':typeof ordersRuntimeVersion==='function'?ordersRuntimeVersion():'1.7.45',
        ...(typeof preferred==='string'&&/^[A-Za-z0-9-]{1,100}$/.test(preferred)?{'X-Sports-Cave-Orders-Continue':preferred}:{}),
        'X-Sports-Cave-Orders-Browser':'1','X-Sports-Cave-Orders-QA':'1','X-Sports-Cave-Orders-Tax':'1','X-Sports-Cave-Orders-Products':'1','X-Sports-Cave-Orders-QA-Batch':'1','X-Sports-Cave-Orders-Reset':'1','X-Sports-Cave-Orders-Merge':'1','X-Sports-Cave-Orders-Sequential':'1','X-Sports-Cave-Orders-Empty-Editor':'1','X-Sports-Cave-Orders-Item-QA':'1'},
      body:'{}', credentials:'omit', signal:AbortSignal.timeout(150000),
    });
    if (!response.ok) return false;
    const result = await response.json();
    if(result.browser && typeof prodigiBrowserRun==='function')
      result.job={...result.job,...await prodigiBrowserRun(result.browser)};
    await chrome.storage.local.set({ordersCompanionLast:{time:Date.now(), ...result}});
    if(!result.browser||!result.job){continueReady=false;break;}
    const stopped=['Needs review','Needs QA','Submission uncertain','Handoff unavailable','Stopped'].includes(result.job.status);
    await chrome.storage.local.set({ordersContinuationOrder:!stopped?result.browser.order_id||'':''});
    continueReady=true;
    if(stopped)break; // Yield this order; another ready order can still progress.
    }
    return true;
  } catch {
    // Reconnection reads the same durable upload intent; it never resends blindly.
    return false;
  } finally { clearInterval(keepAlive); ordersTickRunning = false;if(continueReady)continueOrdersSoon(); }
}
async function ensureOrdersAlarm() {
  if (!(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential) return;
  if (!await chrome.alarms.get(ordersAlarm)) await chrome.alarms.create(ordersAlarm, {periodInMinutes:0.5});
  if(typeof ensureOrdersNotifications==='function')void ensureOrdersNotifications();
}
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === ordersAlarm) void ordersQueueTick(); });
chrome.runtime.onStartup.addListener(() => { void ensureOrdersAlarm().then(ordersQueueTick); });
chrome.runtime.onInstalled.addListener(() => { void ensureOrdersAlarm().then(ordersQueueTick); });
// Unpacked-extension reloads and MV3 worker recovery do not consistently emit
// installation/startup events. Restore only the alarm here, with no supplier call.
void ensureOrdersAlarm();
