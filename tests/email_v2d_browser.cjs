// Real Streamlit component + real loopback resource listener; no external traffic.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs'),crypto=require('crypto');
const out='docs/email-inbox-outlook-v2d-evidence',port=process.argv[2]||'8554',label=process.argv[3]||'after';
const stats=a=>{a.sort((a,b)=>a-b);return {n:a.length,p50_ms:+a[Math.floor(a.length/2)].toFixed(2),p95_ms:+a[Math.ceil(a.length*.95)-1].toFixed(2)}};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{for(const width of [1440,768,390]){
  const context=await browser.newContext({viewport:{width,height:900},ignoreHTTPSErrors:true});
  await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
  await context.addInitScript(()=>{window.__v2b={};window.addEventListener('message',e=>{
   if(e.data?.type==='streamlit:setComponentValue'){try{e.source.__v2b.pending=e.data.value.id;}catch(_){}}
   if(e.data?.type==='streamlit:render'){window.__v2b.model=e.data.args.model;}
  });});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.on('dialog',d=>d.accept());
  const hits=async()=>await(await fetch('http://127.0.0.1:8843/__hits')).json();
  const reset=async()=>fetch('http://127.0.0.1:8843/__reset',{method:'POST'});
  const list=[];for(let i=0;i<6;i++){let t=performance.now();await page.goto(`http://127.0.0.1:${port}/?actor=${crypto.randomUUID()}`);await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first().waitFor();if(i)list.push(performance.now()-t);}
  let f=page.frames().find(f=>f.url().includes('/component/'));
  async function act(selector){const t=performance.now();await f.locator(selector).first().evaluate(b=>b.click());await f.waitForFunction(()=>window.__v2b.model?.ack===window.__v2b.pending);return performance.now()-t;}
  const open=[],cached=[],navigation=[];
  await reset();
  for(let i=1;i<=10;i++){const t=performance.now();await act(`.conversation-wrap:nth-child(${i}) .conversation`);await f.locator('.email-document').first().waitFor();await f.waitForFunction(()=>document.querySelector('.email-document')?.contentDocument?.body?.textContent.includes('Private synthetic'));open.push(performance.now()-t);}
  const initialHits=await hits();if(label!=='before')assert.equal(initialHits.length,0,'Opening mail made an unapproved resource request');
  const first='.conversation-wrap:nth-child(1) .conversation',second='.conversation-wrap:nth-child(2) .conversation';
  for(const s of [first,second]){await act(s);await f.waitForFunction(()=>document.querySelector('.email-document')?.contentDocument?.body?.textContent.includes('Private synthetic'));}
  for(let i=0;i<20;i++){
   const paint=await f.evaluate(s=>new Promise(resolve=>{const t=performance.now();document.querySelector(s).click();requestAnimationFrame(()=>resolve({ms:performance.now()-t,body:!!document.querySelector('.email-document')}));}),i%2?first:second);
   await f.waitForFunction(()=>window.__v2b.model?.ack===window.__v2b.pending);cached.push(paint);
  }
  for(let i=0;i<5;i++){navigation.push(await act('[data-action="folder"][data-folder="Archive"]'));navigation.push(await act('[data-action="folder"][data-folder="INBOX"]'));}
  await act(first);await f.locator('.email-document').first().waitFor();
  let checks={};
  if(label!=='before'){
   assert.equal((await hits()).length,0,'Cached switching/navigation made an unapproved request');
   assert.equal(await f.evaluate(()=>{const doc=document.querySelector('.email-document').contentDocument;return [...doc.querySelectorAll('[data-sc-remote-src]')].every(img=>doc.defaultView.getComputedStyle(img).display==='none');}),true);
   await f.waitForFunction(()=>{const img=document.querySelector('.email-document')?.contentDocument?.querySelector('img[src^="data:"]');return img?.complete&&img.naturalWidth>0});
   await f.evaluate(()=>{window.oldPane=document.querySelector('.reading');window.oldFrame=document.querySelector('.email-document');});
   await act('[data-action="show_images"]');
   await f.waitForFunction(()=>document.querySelector('.image-permission')?.textContent.includes('Images shown'));
   assert.equal(await f.evaluate(()=>window.oldPane===document.querySelector('.reading')&&window.oldFrame===document.querySelector('.email-document')),true,'Approval rebuilt the reading pane or iframe');
   await f.waitForFunction(()=>[...document.querySelector('.email-document').contentDocument.querySelectorAll('img[src^="https:"]')].length===3);
   await page.waitForTimeout(350);
   const approved=await hits();assert.equal(approved.length,3);assert.ok(approved.every(h=>/^\/(image|pixel|responsive)\/\d+$/.test(h.path)));assert.equal(new Set(approved.map(h=>h.path.split('/').pop())).size,1);assert.ok(approved.every(h=>!h.referer));
   await reset();await act(second);await act(first);await page.waitForTimeout(250);assert.equal((await hits()).length,0,'Approval leaked through cached selection');
   assert.ok(await f.locator('[data-action="show_images"]').count());
   await act('[data-action="compose"][data-mode="reply"]');await page.waitForTimeout(150);assert.equal((await hits()).length,0,'Reply quote fetched images');await act('[data-action="close_composer"]');
   await act('[data-action="resume_composer"]');await page.waitForTimeout(150);assert.equal((await hits()).length,0,'Restored draft fetched images');await act('[data-action="close_composer"]');
   await act('[data-action="compose"][data-mode="forward"]');await page.waitForTimeout(150);assert.equal((await hits()).length,0,'Forward quote fetched images');await act('[data-action="close_composer"]');
   await page.reload();await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first().waitFor();f=page.frames().find(f=>f.url().includes('/component/'));await act(first);await page.waitForTimeout(250);assert.equal((await hits()).length,0,'Reload inherited permission');
   checks={unapproved_requests:0,approved_requests:approved,cid_loaded:true,pane_and_iframe_preserved:true,cached_consent_reset:true,reply_forward_restore_private:true,reload_private:true};
  }
  await page.screenshot({path:`${out}/${label}-${width}.png`});
  results.push({width,errors,checks,baseline_unapproved_requests:label==='before'?initialHits.length:undefined,measurements:{list_paint:stats(list),message_open:stats(open),cached_paint:stats(cached.map(x=>x.ms)),cached_body_present:cached.filter(x=>x.body).length,navigation_ack:stats(navigation)}});
  fs.writeFileSync(`${out}/browser-${label}.json`,JSON.stringify({method:'Identical synthetic HTML fixture; warm-process list paint n=5, ten message opens, 20 primed cached paints, ten folder navigations. HTTPS certificate exception only in test context. No production latency claims.',results},null,2));
  assert.equal(errors.length,0);console.log(label,width,'verified');await context.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
