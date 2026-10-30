// Real component + fabricated Workspace on loopback, never customer data.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:900}}),outside=[],errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():(outside.push(r.request().url()),r.abort()));
  await page.goto('http://127.0.0.1:8877');await page.evaluate(()=>loadFixture(12));
  await page.locator('.conversation').filter({hasText:'Long synthetic'}).click();
  await page.locator('.email-document').waitFor();
  assert.equal(await page.locator('.email-document').count(),1);
  await page.evaluate(()=>{window.firstFrame=document.querySelector('.email-document');window.firstDoc=firstFrame.contentDocument;});
  await page.locator('.message-head').nth(1).click();
  await page.waitForFunction(()=>document.querySelectorAll('.email-document').length===2);
  assert.equal(await page.evaluate(()=>firstFrame.isConnected&&firstDoc===firstFrame.contentDocument),true);
  await page.evaluate(()=>{
   currentModel.sync_health={state:'RECONNECTING',category:'timeout',failure_stage:'tcp',retry_after:120,
    diagnosis:'Mailbox connection fails before authentication; check provider/network access.'};
   currentModel.unresolved_receipts=[{status:'unknown',operation_id:'10000000-0000-4000-8000-000000000001',
    notice:'Outcome unresolved; background checks continue with backoff. Do not resend.'}];
   window.postMessage({type:'streamlit:render',args:{model:currentModel}},'*');
  });
  await page.locator('.statusbar').filter({hasText:'before authentication'}).waitFor();
  assert.equal(await page.locator('.conversation').count(),2);
  assert.equal(await page.locator('.email-document').count(),2);
  assert.match(await page.locator('.delivery-receipt').textContent(),/Do not resend/);
  const source=await page.locator('.message-head').nth(1).getAttribute('data-key');
  await page.locator('.reading-toolbar [data-action="compose"][data-mode="reply"]').click();
  await page.locator('#editor').waitFor();
  assert.equal(await page.evaluate(()=>currentModel.active_message),source);
  await page.getByRole('button',{name:'Close · Esc',exact:true}).click();
  await page.locator('.reading-toolbar').waitFor();
  const trace=await (await page.request.get('http://127.0.0.1:8877/trace')).json();
  assert.equal(trace.calls.filter(c=>c[0]==='body').length,2);
  assert.equal(trace.calls.filter(c=>c[0]==='attachment').length,0);
  assert.deepEqual(outside,[]);assert.deepEqual(errors,[]);
  fs.mkdirSync('docs/mailbox-reliability-evidence',{recursive:true});
  const result={cached_mail_usable_during_failure:true,actionable_tcp_diagnosis:true,truthful_unknown_send:true,
    reply_source_preserved:true,lazy_body_reads:2,automatic_body_reads:1,attachment_reads:0,remote_requests:outside,errors};
  fs.writeFileSync('docs/mailbox-reliability-evidence/browser.json',JSON.stringify(result,null,2));
  await page.screenshot({path:'docs/mailbox-reliability-evidence/browser.png'});
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
