// Synthetic 5,000-header mailbox; actual component/event/SQL/browser paths.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs'),crypto=require('crypto');
const out='docs/email-inbox-outlook-v2d-evidence';
const stats=a=>{a=[...a].sort((a,b)=>a-b);return {n:a.length,p50_ms:a[Math.floor(a.length/2)],p95_ms:a[Math.ceil(a.length*.95)-1]};};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{for(const width of [1440,768,390]){
  const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[],ready=[];
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  page.on('pageerror',e=>errors.push(e.message));
  page.on('response',r=>{if(r.url().includes('/api/os/email/read-ready'))ready.push(r.status());});
  await context.addInitScript(()=>{window.__perf={};window.addEventListener('message',e=>{
   if(e.data?.type==='streamlit:setComponentValue'){try{e.source.__perf.pending=e.data.value.id;}catch{}}
   if(e.data?.type==='streamlit:render')window.__perf.model=e.data.args.model;
  });});
  await page.goto(`http://127.0.0.1:8554/?actor=${crypto.randomUUID()}&count=5000&delay=.2`);
  const iframe=page.frameLocator('iframe[title="support_email_page.support_email_desktop"]');
  await iframe.locator('.conversation').first().waitFor();
  const f=page.frames().find(f=>f.url().includes('/component/'));
  await f.waitForFunction(()=>!window.__perf.model.discovery_pending);
  assert.equal(await f.locator('.conversation-wrap').count(),50);
  async function act(selector){await f.locator(selector).first().evaluate(b=>b.click());await f.waitForFunction(()=>window.__perf.model.ack===window.__perf.pending);}
  const opened=[];
  for(let i=1;i<=10;i++){
   const t=performance.now();await act(`.conversation-wrap:nth-child(${i}) .conversation`);
   await f.waitForFunction(()=>document.querySelector('.email-document')?.contentDocument?.body?.textContent.includes('Private synthetic'));
   opened.push(performance.now()-t);
  }
  assert.ok(ready.some(s=>s===200),'The completion endpoint was not exercised');
  // Supersede a pending body with another selected conversation.
  await act('.conversation-wrap:nth-child(11) .conversation');
  await act('.conversation-wrap:nth-child(12) .conversation');
  await f.waitForFunction(()=>document.querySelector('.email-document')?.contentDocument?.body?.textContent.includes('Private synthetic'));
  const identity=await f.evaluate(()=>({active:window.__perf.model.active_message,rows:window.__perf.model.messages.filter(m=>m.expanded).map(m=>m.key)}));
  assert.ok(identity.rows.includes(identity.active));
  const folderPaint=[],searchPaint=[],scroll=[];
  for(let i=0;i<5;i++){
   await act('[data-action="folder"][data-folder="Archive"]');
   const sample=await f.evaluate(()=>new Promise(resolve=>{const t=performance.now();document.querySelector('[data-action="folder"][data-folder="INBOX"]').click();requestAnimationFrame(()=>resolve({ms:performance.now()-t,rows:document.querySelectorAll('.conversation-wrap').length}));}));
   await f.waitForFunction(()=>window.__perf.model.ack===window.__perf.pending);
   folderPaint.push(sample);
  }
  console.log('Folder first-frame samples',width,JSON.stringify(folderPaint));
  assert.ok(folderPaint.every(s=>s.rows===50),'Cached folder lost its rows before the next frame');
  for(let i=0;i<10;i++)searchPaint.push(await f.evaluate(()=>new Promise(resolve=>{const t=performance.now(),input=document.querySelector('#search');input.value='subject: Delivery';input.dispatchEvent(new Event('input',{bubbles:true}));requestAnimationFrame(()=>resolve({ms:performance.now()-t,label:document.querySelector('.list-footer').textContent}));})));
  assert.ok(searchPaint.every(s=>s.label.includes('Cached matches only')));
  await f.waitForFunction(()=>window.__perf.model.query==='Delivery'&&window.__perf.model.field==='SUBJECT');
  await f.locator('#search').fill('');await f.locator('#search-form').evaluate(form=>form.requestSubmit());
  await f.waitForFunction(()=>!window.__perf.model.query&&window.__perf.model.ack===window.__perf.pending);
  await act('[data-action="load_more"]');
  await f.waitForFunction(()=>window.__perf.model.threads.length===100);
  assert.equal(new Set(await f.locator('.conversation').evaluateAll(nodes=>nodes.map(n=>n.dataset.key))).size,100);
  scroll.push(...await f.evaluate(()=>new Promise(resolve=>{const times=[],list=document.querySelector('.conversations');let previous=performance.now();function frame(now){times.push(now-previous);previous=now;list.scrollTop+=40;if(times.length<60)requestAnimationFrame(frame);else resolve(times.slice(1));}requestAnimationFrame(frame);})));
  assert.deepEqual(errors,[]);
  await page.screenshot({path:`${out}/large-mailbox-${width}.png`});
  results.push({width,body_delay_ms:200,initial_rows:50,loaded_rows:100,completion_http_statuses:ready,
    message_completion:stats(opened),folder_cached_paint:stats(folderPaint.map(s=>s.ms)),folder_rows_at_frame:folderPaint.map(s=>s.rows),
    search_cached_paint:stats(searchPaint.map(s=>s.ms)),scroll_frame_interval:stats(scroll),errors});
  fs.writeFileSync(`${out}/responsiveness.json`,JSON.stringify(results,null,2));
  console.log('Responsiveness verified',width);await context.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
