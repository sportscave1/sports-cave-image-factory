'use strict';

const adProject = 'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project';
const adStorage = 'publishAdJob';
let adTickRunning = false;
const adChat = /^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/;

async function collectAd(job, token) {
  if(!adChat.test(job.chat_url||'') || !queueId.test(job.id) || !suppliedReceipt.test(job.receipt))return;
  let local=await staffRead(adStorage);
  if(local?.id!==job.id)local={id:job.id,receipt:job.receipt};
  let tab=local.tab ? await chrome.tabs.get(local.tab).catch(()=>null) : null;
  if(tab?.url!==job.chat_url) {
    tab=(await chrome.tabs.query({url:'https://chatgpt.com/*'})).find(item=>item.url===job.chat_url);
    if(!tab)tab=await chrome.tabs.create({url:job.chat_url,active:false});
    local={...local,tab:tab.id};await staffWrite(adStorage,local);return;
  }
  await chrome.tabs.update(tab.id,{autoDiscardable:false});
  if(job.resume_token && local.resume_token!==job.resume_token) {
    await chrome.tabs.reload(tab.id);
    await staffWrite(adStorage,{...local,resume_token:job.resume_token,transfer:null,transferError:''});return;
  }
  const names=['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'];
  const name=names.find(file=>job.missing?.includes(file));
  if(!name)return;
  let transfer=local.transfer;
  if(transfer?.name!==name)transfer=null;
  if(!transfer) {
    const started=new Date().toISOString();
    const result=await chrome.tabs.sendMessage(tab.id,{type:'project:ad-artifact',job:job.id,name,response:job.response_ids?.[name],recover:job.recover,chat:job.chat_url},{frameId:0});
    if(!result?.clicked) {
      await staffWrite(adStorage,{...local,transfer:null,transferError:result?.reason||'Waiting for downloadable attachments'});return;
    }
    transfer={name,started,response:result.response};
    await staffWrite(adStorage,{...local,transfer,transferError:''});return;
  }
  const downloads=await chrome.downloads.search({startedAfter:transfer.started,limit:30});
  // Cross-origin downloads may reduce the native referrer to the ChatGPT origin.
  // Require a unique named download after our recorded click in either case.
  const candidates=downloads.filter(item=>[job.chat_url,'https://chatgpt.com/'].includes(item.referrer) &&
    item.filename.replaceAll('\\','/').split('/').pop().replace(/ \(\d+\)(?=\.[^.]+$)/,'')===name);
  if(candidates.length!==1) {
    if(Date.now()-Date.parse(transfer.started)>120000)await staffWrite(adStorage,{...local,transfer:null,transferError:'Download was not confirmed. Retrying the same original attachment.'});
    return;
  }
  const item=candidates[0];
  if(item.state==='interrupted'){await staffWrite(adStorage,{...local,transfer:null,transferError:'Attachment download interrupted; retrying.'});return;}
  if(item.state!=='complete')return;
  const url=new URL(item.finalUrl||item.url);
  let data;
  if(url.protocol==='blob:' && url.origin==='https://chatgpt.com') {
    const result=await chrome.tabs.sendMessage(tab.id,{type:'project:ad-blob',job:job.id,name,response:transfer.response,recover:job.recover,chat:job.chat_url,url:url.href},{frameId:0});
    if(!result?.data) {
      await staffWrite(adStorage,{...local,transfer:null,transferError:result?.error||'Original download expired; retrying the same attachment'});return;
    }
    data=Uint8Array.from(atob(result.data),char=>char.charCodeAt(0));
  } else {
    if(url.protocol!=='https:' || url.username || url.password ||
      !(url.hostname==='chatgpt.com'||url.hostname.endsWith('.oaiusercontent.com')))throw Error('Unapproved artifact download host');
    const response=await fetch(url.href,{credentials:'include',signal:AbortSignal.timeout(25000)});
    if(!response.ok){
      await staffWrite(adStorage,{...local,transfer:null,transferError:'Download link expired; requesting the original attachment again.'});
      return;
    }
    const finalURL=new URL(response.url||url.href);
    if(finalURL.protocol!=='https:' || !(finalURL.hostname==='chatgpt.com'||finalURL.hostname.endsWith('.oaiusercontent.com')))throw Error('Unapproved artifact redirect');
    const reader=response.body.getReader(),chunks=[];let size=0;
    while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
      if(size>20*1024*1024){await reader.cancel();throw Error('Ad file exceeds transfer limit');}chunks.push(value);}
    data=new Uint8Array(size);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length;}
  }
  const query=new URLSearchParams({job:job.id,name,chat:job.chat_url,response:transfer.response});
  const response=await fetch(osOrigin+'/api/staff-product-uploads/ad-file?'+query,{
    method:'POST',credentials:'omit',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},
    body:data,signal:AbortSignal.timeout(60000)});
  const receipt=await response.json();
  if(!response.ok)throw Error(receipt.error||'Ad file receipt was not confirmed');
  if(receipt.received!==name)throw Error('Ad file receipt mismatch');
  await staffWrite(adStorage,{...local,transfer:null,transferError:''});
}

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
  const keepAlive=setInterval(()=>{void chrome.storage.local.get(adStorage).catch(()=>{});},20000);
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
                          reason:progress?.reason || report.reason, chat_url:progress?.chat_url,
                          transfer_detail:local?.transferError}),
      credentials:'omit', signal:AbortSignal.timeout(25000),
    });
    if (!response.ok) return;
    const {job, busy, stop} = await response.json();
    if(stop?.id===local?.id && local) {
      const operation=pending.get(local.receipt);if(operation)operation.cancelled=true;
      if(local.tab)await chrome.tabs.sendMessage(local.tab,{type:'project:cancel'},{frameId:0}).catch(()=>null);
      await chrome.storage.local.remove(adStorage);return;
    }
    if (busy) return;
    if (!job) await chrome.storage.local.remove(adStorage);
    else if (job.stage === 'opening') await startAd(job);
    else if (job.stage === 'generating') await collectAd(job,token);
  } catch(error) {
    const local=await staffRead(adStorage);
    if(local)await staffWrite(adStorage,{...local,transferError:String(error.message||'Ad transfer interrupted').slice(0,300)});
    // The durable server checkpoint and local send journal survive an interrupted poll.
  } finally {
    clearInterval(keepAlive);
    adTickRunning = false;
  }
}

chrome.alarms.onAlarm.addListener(alarm => {if (alarm.name === staffAlarm) void adQueueTick();});
chrome.runtime.onStartup.addListener(() => {void adQueueTick();});
chrome.runtime.onInstalled.addListener(() => {void adQueueTick();});
