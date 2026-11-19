'use strict';

const designProject = 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project';
const designStorage = 'morningDesignJobs';
const designAlarm = 'sports-cave-morning-designs';
let designTickRunning = false;
let designTickRequested = false;
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
      typeof job.prompt !== 'string' || job.prompt.length > 1048576) return;
  const output=job.prompt.match(/\nQueue output receipt: ([a-f0-9-]{36})\n/);
  const retry=job.prompt.match(/\nQueue retry receipt: ([a-f0-9-]{36})\n/);
  const outputId=output ? output[1] : job.id;
  if(job.kind==='edit' ? !job.prompt.startsWith('**USER-REQUESTED DESIGN CHANGES**\n') :
    (output && (!queueId.test(outputId) || retry?.[1]!==outputId)) ||
      !job.prompt.includes('morning_design_job_id = "'+outputId+'"'))return;
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

async function retireDesign(job) {
  const operation=pending.get(job.receipt);
  if(operation)operation.cancelled=true;
  const id=job.tab || operation?.tab;
  const tab=id ? await chrome.tabs.get(id).catch(()=>null) : null;
  const owned=tab && (tab.url===designProject || /^https:\/\/chatgpt\.com\/g\/g-p-6a1e449948e881919c1e345006d63654(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/.test(tab.url||''));
  if(owned && (!job.chatUrl || job.chatUrl===tab.url)) {
    let progress=await companionMessage(id,{type:'project:progress'},{frameId:0}).catch(()=>null);
    if(progress?.generating!==false) {
      const stopped=await companionMessage(id,{type:'project:cancel'},{frameId:0}).catch(()=>null);
      progress=await companionMessage(id,{type:'project:progress'},{frameId:0}).catch(()=>null);
      if(progress?.generating!==false && !(tab.url===designProject && stopped?.stopped)) {
        if(!job.stopReloaded) {
          await chrome.tabs.reload(id).catch(()=>{});
          await updateDesignJobs(jobs=>jobs[job.id] ? {...jobs,[job.id]:{...jobs[job.id],stopReloaded:true}} : jobs);
        }
        return false;
      }
    }
  }
  await save(job.receipt,'cancelled','Queue slot released; saved conversation and files retained. Restart only explicitly.');
  return true;
}

async function wakeDesignFromTab(sender) {
  if (sender.frameId !== 0 || !sender.tab ||
      !/^https:\/\/chatgpt\.com\/g\/g-p-6a1e449948e881919c1e345006d63654(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/.test(sender.url || '')) return {accepted:false};
  const jobs = await staffRead(designStorage) || {};
  if (!Object.values(jobs).some(job => job.tab === sender.tab.id && (!job.chatUrl || job.chatUrl === sender.url))) return {accepted:false};
  designTickRequested = true;
  await designQueueTick();
  return {accepted:true};
}

async function designQueueTick() {
  if (designTickRunning) return;
  designTickRunning = true;
  designTickRequested = false;
  try {
    const token = await staffRead(staffDeviceKey);
    if (!token) return;
    const jobs = await staffRead(designStorage) || {};
    const events = [];
    for (const job of Object.values(jobs).slice(0, 2)) {
      const report = await health(job.receipt);
      const tab = job.tab ? await chrome.tabs.get(job.tab).catch(() => null) : null;
      const progress = tab && ['submitted','uncertain'].includes(report.state) ? await companionMessage(job.tab, {type:'project:progress'}, {frameId:0}).catch(() => null) : null;
      if(report.state==='uncertain' && (progress?.generating || progress?.finished) && !progress.blocked) {
        await save(job.receipt,'submitted');report.state='submitted';
      }
      if(progress?.chat_url)await updateDesignJobs(current=>current[job.id] ? {...current,[job.id]:{...current[job.id],chatUrl:progress.chat_url}} : current);
      events.push({id:job.id, state:progress?.blocked ? 'blocked' : report.state, reason:progress?.reason || report.reason,
        activity:progress?.activity,finished:progress?.finished,generating:progress?.generating,
        chat_url:progress?.chat_url || tab?.url || ''});
    }
    const response = await fetch(osOrigin + '/api/morning-designs/tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json'},
      body:JSON.stringify({events, capacity:1}), credentials:'omit', signal:AbortSignal.timeout(25000),
    });
    if (!response.ok) return;
    const result = await response.json();
    if (!Array.isArray(result.jobs) || result.jobs.length > 2) return;
    const activeReceipts = new Map(result.jobs.map(job => [job.id,job.receipt]));
    // A deferred/cancelled job keeps its chat and can receive late delivery,
    // but its generation must stop before the next design starts.
    const current=await staffRead(designStorage)||{};
    for(const job of Object.values(current)) {
      if(activeReceipts.get(job.id)!==job.receipt && !await retireDesign(job))return;
    }
    // Reload after asynchronous stopping so concurrent tab references survive.
    await updateDesignJobs(current => Object.fromEntries(Object.entries(current).filter(([id,job]) => activeReceipts.get(id)===job.receipt)));
    // Preserve reports for jobs admitted before the rollback, but never start
    // a second design while another is running or open two new chats at once.
    if (!result.jobs.some(job => job.stage === 2 || job.stage === 3)) {
      const opening = result.jobs.find(job => job.stage === 1);
      if (opening) await startDesign(opening);
    }
  } catch {
    // Durable server claims and the local send journal survive network outages.
  } finally {
    designTickRunning = false;
    if (designTickRequested) void designQueueTick();
  }
}

async function ensureDesignAlarm() {
  if (!await chrome.alarms.get(designAlarm)) await chrome.alarms.create(designAlarm, {periodInMinutes:0.5});
}
chrome.alarms.onAlarm.addListener(alarm => {if (alarm.name === designAlarm) void designQueueTick();});
chrome.runtime.onStartup.addListener(() => {void ensureDesignAlarm().then(designQueueTick);});
chrome.runtime.onInstalled.addListener(async () => {
  // Existing saved chats still hold the previous content scripts after an
  // extension update. Reload only submitted chats, never a pending Send tab.
  const jobs=await staffRead(designStorage)||{};
  for(const job of Object.values(jobs)) {
    if((await health(job.receipt)).state!=='submitted' || !job.tab)continue;
    const tab=await chrome.tabs.get(job.tab).catch(()=>null);
    if(tab?.url?.startsWith(designProject.replace('/project','/c/')) ||
      /^https:\/\/chatgpt\.com\/g\/g-p-6a1e449948e881919c1e345006d63654-[a-z0-9-]+\/c\/[a-f0-9-]{36}$/.test(tab?.url||''))await chrome.tabs.reload(tab.id);
  }
  await ensureDesignAlarm();void designQueueTick();
});
