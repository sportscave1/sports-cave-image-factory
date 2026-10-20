// Previous released frontend + new synthetic Workspace: no legacy request loop.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),events=[],errors=[];
  const previous=execFileSync('git',['show','b9754240:components/support_email/mail.js'],{encoding:'utf8'});
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await page.route('**/mail.js',r=>r.fulfill({body:previous,contentType:'text/javascript; charset=utf-8'}));
  page.on('request',r=>{if(r.url().endsWith('/event'))events.push(r.postDataJSON().action);});
  await page.goto('http://127.0.0.1:8877');await page.evaluate(()=>loadFixture(12));
  await page.locator('.conversation').filter({hasText:'Long synthetic'}).click();
  await page.waitForFunction(()=>currentModel.messages.length===12&&currentModel.messages.slice(1).every(m=>m.body_error));
  const count=events.length;await page.waitForTimeout(700);
  assert.equal(events.length,count,'Old scheduler must stop after compatibility response');
  assert.equal(events.filter(a=>a==='load_conversation_body').length,1);
  assert.equal(await page.locator('.email-document').count(),1);
  const trace=await (await page.request.get('http://127.0.0.1:8877/trace')).json();
  assert.equal(trace.calls.filter(c=>c[0]==='body').length,1);
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({legacy_frontend_stopped:true,compatibility_requests:1,body_reads:1,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
