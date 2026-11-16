'use strict';

const staffAlarm = 'sports-cave-staff-queue';
const staffDeviceKey = 'staffQueueCredential';
const staffJobKey = 'staffQueueJob';
const queueId = /^[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}$/;
const blockedReasons = {
  REFERENCE:'ChatGPT could not retrieve the original black-frame WebP.',
  GENERATION:'ChatGPT could not generate or convert all three lifestyle mockups.',
  DROPBOX:'ChatGPT could not confirm the complete eight-WebP Dropbox package.',
  SHOPIFY:'ChatGPT could not verify the live Shopify listing.',
  EDITION_SYNC:'ChatGPT could not find the exact listing in Edition Ops.',
  PSD_MOVE:'ChatGPT could not move the original PSD from Review to Live.',
  PSD_MAPPING:'ChatGPT could not confirm the original PSD mapping in Edition Ops.',
  APPROVAL:'ChatGPT paused for an approval. Open the upload conversation to review the requested action.',
};
const staffRead = async key => (await chrome.storage.local.get(key))[key];
const staffWrite = (key, value) => chrome.storage.local.set({[key]:value});
let staffTickRunning = false;

async function pairStaffQueue(token) {
  if (typeof token !== 'string' || !/^[A-Za-z0-9_-]{43}$/.test(token)) return {paired:false};
  await staffWrite(staffDeviceKey, token);
  await ensureStaffAlarm();
  void staffQueueTick();
  return {paired:true};
}

async function ensureStaffAlarm() {
  if (await staffRead(staffDeviceKey) && !await chrome.alarms.get(staffAlarm)) {
    await chrome.alarms.create(staffAlarm, {periodInMinutes:0.5});
  }
}

async function rememberStaffReceipt(id, receipt, tab) {
  const job = await staffRead(staffJobKey);
  if (!queueId.test(id) || job?.id !== id || job.tab !== tab) return false;
  await staffWrite(staffJobKey, {...job, receipt});
  return true;
}

async function rememberChatTab(id, chatTab) {
  const job = await staffRead(staffJobKey);
  if (job?.id === id) await staffWrite(staffJobKey, {...job, chatTab});
}

async function recordChatBlock(sender, code) {
  const job = await staffRead(staffJobKey);
  const scopedChat = /^https:\/\/chatgpt\.com\/g\/g-p-6a387a17627081918e1700ec2783a12b(?:-sc-mockups-uploads)?\/c\/[a-f0-9-]{36}$/;
  if (!job?.chatTab || sender.tab?.id !== job.chatTab || !scopedChat.test(sender.url || '') ||
      !Object.hasOwn(blockedReasons, code)) return;
  await staffWrite(staffJobKey, {...job, blocked:blockedReasons[code]});
}

async function staffQueueTick() {
  if (staffTickRunning) return;
  staffTickRunning = true;
  try {
    const token = await staffRead(staffDeviceKey);
    if (!token) return;
    const local = await staffRead(staffJobKey);
    const report = local?.receipt ? await health(local.receipt) : {};
    const event = local?.blocked && report.state === 'submitted'
      ? {id:local.id, state:'blocked', reason:local.blocked}
      : {id:local?.id, state:report.state, reason:report.reason};
    const response = await fetch(osOrigin + '/api/staff-product-uploads/tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json'},
      body:JSON.stringify(event), credentials:'omit', signal:AbortSignal.timeout(20000),
    });
    if (!response.ok) return;
    const {job} = await response.json();
    if (!job || !queueId.test(job.id) || job.stage >= 5) return;
    const url = new URL('/', osOrigin);
    url.searchParams.set('page', 'product_uploads');
    url.searchParams.set('staff_upload_job', job.id);
    if (local?.id === job.id) {
      const existing = await chrome.tabs.get(local.tab).catch(() => null);
      const address = existing?.pendingUrl || existing?.url;
      if (address && new URL(address).searchParams.get('staff_upload_job') === job.id) return;
      if (local.receipt && ['sending', 'submitted', 'uncertain'].includes(report.state)) return;
    }
    const tab = await chrome.tabs.create({url:url.href, active:false});
    await staffWrite(staffJobKey, {id:job.id, tab:tab.id});
  } catch {
    // Browser startup and connectivity failures are retried by the next alarm.
  } finally {
    staffTickRunning = false;
  }
}

chrome.alarms.onAlarm.addListener(alarm => {if (alarm.name === staffAlarm) void staffQueueTick();});
chrome.runtime.onStartup.addListener(() => {void ensureStaffAlarm().then(staffQueueTick);});
chrome.runtime.onInstalled.addListener(() => {void ensureStaffAlarm().then(staffQueueTick);});
