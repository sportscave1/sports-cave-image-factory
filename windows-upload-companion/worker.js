'use strict';

const project = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
const osComponent = /^https:\/\/sports-cave-image-factory\.onrender\.com\/component\/product_upload_gallery\.product_upload_gallery\/[^?#]*$/;
const suppliedReceipt = /^[a-f0-9]{64}$/;
const pending = new Map();
const latest = 'uploadCompanionLast';
let queue = Promise.resolve();
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const keyFor = id => 'upload:' + id;

async function save(id, state, reason = '') {
  const record = {state, reason, time: Date.now()};
  await chrome.storage.local.set({[keyFor(id)]: record, [latest]: record});
}
function promptIsValid(prompt) {
  return typeof prompt === 'string' && prompt.length <= 131072 &&
    prompt.startsWith('Run this Product Uploads workflow for ') &&
    prompt.includes('https://www.dropbox.com/home/') &&
    prompt.includes('STEP 5 — VERIFY EDITION OPS AND ATTACH THE ORIGINAL PSD');
}
async function run(id, prompt, job) {
  try {
    const tab = await chrome.tabs.create({url: project, active: true});
    job.tab = tab.id;
    if (!Number.isInteger(job.tab)) throw new Error();
    const deadline = Date.now() + 18000;
    let ready;
    do {
      try { ready = await chrome.tabs.sendMessage(job.tab, {type:'project:ready'}, {frameId:0}); }
      catch { /* Edge has not loaded the project content script yet. */ }
      if (ready?.ready) break;
      await delay(300);
    } while (Date.now() < deadline);
    if (!ready?.ready) {
      await save(id, 'failed', 'Open the project in this Edge profile and make sure ChatGPT is signed in.');
      return;
    }
    const result = await chrome.tabs.sendMessage(job.tab, {type:'project:send', id, prompt}, {frameId:0});
    if (result?.sent && job.sending) {
      await save(id, 'submitted');
    } else if (job.sending) {
      await save(id, 'uncertain', 'Check the new ChatGPT tab for the sent prompt before retrying.');
    } else {
      await save(id, 'failed', 'ChatGPT did not provide an empty project composer and a ready Send button.');
    }
  } catch {
    await save(id, job.sending ? 'uncertain' : 'failed', job.sending
      ? 'Check the new ChatGPT tab for the sent prompt before retrying.'
      : 'Edge could not complete the project handoff.');
  } finally {
    pending.delete(id);
  }
}
async function start(message) {
  const {receipt, prompt} = message;
  if (!suppliedReceipt.test(receipt || '') || !promptIsValid(prompt)) return {accepted:false};
  if (pending.has(receipt)) return {accepted:true};
  if (pending.size >= 4) return {accepted:true, busy:true};
  const job = {tab:null, sending:false};
  pending.set(receipt, job);
  try {
    const key = keyFor(receipt);
    const state = (await chrome.storage.local.get(key))[key];
    if (state?.state === 'submitted' || state?.state === 'uncertain' || state?.state === 'sending') {
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
async function health() {
  const record = (await chrome.storage.local.get(latest))[latest];
  if (record && record.state === 'sending' && !pending.size) return {
    state:'uncertain', reason:'Check the last ChatGPT tab for the sent prompt.', time:record.time,
  };
  if (record && record.state === 'opening' && !pending.size) return {
    state:'failed', reason:'Edge closed before the prompt was sent. Retry from Product Uploads.', time:record.time,
  };
  return record || {state:'ready'};
}
async function permit(message, sender) {
  const job = pending.get(message.id);
  if (!job || sender.frameId !== 0 || sender.tab?.id !== job.tab || sender.url !== project || job.sending) {
    return {ok:false};
  }
  // Persist the send boundary before returning permission to click. No retry can
  // click again after an interrupted or unconfirmed send.
  job.sending = true;
  await save(message.id, 'sending');
  return {ok:true};
}
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  let action;
  if (message?.type === 'project:permit') {
    action = permit(message, sender);
  } else if (sender.frameId > 0 && sender.tab && osComponent.test(sender.url || '')) {
    if (message?.type === 'os:health') action = health();
    if (message?.type === 'os:start') action = start(message);
  }
  if (!action) return;
  action.then(reply, () => reply({error:true}));
  return true;
});
