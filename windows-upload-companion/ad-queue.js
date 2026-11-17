'use strict';

const adProject = 'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project';
const adStorage = 'publishAdJob';
let adTickRunning = false;

async function rememberAdTab(id, tab) {
  const job = await staffRead(adStorage);
  if (job?.id === id) await staffWrite(adStorage, {...job, tab});
}

async function startAd(job) {
  if (!queueId.test(job.id) || !suppliedReceipt.test(job.receipt) || job.project !== adProject ||
      typeof job.prompt !== 'string' || job.prompt.length > 1048576 ||
      !job.prompt.startsWith('Sports Cave automatic ad job ' + job.id + '\n')) return;
  if (pending.has(job.receipt)) return;
  const previous = await staffRead(keyFor(job.receipt));
  const local = await staffRead(adStorage);
  if (local?.id !== job.id) await staffWrite(adStorage, {id:job.id, receipt:job.receipt});
  if (previous) return;
  const operation = {tab:null, sending:false, project:adProject, adJob:job.id};
  await save(job.receipt, 'opening');
  pending.set(job.receipt, operation);
  queue = queue.then(() => run(job.receipt, job.prompt, operation)).catch(() => {});
}

async function adQueueTick() {
  if (adTickRunning) return;
  adTickRunning = true;
  try {
    const token = await staffRead(staffDeviceKey);
    if (!token) return;
    const local = await staffRead(adStorage);
    const report = local?.receipt ? await health(local.receipt) : {};
    const progress = local?.tab && report.state === 'submitted'
      ? await chrome.tabs.sendMessage(local.tab, {type:'project:progress'}, {frameId:0}).catch(() => null) : null;
    const response = await fetch(osOrigin + '/api/staff-product-uploads/ad-tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json'},
      body:JSON.stringify({id:local?.id, state:progress?.blocked ? 'blocked' : report.state,
                          reason:progress?.reason || report.reason, chat_url:progress?.chat_url}),
      credentials:'omit', signal:AbortSignal.timeout(25000),
    });
    if (!response.ok) return;
    const {job, busy} = await response.json();
    if (busy) return;
    if (!job) await chrome.storage.local.remove(adStorage);
    else if (job.stage === 'opening') await startAd(job);
  } catch {
    // The durable server checkpoint and local send journal survive an interrupted poll.
  } finally {
    adTickRunning = false;
  }
}

chrome.alarms.onAlarm.addListener(alarm => {if (alarm.name === staffAlarm) void adQueueTick();});
chrome.runtime.onStartup.addListener(() => {void adQueueTick();});
chrome.runtime.onInstalled.addListener(() => {void adQueueTick();});

