const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('fs'),crypto=require('crypto');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{for(const width of [1440,768,390]){
  const page=await browser.newPage({viewport:{width,height:900}}),errors=[];
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`http://127.0.0.1:8554/?actor=${crypto.randomUUID()}&count=500&heavy=1`);
  const iframe=page.frameLocator('iframe[title="support_email_page.support_email_desktop"]');
  await iframe.locator('.conversation').first().waitFor();
  const f=page.frames().find(f=>f.url().includes('/component/'));
  const start=performance.now();await f.locator('.conversation').first().evaluate(b=>b.click());
  await f.waitForFunction(()=>document.querySelector('.email-document')?.contentDocument?.body?.textContent.includes('Synthetic large paragraph'));
  const open=performance.now()-start;
  await f.waitForFunction(()=>document.querySelectorAll('article.message').length>=100,null,{timeout:15000});
  assert.equal(await f.locator('[data-action="download"]').count(),15);
  const images=await f.evaluate(()=>[...document.querySelector('.email-document').contentDocument.querySelectorAll('img')].map(img=>img.getAttribute('src')));
  assert.ok(images.every(src=>!src||src.startsWith('data:')));
  const frameIntervals=await f.evaluate(()=>new Promise(resolve=>{let previous=performance.now(),samples=[];const scroll=document.querySelector('.reading-scroll');function tick(now){samples.push(now-previous);previous=now;scroll.scrollTop+=60;if(samples.length<60)requestAnimationFrame(tick);else resolve(samples.slice(1));}requestAnimationFrame(tick);}));
  frameIntervals.sort((a,b)=>a-b);
  await page.screenshot({path:`docs/email-inbox-outlook-v2d-evidence/long-thread-${width}.png`});
  assert.deepEqual(errors,[]);
  results.push({width,synthetic_open_ms:open,thread_rows:await f.locator('article.message').count(),attachment_metadata:15,
    scroll_p50_ms:frameIntervals[29],scroll_p95_ms:frameIntervals[56],errors});
  await page.close();
 }}finally{await browser.close();}
 fs.writeFileSync('docs/email-inbox-outlook-v2d-evidence/heavy-browser.json',JSON.stringify(results,null,2));
 console.log(results);
})().catch(e=>{console.error(e);process.exitCode=1});
