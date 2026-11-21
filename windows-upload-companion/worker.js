'use strict';

const project = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
const osOrigin = 'https://sports-cave-image-factory.onrender.com';
const osComponentPath = '/component/product_upload_gallery.product_upload_gallery/index.html';
const suppliedReceipt = /^[a-f0-9]{64}$/;
const pending = new Map();
const latest = 'uploadCompanionLast';
let queue = Promise.resolve();
importScripts('message-deadline.js');
importScripts('staff-queue.js');
importScripts('design-queue.js');
importScripts('ad-queue.js');
importScripts('orders-queue.js');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const keyFor = id => 'upload:' + id;

async function save(id, state, reason = '') {
  const record = {state, reason, time: Date.now()};
  await chrome.storage.local.set({[keyFor(id)]: record, [latest]: record});
}
function promptIsValid(prompt) {
  return typeof prompt === 'string' && prompt.length <= 1048576 &&
    prompt.startsWith('Run this Product Uploads workflow for ') &&
    prompt.includes('https://www.dropbox.com/home/') &&
    prompt.includes('STEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD');
}
async function run(id, prompt, job) {
  // A pending tabs.sendMessage Promise alone does not keep an MV3 worker alive.
  // Keep this bounded handoff alive while the page uploads; never run when idle.
  const keepAlive = setInterval(() => {
    void chrome.storage.local.get(keyFor(id)).catch(() => {});
  }, 20000);
  try {
    if (job.cancelled) return;
    const tab = await chrome.tabs.create({url: job.project || project, active: !job.adJob});
    job.tab = tab.id;
    if (!Number.isInteger(job.tab)) throw new Error();
    if (job.staffJob) await rememberChatTab(job.staffJob, job.tab);
    if (job.designJob) await rememberDesignTab(job.designJob, job.tab);
    if (job.adJob) await rememberAdTab(job.adJob, job.tab);
    const deadline = Date.now() + 18000;
    let ready;
    do {
      try { ready = await companionMessage(job.tab, {type:'project:ready'}, {frameId:0}); }
      catch { /* Edge has not loaded the project content script yet. */ }
      if (job.cancelled) return;
      if (ready?.ready) break;
      await delay(300);
    } while (Date.now() < deadline);
    if (!ready?.ready) {
      await save(id, 'failed', 'Open the project in this Edge profile and make sure ChatGPT is signed in.');
      return;
    }
    if (job.cancelled) return;
    const result = await companionMessage(job.tab, {type:'project:send', id, prompt,
      freshUpload:!job.designJob && !job.adJob, reference:job.reference}, {frameId:0});
    if (job.cancelled) return;
    if (result?.sent && job.sending) {
      await save(id, 'submitted');
    } else if (job.sending) {
      await save(id, 'uncertain', 'Check the new ChatGPT tab for the sent prompt before retrying.');
    } else {
      await save(id, 'failed', result?.reason || 'ChatGPT did not provide an empty project composer and a ready Send button.');
    }
  } catch {
    if (job.cancelled) return;
    await save(id, job.sending ? 'uncertain' : 'failed', job.sending
      ? 'Check the new ChatGPT tab for the sent prompt before retrying.'
      : 'Edge could not complete the project handoff.');
  } finally {
    clearInterval(keepAlive);
    pending.delete(id);
  }
}
async function start(message) {
  const {receipt, prompt, staffJob, reference} = message;
  if (!suppliedReceipt.test(receipt || '') || !promptIsValid(prompt)) return {accepted:false};
  if(reference && !await verifiedReference(reference))return {accepted:false};
  if (staffJob && !await rememberStaffReceipt(staffJob, receipt, message.senderTab)) return {accepted:false};
  if (pending.has(receipt)) return {accepted:true};
  if (pending.size >= 4) return {accepted:true, busy:true};
  const job = {tab:null, sending:false, staffJob, reference};
  pending.set(receipt, job);
  try {
    const key = keyFor(receipt);
    const state = (await chrome.storage.local.get(key))[key];
    if (['submitted', 'uncertain', 'sending', 'cancelled'].includes(state?.state)) {
      pending.delete(receipt);
      return {accepted:true};
    }
    await save(receipt, 'opening');
    queue = queue.then(() => run(receipt, prompt, job)).catch(() => {});
    return {accepted:true};
  } catch {
    pending.delete(receipt);
    return {accepted:false};
  }
}
async function verifiedReference(reference){
  if(reference.type!=='image/webp' || typeof reference.name!=='string' ||
     !reference.name.endsWith('.webp') || /[/\\]/.test(reference.name) ||
     !Number.isInteger(reference.size) || reference.size<1 || reference.size>16*1024*1024 ||
     typeof reference.data!=='string' || reference.data.length>24*1024*1024 ||
     !/^[A-Za-z0-9+/]*={0,2}$/.test(reference.data) || !suppliedReceipt.test(reference.sha256||''))return false;
  try{
    const bytes=Uint8Array.from(atob(reference.data),c=>c.charCodeAt(0));
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    return bytes.length===reference.size && hash===reference.sha256;
  }catch{return false;}
}
async function health(receipt) {
  const exact = suppliedReceipt.test(receipt || '');
  const key = exact ? keyFor(receipt) : latest;
  const record = (await chrome.storage.local.get(key))[key] || {state:'ready'};
  const active = exact ? pending.has(receipt) : pending.size > 0;
  const version = chrome.runtime.getManifest().version;
  const ordersState = await chrome.storage.local.get([staffDeviceKey, 'ordersCompanionLast']);
  const orders = {paired: Boolean(ordersState[staffDeviceKey]), last: ordersState.ordersCompanionLast || null};
  if (record.state === 'sending' && !active) return {
    state:'uncertain', reason:'Check the last ChatGPT tab for the sent prompt.', time:record.time, version,
  };
  if (record.state === 'opening' && !active) return {
    state:'failed', reason:'Edge closed before the prompt was sent. Retry from Product Uploads.', time:record.time, version,
  };
  return {...record, version, orders};
}
async function permit(message, sender) {
  const job = pending.get(message.id);
  if (!job || job.cancelled || sender.frameId !== 0 || sender.tab?.id !== job.tab || sender.url !== (job.project || project) || job.sending) {
    return {ok:false};
  }
  // Persist the send boundary before returning permission to click. No retry can
  // click again after an interrupted or unconfirmed send.
  job.sending = true;
  await save(message.id, 'sending');
  return {ok:true};
}
async function backupDraft(message, sender) {
  const job=pending.get(message.id);
  if (!job || job.sending || sender.frameId!==0 || sender.tab?.id!==job.tab ||
      sender.url!==(job.project || project) || typeof message.text!=='string' || !message.text.trim() ||
      message.text.length>1048576) return {ok:false};
  await chrome.storage.local.set({['draft:'+message.id]:{text:message.text, time:Date.now(), project:job.project || project}});
  return {ok:true};
}
function isOsComponent(address) {
  try {
    const url = new URL(address);
    // Streamlit appends streamlitUrl to the component iframe URL.
    return url.origin === osOrigin && url.pathname === osComponentPath && !url.username && !url.password;
  } catch {
    return false;
  }
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  let action;
  if(message?.type==='os:wake-designs' && sender.frameId===0 &&
      sender.url && new URL(sender.url).origin===osOrigin) {
    action=designQueueTick().then(()=>({accepted:true}));
  } else
  if (message?.type === 'project:permit') {
    action = permit(message, sender);
  } else if (message?.type === 'project:backup-draft') {
    action = backupDraft(message, sender);
  } else if (message?.type === 'project:design-progress') {
    action = wakeDesignFromTab(sender);
  } else if (message?.type === 'project:blocked' && sender.frameId === 0) {
    action = recordChatBlock(sender, message.code);
  } else if (sender.frameId > 0 && sender.tab && isOsComponent(sender.url)) {
    if (message?.type === 'os:health') action = health(message.receipt);
    if (message?.type === 'os:start') action = start({...message, senderTab:sender.tab.id}).then(result => ({...result, version:chrome.runtime.getManifest().version}));
    if (message?.type === 'os:pair') action = pairStaffQueue(message.token);
    if (message?.type === 'os:wake') action = staffRead(staffDeviceKey).then(async token => {
      if (!token) return {paired:false};
      await ensureStaffAlarm();
      await ensureOrdersAlarm();
      void ordersQueueTick();
      void staffQueueTick();
      return {paired:true};
    });
  }
  if (!action) return;
  action.then(reply, () => reply({error:true}));
  return true;
});
