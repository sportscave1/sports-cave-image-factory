// Actual Streamlit component, synthetic mail, disposable SQL, loopback requests only.
const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto');
const port=process.argv[2]||'8553',label=process.argv[3]||'after',out='docs/email-inbox-outlook-v2a-evidence';
const stats=a=>{a=[...a].sort((a,b)=>a-b);return a.length?{n:a.length,p50_ms:+a[Math.floor(a.length/2)].toFixed(2),p95_ms:+a[Math.ceil(a.length*.95)-1].toFixed(2)}:{n:0}};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
 try{for(const width of [1440,390]){
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
   const immediate=await frame.evaluate(({s,action})=>new Promise(resolve=>{const b=document.querySelector(s),a=window.__v2a;a.ack=null;a.action=action||b.dataset.action;a.t=performance.now();b.click();requestAnimationFrame(()=>resolve({ms:performance.now()-a.t,body:!!document.querySelector('.message-body'),text:document.querySelector('#send-status')?.textContent}));}),{s:selector,action});
   await frame.waitForFunction(()=>window.__v2a.ack!==null,null,{timeout:20000});return {...immediate,ack:await frame.evaluate(()=>window.__v2a.ack)};
  }
  const first='.conversation-wrap:nth-child(1) .conversation',second='.conversation-wrap:nth-child(2) .conversation';
  await act(first);await frame.locator('.message-body').first().waitFor();
  await act(second);await frame.locator('.message-body').first().waitFor();
  const incomplete=[],cached=[],reply=[],save=[],restore=[],flags=[],sync=[],send=[],archive=[],move=[];
  for(let i=0;i<20;i++)cached.push(await act(i%2?first:second));
  results.push({width,errors,measurements:{cached_paint:stats(cached.map(x=>x.ms)),cached_ack:stats(cached.map(x=>x.ack)),cached_body_present:cached.filter(x=>x.body).length}});
  fs.writeFileSync(`${out}/cached-${label}.json`,JSON.stringify({method:'Both source bodies confirmed present before 20 alternating switches. Same loopback fixture and event acknowledgement as the full browser benchmark.',results},null,2));
  console.log(label,width,'cached complete');await page.close();
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
