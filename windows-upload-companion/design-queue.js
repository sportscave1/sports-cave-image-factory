'use strict';

const designProject = 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project';
const designStorage = 'morningDesignJobs';
const designAlarm = 'sports-cave-morning-designs';
let designTickRunning = false;
let designStateQueue = Promise.resolve();

function updateDesignJobs(change) {
  const update = designStateQueue.then(async () => {
    const current = await staffRead(designStorage) || {};
    await staffWrite(designStorage, change(current));
  });
  designStateQueue = update.catch(() => {});
  return update;
}

async function rememberDesignTab(id, tab) {
  await updateDesignJobs(jobs => jobs[id] ? {...jobs, [id]:{...jobs[id], tab}} : jobs);
}

async function startDesign(job) {
  if (!queueId.test(job.id) || !suppliedReceipt.test(job.receipt) || job.project !== designProject ||
      typeof job.prompt !== 'string' || job.prompt.length > 1048576 ||
      !(job.kind==='edit' ? job.prompt.startsWith('**USER-REQUESTED DESIGN CHANGES**\n') :
        job.prompt.includes('morning_design_job_id = "' + job.id + '"'))) return;
  if (pending.has(job.receipt)) return;
  const previous = (await chrome.storage.local.get(keyFor(job.receipt)))[keyFor(job.receipt)];
  // Even an interrupted opening needs inspection, not a second automatic chat.
  if (previous) return;
  await updateDesignJobs(jobs => ({...jobs, [job.id]:{id:job.id, receipt:job.receipt}}));
  const operation = {tab:null, sending:false, project:designProject, designJob:job.id};
  pending.set(job.receipt, operation);
  await save(job.receipt, 'opening');
  // Share the product worker's paste/send mutex, while generation runs in parallel.
  queue = queue.then(() => run(job.receipt, job.prompt, operation)).catch(() => {});
}

async function designQueueTick() {
  if (designTickRunning) return;
  designTickRunning = true;
  try {
    const token = await staffRead(staffDeviceKey);
    if (!token) return;
    const jobs = await staffRead(designStorage) || {};
    const events = [];
    for (const job of Object.values(jobs).slice(0, 1)) {
      const report = await health(job.receipt);
      const tab = job.tab ? await chrome.tabs.get(job.tab).catch(() => null) : null;
      const progress = tab && report.state === 'submitted' ? await companionMessage(job.tab, {type:'project:progress'}, {frameId:0}).catch(() => null) : null;
      events.push({id:job.id, state:progress?.blocked ? 'blocked' : report.state, reason:progress?.reason || report.reason, chat_url:progress?.chat_url || tab?.url || ''});
    }
    const response = await fetch(osOrigin + '/api/morning-designs/tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json'},
      body:JSON.stringify({events}), credentials:'omit', signal:AbortSignal.timeout(25000),
    });
    if (!response.ok) return;
    const result = await response.json();
    if (!Array.isArray(result.jobs) || result.jobs.length > 1) return;
    const activeIds = new Set(result.jobs.map(job => job.id));
    // Reload after the network wait so a concurrent submission's tab is retained.
    await updateDesignJobs(current => Object.fromEntries(Object.entries(current).filter(([id]) => activeIds.has(id))));
    for (const job of result.jobs) if (job.stage === 1) await startDesign(job);
  } catch {
    // Durable server claims and the local send journal survive network outages.
  } finally {
    designTickRunning = false;
  }
}

async function ensureDesignAlarm() {
  if (!await chrome.alarms.get(designAlarm)) await chrome.alarms.create(designAlarm, {periodInMinutes:0.5});
}
chrome.alarms.onAlarm.addListener(alarm => {if (alarm.name === designAlarm) void designQueueTick();});
chrome.runtime.onStartup.addListener(() => {void ensureDesignAlarm().then(designQueueTick);});
chrome.runtime.onInstalled.addListener(() => {void ensureDesignAlarm().then(designQueueTick);});
