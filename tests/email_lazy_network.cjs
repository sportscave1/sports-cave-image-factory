// Actual component + Workspace over loopback. No app startup or customer data.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const label=process.argv[2]||'after',port=Number(process.argv[3]||8877);
const base=`http://127.0.0.1:${port}`;
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const results=[];
 try{
  for(const throttled of [false,true])for(const count of [1,12]){
   const page=await browser.newPage({viewport:{width:1440,height:900}}),requests=[],errors=[],outside=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():(outside.push(r.request().url()),r.abort()));
   page.on('response',async r=>{if(r.url().endsWith('/event'))requests.push({event:r.request().postDataJSON(),bytes:Number(r.headers()['content-length'])});});
   await page.goto(base);
   const cdp=await page.context().newCDPSession(page);
   if(throttled)await cdp.send('Network.emulateNetworkConditions',{offline:false,latency:150,downloadThroughput:125000,uploadThroughput:125000});
   await page.evaluate(n=>loadFixture(n),count);
   await page.locator('.conversation').first().waitFor();
   const key=await page.locator('.conversation').filter({hasText:'Long synthetic'}).first().getAttribute('data-key');
   const row=()=>page.locator(`.conversation[data-key="${key}"]`);
   const open=async warm=>{
    const start=requests.length,t=Date.now();await row().click();
    await page.locator('.email-document').first().waitFor();
    const first_ms=Date.now()-t;
    await page.waitForFunction(k=>currentModel.selected===k,key,{timeout:90000});
    const expected=label==='before'?count:1;
    await page.waitForFunction(n=>document.querySelectorAll('.email-document').length===n,expected,{timeout:90000});
    await page.waitForFunction(()=>!currentModel.history_pending&&!currentModel.body_pending,null,{timeout:90000});
    await page.waitForTimeout(350);
    const trace=await (await page.request.get(base+'/trace')).json();
    const heap=await cdp.send('Runtime.getHeapUsage');
    const events=requests.slice(start);
    const result={label,count,throttled,warm,first_ms,settled_ms:Date.now()-t,requests:events.length,response_bytes:events.reduce((n,r)=>n+r.bytes,0),body_reads:trace.calls.filter(c=>c[0]==='body').length,cache_bytes:trace.cache_bytes,iframes:await page.locator('.email-document').count(),heap_used:heap.usedSize};
    results.push(result);console.log(JSON.stringify(result));
    if(label==='after'){assert.equal(result.iframes,1);assert.equal(trace.calls.filter(c=>c[0]==='body').length,warm?2:1);}
   };
   await open(false);
   // A distinct conversation makes cached reopening observable.
   await page.locator('.conversation').filter({hasText:'Other conversation'}).click();
   await page.waitForFunction(()=>currentModel.messages[0]?.expanded&&currentModel.messages[0].subject==='Other conversation');
   await open(true);
   if(label==='after'&&count>1){
    const before=await (await page.request.get(base+'/trace')).json();
    await page.locator('.message-head').nth(1).click();
    await page.waitForFunction(()=>document.querySelectorAll('.email-document').length===2);
    const after=await (await page.request.get(base+'/trace')).json();
    assert.equal(after.calls.filter(c=>c[0]==='body').length,before.calls.filter(c=>c[0]==='body').length+1);
    const key2=await page.locator('.message-head').nth(1).getAttribute('data-key');
    await page.locator(`[data-action="collapse_message"][data-key="${key2}"]`).click();
    await page.waitForFunction(()=>document.querySelectorAll('.email-document').length===1);
    await page.locator('.message-head').nth(1).click();
    await page.waitForFunction(()=>document.querySelectorAll('.email-document').length===2);
    const cached=await (await page.request.get(base+'/trace')).json();
    assert.equal(cached.calls.filter(c=>c[0]==='body').length,after.calls.filter(c=>c[0]==='body').length);
   }
   assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
   await page.close();
  }
  fs.mkdirSync('docs/email-lazy-evidence',{recursive:true});
  fs.writeFileSync(`docs/email-lazy-evidence/${label}.json`,JSON.stringify(results,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
