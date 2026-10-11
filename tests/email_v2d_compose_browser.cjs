const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto'),assert=require('node:assert/strict');
const stats=a=>{a.sort((a,b)=>a-b);return {n:a.length,p50_ms:a[Math.floor(a.length/2)],p95_ms:a[Math.ceil(a.length*.95)-1]}};
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{for(const width of [1440,768,390])for(const label of ['before','after']){
  const page=await browser.newPage({viewport:{width,height:900}});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());page.on('dialog',d=>d.accept());
  await page.goto(`http://127.0.0.1:${label==='before'?8555:8554}/?actor=${crypto.randomUUID()}&delay=0`);
  await page.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation').first().waitFor();
  const f=page.frames().find(f=>f.url().includes('/component/')),samples=[];
  for(let i=0;i<11;i++){
   const elapsed=await f.evaluate(()=>new Promise((resolve,reject)=>{
    const start=performance.now();let done=false;
    const observer=new MutationObserver(check),timer=setTimeout(()=>{observer.disconnect();reject(new Error('Durable editor readiness timed out'));},20000);
    function check(){if(done||!document.querySelector('#editor')?.isContentEditable)return;done=true;observer.disconnect();clearTimeout(timer);requestAnimationFrame(()=>resolve(performance.now()-start));}
    observer.observe(document.body,{childList:true,subtree:true,attributes:true});
    document.querySelector('[data-action="compose"][data-mode="new"]').click();check();
   }));
   assert.equal(await f.locator('#editor').evaluate(node=>node.isContentEditable),true);
   if(i)samples.push(elapsed);
   await f.locator('[data-action="close_composer"]').evaluate(button=>button.click());
   await f.locator('#editor').waitFor({state:'detached'});
  }
  results.push({width,label,new_editor_ready:stats(samples)});await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync('docs/email-inbox-outlook-v2d-evidence/new-compose.json',JSON.stringify(results,null,2));console.log(results);
})().catch(e=>{console.error(e);process.exitCode=1});
