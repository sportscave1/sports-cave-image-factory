'use strict';

const adProject = 'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project';
const adStorage = 'publishAdJob';
let adTickRunning = false;
let adFollowupTimer = null;
function followUpAdTransfer(outcome) {
  // One prompt-free fast check after progress, with the durable alarm as fallback.
  if (!['download-started','received'].includes(outcome) || adFollowupTimer !== null) return;
  adFollowupTimer = setTimeout(() => {adFollowupTimer=null;void adQueueTick();}, outcome==='received'?250:1000);
}
const adChat = /^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/;
const adLibrary=/^https:\/\/chatgpt\.com\/library\?file_id=libfile_[a-f0-9]+$/;

async function repairAd(job,tab,token,local) {
  const repair=job.repair;
  local={...local,chat_url:job.chat_url};
  await staffWrite(adStorage,{...local,repair});
  const message={job:job.id,repair:repair.id,chat:job.chat_url,names:repair.names};
  const status=await companionMessage(tab.id,{type:'project:ad-repair-status',...message},{frameId:0}).catch(()=>null);
  if(!status && local.repairReload!==repair.id) {
    await staffWrite(adStorage,{...local,repair,repairReload:repair.id});
    await chrome.tabs.reload(tab.id);return;
  }
  if(status?.found)return;
  // Continue only our exact journalled, unclicked draft. Never reissue a Send
  // after a click or infer non-submission from virtualized/absent chat history.
  if(repair.state==='sending' && status?.staged) {
    await companionMessage(tab.id,{type:'project:ad-repair-send',...message,resume:true},{frameId:0});return;
  }
  if(!status?.ready || repair.state!=='ready')return;
  // The server's job lease serializes claims across tabs/restarts. A lost
  // response consumes the permit: reconcile the marker, never repeat Send.
  const response=await fetch(osOrigin+'/api/staff-product-uploads/ad-tick',{
    method:'POST',credentials:'omit',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},
    body:JSON.stringify({id:job.id,repair_claim:repair.id}),signal:AbortSignal.timeout(25000)});
  if(!response.ok)return;
  const claimed=(await response.json()).job;
  if(!claimed?.repair_send || claimed.id!==job.id || claimed.chat_url!==job.chat_url || claimed.repair?.id!==repair.id)return;
  await staffWrite(adStorage,{...local,repair:claimed.repair});
  await companionMessage(tab.id,{type:'project:ad-repair-send',...message,names:claimed.repair.names,permit:true},{frameId:0});
}

async function failedAdDownload(local,tab,reason) {
  const failures=(local.downloadFailures||0)+1;
  const failed=failures>=3;
  await staffWrite(adStorage,{...local,transfer:null,downloadFailures:failures,transferFailed:failed,
    transferError:failed ? 'Attachment download failed after three attempts; requesting automatic repair in the saved chat.' :
      reason+'. Refreshing the saved chat and retrying the same attachment.'});
  if(!failed)await chrome.tabs.reload(tab.id);
}

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
  if(job.repair && ['ready','sending'].includes(job.repair.state))return repairAd(job,tab,token,local);
  if(job.repair?.state==='submitted' && (local.repair?.id!==job.repair.id || local.repair?.state!=='submitted')) {
    local={...local,repair:job.repair,transfer:null,transferError:'',downloadFailures:0,transferFailed:false};
    await staffWrite(adStorage,local);
  }
  if(job.resume_token && local.resume_token!==job.resume_token) {
    await chrome.tabs.reload(tab.id);
    await staffWrite(adStorage,{...local,resume_token:job.resume_token,transfer:null,transferError:'',downloadFailures:0,transferFailed:false});return;
  }
  const names=['ad_copy.csv','collector-hallway.jpg','architectural-wall.jpg','man-cave.jpg'];
  const name=names.find(file=>job.missing?.includes(file));
  if(!name)return;
  if(local.transferFailed)return;
  const maxBytes=(name.endsWith('.csv')?2:20)*1024*1024;
  let transfer=local.transfer;
  if(transfer?.name!==name)transfer=null;
  if(!transfer) {
    const started=new Date().toISOString();
    const result=await companionMessage(tab.id,{type:'project:ad-artifact',job:job.id,name,response:job.response_ids?.[name],recover:job.recover,repair:job.repair?.id,chat:job.chat_url},{frameId:0});
    if(!result?.clicked) {
      await staffWrite(adStorage,{...local,transfer:null,transferError:result?.reason||'Waiting for downloadable attachments'});return;
    }
    transfer={name,started,response:result.response,library:adLibrary.test(result.library||'')?result.library:undefined};
    await staffWrite(adStorage,{...local,transfer,transferError:''});return 'download-started';
  }
  const downloads=await chrome.downloads.search({startedAfter:transfer.started,limit:30});
  // Cross-origin downloads may reduce the native referrer to the ChatGPT origin.
  // Require a unique named download after our recorded click in either case.
  const candidates=downloads.filter(item=>[job.chat_url,'https://chatgpt.com/',...(transfer.libraryTab?[transfer.library]:[])].includes(item.referrer) &&
    item.filename.replaceAll('\\','/').split('/').pop().replace(/ \(\d+\)(?=\.[^.]+$)/,'')
      .replace(transfer.libraryTab?/\(\d{8}-\d{6}\)(?=\.[^.]+$)/:/$^/,'')===name);
  if(candidates.length!==1) {
    const status=await companionMessage(tab.id,{type:'project:ad-download-status',job:job.id,name,
      response:transfer.response,chat:job.chat_url},{frameId:0}).catch(()=>null);
    if(status?.error || Date.now()-Date.parse(transfer.started)>120000) {
      if(adLibrary.test(transfer.library||'') && !transfer.librarySent) {
        // A Library viewer can load without a usable Download button.
        // Bound that wait so this branch also spends its retry budget.
        if(transfer.libraryTab && Date.now()-Date.parse(transfer.libraryOpenedAt||transfer.started)>120000) {
          await failedAdDownload(local,tab,'Library original did not become downloadable');return;
        }
        let original=transfer.libraryTab?await chrome.tabs.get(transfer.libraryTab).catch(()=>null):null;
        if(!original) {
          original=await chrome.tabs.create({url:transfer.library,active:false});
          await staffWrite(adStorage,{...local,transfer:{...transfer,libraryTab:original.id,libraryOpenedAt:new Date().toISOString()}});return;
        }
        if(original.url!==transfer.library){await failedAdDownload(local,tab,'Library original changed');return;}
        // Record before clicking: a fast native download can start before the
        // content-script reply. Recording after it loses that exact receipt.
        const libraryStarted=new Date().toISOString();
        const restored=await companionMessage(original.id,{type:'project:ad-library',job:job.id,name,url:transfer.library},{frameId:0}).catch(()=>null);
        if(restored?.clicked) {
          await staffWrite(adStorage,{...local,transfer:{...transfer,started:libraryStarted,librarySent:true}});return 'download-started';
        }
        return; // Let this viewer finish loading within its bounded wait.
      }
      await failedAdDownload(local,tab,status?.error||'No browser download receipt');
    }
    return;
  }
  const item=candidates[0];
  if(item.state==='interrupted'){await failedAdDownload(local,tab,'Attachment download interrupted');return;}
  if(item.state!=='complete') {
    if(Date.now()-Date.parse(transfer.started)>120000)await failedAdDownload(local,tab,'Attachment download did not finish');
    return;
  }
  const url=new URL(item.finalUrl||item.url);
  let data;
  if(url.protocol==='blob:' && url.origin==='https://chatgpt.com') {
    const result=transfer.librarySent
      ? await companionMessage(transfer.libraryTab,{type:'project:ad-library-blob',job:job.id,name,url:transfer.library,blob:url.href},{frameId:0})
      : await companionMessage(tab.id,{type:'project:ad-blob',job:job.id,name,response:transfer.response,recover:job.recover,repair:job.repair?.id,chat:job.chat_url,url:url.href},{frameId:0});
    if(!result?.data) {
      await failedAdDownload(local,tab,result?.error||'Original download expired');return;
    }
    if(result.data.length>Math.ceil(maxBytes/3)*4)throw Error('Ad file exceeds transfer limit');
    data=Uint8Array.from(atob(result.data),char=>char.charCodeAt(0));
    if(data.length>maxBytes)throw Error('Ad file exceeds transfer limit');
  } else {
    if(url.protocol!=='https:' || url.username || url.password ||
      !(url.hostname==='chatgpt.com'||url.hostname.endsWith('.oaiusercontent.com')))throw Error('Unapproved artifact download host');
    const response=await fetch(url.href,{credentials:'include',signal:AbortSignal.timeout(25000)});
    if(!response.ok){
      await failedAdDownload(local,tab,'Download link expired');
      return;
    }
    const finalURL=new URL(response.url||url.href);
    if(finalURL.protocol!=='https:' || !(finalURL.hostname==='chatgpt.com'||finalURL.hostname.endsWith('.oaiusercontent.com')))throw Error('Unapproved artifact redirect');
    const reader=response.body.getReader(),chunks=[];let size=0;
    while(true){const {done,value}=await reader.read();if(done)break;size+=value.length;
      if(size>maxBytes){await reader.cancel();throw Error('Ad file exceeds transfer limit');}chunks.push(value);}
    data=new Uint8Array(size);let offset=0;for(const chunk of chunks){data.set(chunk,offset);offset+=chunk.length;}
  }
  const query=new URLSearchParams({job:job.id,name,chat:job.chat_url,response:transfer.response});
  const response=await fetch(osOrigin+'/api/staff-product-uploads/ad-file?'+query,{
    method:'POST',credentials:'omit',headers:{Authorization:'Bearer '+token,'Content-Type':'application/octet-stream'},
    body:data,signal:AbortSignal.timeout(60000)});
  const receipt=await response.json();
  if(!response.ok)throw Error(receipt.error||'Ad file receipt was not confirmed');
  if(receipt.received!==name)throw Error('Ad file receipt mismatch');
  await staffWrite(adStorage,{...local,transfer:null,transferError:'',downloadFailures:0,transferFailed:false});
  return 'received';
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
    const repairStatus=local?.repair && local.repair.state!=='submitted' && local.tab
      ? await companionMessage(local.tab,{type:'project:ad-repair-status',job:local.id,repair:local.repair.id,
          chat:local.chat_url,names:local.repair.names},{frameId:0}).catch(()=>null) : null;
    const report = local?.receipt ? await health(local.receipt) : {};
    // A missed send receipt is not a failed generation. Reconcile only the
    // exact tab created for this job; never resend or adopt an unrelated chat.
    const observing = ['submitted','uncertain','sending'].includes(report.state);
    const tab = local?.tab && observing ? await chrome.tabs.get(local.tab).catch(()=>null) : null;
    const progress = tab && adChat.test(tab.url||'')
      ? await companionMessage(local.tab, {type:'project:progress'}, {frameId:0}).catch(() => null) : null;
    const matched = progress && progress.chat_url === tab?.url && adChat.test(progress.chat_url||'') &&
      (!local.chat_url || local.chat_url === progress.chat_url);
    if (matched && (progress.generating || progress.finished) && report.state !== 'submitted') {
      await save(local.receipt,'submitted');
      report.state='submitted';report.reason='';
    }
    if(matched && local.chat_url!==progress.chat_url)
      await staffWrite(adStorage,{...local,chat_url:progress.chat_url});
    const response = await fetch(osOrigin + '/api/staff-product-uploads/ad-tick', {
      method:'POST', headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json'},
      body:JSON.stringify({id:local?.id, state:matched && progress.blocked ? 'blocked' : report.state,
                          reason:matched && progress.reason || report.reason, chat_url:matched ? progress.chat_url : undefined,
                          generating:matched ? progress.generating : undefined,
                          finished:matched ? progress.finished : undefined, activity:matched ? progress.activity : undefined,
                          transfer_detail:local?.transferError,transfer_failed:local?.transferFailed===true,
                          repair_id:local?.repair?.id,repair_seen:repairStatus?.found?local.repair.id:undefined}),
      credentials:'omit', signal:AbortSignal.timeout(25000),
    });
    if (!response.ok) return;
    const {job, busy, stop} = await response.json();
    if(stop?.id===local?.id && local) {
      const operation=pending.get(local.receipt);if(operation)operation.cancelled=true;
      if(local.tab)await companionMessage(local.tab,{type:'project:cancel'},{frameId:0}).catch(()=>null);
      await chrome.storage.local.remove(adStorage);return;
    }
    if (busy) return;
    if (!job) await chrome.storage.local.remove(adStorage);
    else if (job.stage === 'opening') await startAd(job);
    else if (job.stage === 'generating') followUpAdTransfer(await collectAd(job,token));
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
chrome.runtime.onInstalled.addListener(async () => {
  // Existing tabs still hold the previous content scripts after an update.
  const local=await staffRead(adStorage);
  const tab=local?.tab ? await chrome.tabs.get(local.tab).catch(()=>null) : null;
  if(tab && adChat.test(tab.url||''))await chrome.tabs.reload(tab.id);
  void adQueueTick();
});
