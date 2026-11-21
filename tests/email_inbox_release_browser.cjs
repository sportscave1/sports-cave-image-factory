// Real component DOM, synthetic model only. No app server, credentials or network.
// EMAIL_BROWSER_MODEL points to a WorkspaceTests model generated offline.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');

(async()=>{
  const model=JSON.parse(fs.readFileSync(process.env.EMAIL_BROWSER_MODEL,'utf8'));
  Object.assign(model,{history_pending:false,discovery_pending:false,live_pending:false,
    sync_health:{state:'CONNECTED',category:'',diagnosis:''}});
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    const page=await browser.newPage({viewport:{width:1440,height:900}});
    const errors=[],requests=[];
    page.on('pageerror',e=>errors.push(e.message));
    await page.route('**/*',route=>{
      if(route.request().url()==='https://inbox-fixture.test/')return route.fulfill({
        contentType:'text/html',body:'<div id="mail"></div>'});
      requests.push(route.request().url());return route.abort();
    });
    await page.goto('https://inbox-fixture.test/');
    await page.addStyleTag({content:fs.readFileSync('components/support_email/style.css','utf8')});
    await page.addScriptTag({content:fs.readFileSync('components/support_email/mail.js','utf8')
      .replace(/\}\)\(\);\s*$/, 'window.inboxTest={render};})();')});
    await page.evaluate(m=>{
      window.fixture=m;window.actions=[];
      addEventListener('message',event=>{
        if(event.data.type!=='streamlit:setComponentValue')return;
        const value=event.data.value;actions.push(value.action);
        if(value.action==='retry_connection')inboxTest.render({...fixture,ack:value.id});
      });
      inboxTest.render(m);
    },model);
    await page.locator('.conversation').first().waitFor();
    await page.locator('.message-body,.email-document').first().waitFor();
    const rows=await page.locator('.conversation').count();
    const selected=await page.locator('.conversation.selected').getAttribute('data-key');
    const samples=await page.evaluate(()=>{
      const times=[];
      for(let i=0;i<50;i++){const t=performance.now();inboxTest.render(fixture);times.push(performance.now()-t);}
      return times.sort((a,b)=>a-b);
    });
    await page.evaluate(()=>inboxTest.render({...fixture,
      sync_health:{state:'RECONNECTING',category:'timeout',failure_stage:'tcp',
        diagnosis:'Mailbox connection fails before authentication; check provider/network access.'},
      recovery:{state:'stopped',message:'Mailbox connection unavailable.',delay_ms:0}}));
    await page.locator('.statusbar').filter({hasText:'Mailbox connection needs attention'}).waitFor();
    assert.equal(await page.locator('.conversation').count(),rows);
    assert.equal(await page.locator('.conversation.selected').getAttribute('data-key'),selected);
    assert.ok(await page.locator('.message-body,.email-document').count()>0);
    await page.locator('.connection-retry').click();
    await page.locator('.statusbar').filter({hasText:'Connected'}).waitFor();
    assert.deepEqual(await page.evaluate(()=>actions),['retry_connection']);
    for(const width of [390,1440,1920]){
      await page.setViewportSize({width,height:900});
      assert.equal(await page.locator('.conversation').count(),rows);
      assert.ok(await page.locator('.reading-toolbar').isVisible()||width===390);
    }
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
    console.log(JSON.stringify({method:'50 warm real-component DOM renders; synthetic mail; no app server',
      warm_render_median_ms:samples[25],warm_render_p95_ms:samples[47],rows,
      cached_body_survived_outage:true,retry_restored_connected:true,viewports:[390,1440,1920],
      external_requests:requests.length,runtime_errors:errors},null,2));
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
