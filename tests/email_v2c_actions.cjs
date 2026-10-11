// Actual Streamlit component, synthetic mail, disposable SQL, loopback requests only.
const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
const port=process.argv[2]||'8553',label=process.argv[3]||'after',out='docs/email-inbox-outlook-v2c-evidence';
const stats=a=>{a=[...a].sort((a,b)=>a-b);return a.length?{n:a.length,p50_ms:+a[Math.floor(a.length/2)].toFixed(2),p95_ms:+a[Math.ceil(a.length*.95)-1].toFixed(2)}:{n:0}};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
 try{for(const width of [1440,768,390]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  await page.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
  await page.addInitScript(()=>{window.__v2a={};window.addEventListener('message',e=>{
   if(e.data?.type==='streamlit:setComponentValue'){try{const a=e.source.__v2a;a.lastEvent=e.data.value;if(a.action===e.data.value.action){a.expected=e.data.value.id;a.started=performance.now();}}catch(_){}}
   if(e.data?.type==='streamlit:render'){const a=window.__v2a;a.model=e.data.args.model;if(a.expected&&a.model.ack===a.expected){requestAnimationFrame(()=>{a.ack=performance.now()-a.t;a.expected=null;});}}
  });});
  const navigation=[];
  await page.goto(`http://127.0.0.1:${port}/?actor=${crypto.randomUUID()}`);
  await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation-wrap').first().waitFor({timeout:20000});
  for(let i=0;i<5;i++){const t=performance.now();await page.goto(`http://127.0.0.1:${port}/?actor=${crypto.randomUUID()}`);await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation-wrap').first().waitFor({timeout:20000});navigation.push(performance.now()-t);}
  const frame=page.frames().find(f=>f.url().includes('/component/'));
  async function act(selector,action){
   await frame.waitForFunction(s=>{const b=document.querySelector(s);return b&&!b.disabled},selector);
   const immediate=await frame.evaluate(({s,action})=>new Promise(resolve=>{const b=document.querySelector(s),a=window.__v2a;a.ack=null;a.action=action||b.dataset.action;a.t=performance.now();b.click();requestAnimationFrame(()=>resolve({ms:performance.now()-a.t,body:!!document.querySelector('.message-body,.email-document'),text:document.querySelector('#send-status')?.textContent}));}),{s:selector,action});
   await frame.waitForFunction(()=>window.__v2a.ack!==null,null,{timeout:20000});return {...immediate,ack:await frame.evaluate(()=>window.__v2a.ack)};
  }
  const first='.conversation-wrap:nth-child(1) .conversation',second='.conversation-wrap:nth-child(2) .conversation';
  await act(first);await frame.waitForFunction(()=>window.__v2a.model.messages.some(m=>m.expanded));
  await act(second);await frame.waitForFunction(()=>window.__v2a.model.messages.some(m=>m.expanded));
  const incomplete=[],cached=[],reply=[],save=[],restore=[],flags=[],sync=[],send=[],archive=[],move=[];
  for(let i=0;i<20;i++)cached.push(await act(i%2?first:second));
  for(let i=0;i<10;i++){
   reply.push(await act('[data-action="compose"][data-mode="reply"]'));
   await frame.locator('#editor').fill('Synthetic revision '+i);
   const t=performance.now();await frame.waitForFunction(()=>document.querySelector('#draft-save-status')?.textContent==='Saved',null,{timeout:10000});save.push(performance.now()-t);
   await act('[data-action="close_composer"]');
   restore.push(await act('[data-action="resume_composer"]'));
   await act('[data-action="close_composer"]');
  }
  for(let i=0;i<10;i++){
   if(await frame.locator('.reading-toolbar [data-action="mark_read"]').count())await act('.reading-toolbar [data-action="mark_read"]');
   flags.push(await act('[data-action="mark_unread"]'));
   await act('[data-action="mark_read"]');
   // Trigger the real background handler via component events, not direct application state edits.
   const ack=await frame.evaluate(()=>new Promise(resolve=>{const a=window.__v2a;a.ack=null;a.action='live_check';a.t=performance.now();parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',dataType:'json',value:{id:crypto.randomUUID(),action:'live_check'}},'*');requestAnimationFrame(()=>resolve(performance.now()-a.t));}));
   await frame.waitForFunction(()=>window.__v2a.ack!==null);sync.push({ms:ack,ack:await frame.evaluate(()=>window.__v2a.ack)});
  }
  for(let i=0;i<5;i++){
   await act('[data-action="compose"][data-mode="new"]');
   await frame.locator('#draft-to').fill('synthetic@example.test');await frame.locator('#draft-subject').fill('Local mocked send');await frame.locator('#editor').fill('No real transport.');
   send.push(await act('[data-action="send"]'));
   await frame.waitForFunction(()=>window.__v2a.model.send_stage==='SENT',null,{timeout:20000});
   await act('[data-action="folder"][data-folder="INBOX"]');
  }
  for(let i=0;i<10;i++){
   await act(`.conversation-wrap:nth-child(${i+1}) .conversation`);
   await frame.waitForFunction(()=>window.__v2a.model.messages.some(m=>m.expanded));
   const sender=await frame.evaluate(()=>window.__v2a.model.threads.find(t=>t.key===window.__v2a.model.selected).email);
   archive.push(await act('[data-action="archive"]'));
   await act('[data-action="folder"][data-folder="Archive"]');
   try{await frame.waitForFunction(email=>window.__v2a.model.threads.some(t=>t.email===email),sender,{timeout:10000});}catch(e){if(label!=='before')throw e;incomplete.push('Baseline archive acknowledged but archived sender was absent from destination; move comparison unavailable.');break;}
   const selected=await frame.evaluate(email=>window.__v2a.model.threads.find(t=>t.email===email).key,sender);
   await act(`.conversation[data-key="${selected}"]`);
   await frame.waitForFunction(()=>window.__v2a.model.messages.some(m=>m.expanded));
   await frame.locator('.reading-toolbar [data-action="message_menu"]').evaluate(b=>b.click());
   await frame.locator('[data-menu-action="move"]').evaluate(b=>b.click());
   move.push(await act('[data-menu-action="move_to"][data-destination="Customers"]','move'));
   await act('[data-action="folder"][data-folder="INBOX"]');
  }
  await page.screenshot({path:`${out}/${label}-${width}.png`});
  const measurements={list_paint:stats(navigation),cached_paint:stats(cached.map(x=>x.ms)),cached_ack:stats(cached.map(x=>x.ack)),cached_body_present:cached.filter(x=>x.body).length,
    reply_ack:stats(reply.map(x=>x.ack)),autosave_including_debounce:stats(save),resume_ack:stats(restore.map(x=>x.ack)),mark_unread_ack:stats(flags.map(x=>x.ack)),background_ack:stats(sync.map(x=>x.ack)),send_feedback:stats(send.map(x=>x.ms)),send_prepare_ack:stats(send.map(x=>x.ack)),send_text:send.map(x=>x.text),archive_ack:stats(archive.map(x=>x.ack)),move_ack:stats(move.map(x=>x.ack))};
  results.push({width,errors,incomplete,measurements});fs.writeFileSync(`${out}/actions-${label}.json`,JSON.stringify({method:'Warm-process loopback fixture. Fresh page list paint 5 samples; cached body paint 20; action ack 10; mocked send 5. Autosave includes debounce+SQL+ack; no actual provider or recipient delivery. Narrow hidden list clicks are programmatic for comparable timing.',results},null,2));
  console.log(label,width,'complete');await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
