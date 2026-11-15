// Real component in Chromium; fabricated controller on loopback only.
const {chromium,request}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
(async()=>{
 const api=await request.newContext();
 const response=await api.get('http://127.0.0.1:8877/reset?count=1');
 assert.equal(response.status(),200);const model=await response.json();await api.dispose();
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());assert.equal(url.hostname,'127.0.0.1');
   if(url.pathname==='/host')return route.fulfill({contentType:'text/html',body:`<!doctype html><iframe title="Email" height="0" src="/component/index.html" sandbox="allow-scripts allow-same-origin"></iframe><script>
    window.readyCount=0;window.heightCount=0;window.model=${JSON.stringify(model).replace(/</g,'\\u003c')};
    setTimeout(()=>window.addEventListener('message',e=>{if(e.data.type==='streamlit:setFrameHeight'){heightCount++;document.querySelector('iframe').height=e.data.height;}if(e.data.type==='streamlit:componentReady'){
     readyCount++;e.source.postMessage({type:'streamlit:render',args:{model}},'*');
    }}),800);</script>`});
   const name=path.basename(url.pathname);assert.ok(['index.html','mail.js','mail_tools.js','draft_journal.js','style.css'].includes(name));
   return route.fulfill({path:path.join('components/support_email',name),contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  });
  await page.goto('http://127.0.0.1:8877/host');
  await page.frameLocator('iframe').locator('.workspace').waitFor({timeout:5000});
  const frameHeight=await page.locator('iframe').evaluate(frame=>frame.getBoundingClientRect().height);
  assert.ok(frameHeight>100,'host receives a usable component height after the delayed handshake');
  assert.equal(await page.evaluate(()=>readyCount),1);
  await page.waitForTimeout(1200);assert.equal(await page.evaluate(()=>readyCount),1);
  const heightMessages=await page.evaluate(()=>heightCount);
  await page.evaluate(()=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args:{model}},'*'));
  await page.waitForTimeout(100);
  assert.equal(await page.evaluate(()=>heightCount),heightMessages,'unchanged later renders retain height deduplication');
  assert.deepEqual(errors,[]);
  const result={delayed_host_listener_ms:800,initial_frame_height:0,rendered_frame_height:frameHeight,workspace_rendered:true,ready_messages_received:1,retries_stopped_after_ack:true,later_height_messages_deduplicated:true,page_errors:errors};
  fs.writeFileSync('docs/mailbox-reliability-evidence/component-handshake-browser.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
