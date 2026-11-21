'use strict';

// Independent Orders worker; no Prodigi key, payment, submit or browser clicks.
// All item identity checks and the durable write fence live in Sports Cave OS.
const ordersAlarm = 'sports-cave-orders-queue';
let ordersTickRunning = false;
async function ordersQueueTick() {
  if (ordersTickRunning) return;
  ordersTickRunning = true;
  const keepAlive = setInterval(() => {
    void chrome.storage.local.get('staffQueueCredential').catch(() => {});
  }, 20000);
  try {
    const token = (await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential;
    if (!token) return;
    const interrupted=(await chrome.storage.local.get('ordersBrowserPending')).ordersBrowserPending;
    if(interrupted && typeof prodigiReceipt==='function') {
      await prodigiReceipt(interrupted,'finish');
      await chrome.storage.local.remove('ordersBrowserPending');
    }
    const response = await fetch(osOrigin + '/api/orders-companion/tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json',
        'X-Sports-Cave-Orders-Browser':'1','X-Sports-Cave-Orders-Documents':'1'},
      body:'{}', credentials:'omit', signal:AbortSignal.timeout(150000),
    });
    if (!response.ok) return;
    const result = await response.json();
    if(result.browser && typeof prodigiBrowserRun==='function')
      result.job={...result.job,...await prodigiBrowserRun(result.browser)};
    await chrome.storage.local.set({ordersCompanionLast:{time:Date.now(), ...result}});
  } catch {
    // Reconnection reads the same durable upload intent; it never resends blindly.
  } finally { clearInterval(keepAlive); ordersTickRunning = false; }
}
async function ensureOrdersAlarm() {
  if (!(await chrome.storage.local.get('staffQueueCredential')).staffQueueCredential) return;
  if (!await chrome.alarms.get(ordersAlarm)) await chrome.alarms.create(ordersAlarm, {periodInMinutes:0.5});
}
chrome.alarms.onAlarm.addListener(alarm => { if (alarm.name === ordersAlarm) void ordersQueueTick(); });
chrome.runtime.onStartup.addListener(() => { void ensureOrdersAlarm().then(ordersQueueTick); });
chrome.runtime.onInstalled.addListener(() => { void ensureOrdersAlarm().then(ordersQueueTick); });
// Unpacked-extension reloads and MV3 worker recovery do not consistently emit
// installation/startup events. Restore only the alarm here, with no supplier call.
void ensureOrdersAlarm();
