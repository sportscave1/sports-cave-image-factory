// Focused real-browser interaction checks against the synthetic Workspace harness.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const base='http://127.0.0.1:8877';
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[],outside=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():(outside.push(r.request().url()),r.abort()));
  await page.goto(base);await page.evaluate(()=>loadFixture(12));
  const long=page.locator('.conversation').filter({hasText:'Long synthetic'});
  const other=page.locator('.conversation').filter({hasText:'Other conversation'});
  const key=await long.getAttribute('data-key'),otherKey=await other.getAttribute('data-key');
  await long.click();await page.locator('.email-document').waitFor();
  await page.waitForFunction(()=>!currentModel.history_pending);
  await page.evaluate(()=>{window.firstFrame=document.querySelector('.email-document');window.firstDoc=firstFrame.contentDocument;});
  await page.request.get(base+'/fail');
  await page.route('**/event',async r=>{await new Promise(resolve=>setTimeout(resolve,300));await r.continue();});
  await page.locator('.message-head').nth(1).click();
  await page.locator('.message-loading').waitFor();
  await page.getByRole('button',{name:'Retry',exact:true}).waitFor();
  assert.equal(await page.locator('.email-document').count(),1);
  await page.getByRole('button',{name:'Retry',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.email-document').length===2);
  assert.equal(await page.evaluate(()=>firstFrame.isConnected&&firstFrame.contentDocument===firstDoc),true,'Expansion must retain an unchanged email document');
  assert.equal(await page.locator('.message-error').count(),0);
  const trace=await (await page.request.get(base+'/trace')).json();
  assert.deepEqual(trace.calls.filter(c=>c[0]==='body').map(c=>c[1]),['1','2','2']);
  assert.equal(trace.calls.filter(c=>c[0]==='attachment').length,0);
  const replyKey=await page.locator('.message-head').nth(1).getAttribute('data-key');
  await page.locator('.reading-toolbar [data-action="compose"][data-mode="reply"]').click();
  await page.locator('#editor').waitFor();
  assert.equal(await page.evaluate(()=>currentModel.active_message),replyKey,'Reply must retain the selected historical source');
  await page.getByRole('button',{name:'Close · Esc',exact:true}).click();
  await page.locator('.reading-toolbar').waitFor();
  assert.equal(await page.locator('.message.active .message-head').getAttribute('data-key'),replyKey);
  assert.equal(await page.locator('.message.active .email-document').count(),1);
  // Queue multiple selections while the first server response is delayed.
  await other.click();await long.click();await other.click();
  await page.waitForFunction(k=>currentModel.selected===k,otherKey);
  await page.waitForTimeout(900);
  assert.equal(await page.locator('.conversation.selected').getAttribute('data-key'),otherKey);
  assert.equal(await page.locator('.subject-header h2').textContent(),'Other conversation');
  await long.click();await page.waitForFunction(k=>currentModel.selected===k,key);
  await page.waitForTimeout(400);
  assert.equal(await page.locator('.email-document').count(),1);
  assert.equal(await page.locator('.message-head[aria-expanded="false"]').count(),11);
  assert.equal(await page.locator('.message-head[aria-expanded="true"]').count(),1);
  assert.equal(await page.locator('.message-head[disabled]').count(),0,'Cached reopening must re-enable retained message controls');
  assert.equal(await page.getByRole('button',{name:'Collapse message',exact:true}).isEnabled(),true);
  fs.mkdirSync('docs/email-lazy-evidence',{recursive:true});
  await page.evaluate(()=>{document.querySelector('.reading-scroll').scrollTop=0;});
  await page.screenshot({path:'docs/email-lazy-evidence/reader.png'});
  const checks={reply_source_preserved:true,loading:true,inline_retry:true,unchanged_iframe_retained:true,rapid_switch_latest_wins:true,collapsed_reopen:true,remote_requests:outside,errors};
  assert.deepEqual(errors,[]);assert.deepEqual(outside,[]);
  fs.writeFileSync('docs/email-lazy-evidence/interactions.json',JSON.stringify(checks,null,2));
  console.log(JSON.stringify(checks));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
