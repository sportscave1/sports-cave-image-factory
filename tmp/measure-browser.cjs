const {chromium}=require('playwright'),fs=require('node:fs'),{execFileSync}=require('node:child_process');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
for(const version of ['before','after']){
 const html=version==='before'?execFileSync('git',['show','HEAD:components/psd_open/index.html'],{encoding:'utf8'}):fs.readFileSync('components/psd_open/index.html','utf8').replace('__OWNER_DESKTOP_ALLOWED__','false');
 const page=await browser.newPage();let grants=0;
 await page.addInitScript(()=>{let listener;window.sent=[];window.created=[];window.revoked=[];const create=URL.createObjectURL.bind(URL),revoke=URL.revokeObjectURL.bind(URL);URL.createObjectURL=b=>{const u=create(b);created.push(u);return u};URL.revokeObjectURL=u=>{revoked.push(u);revoke(u)};window.chrome=window.chrome||{};window.chrome.webview={addEventListener(n,fn){listener=fn},removeEventListener(){},postMessage(m){sent.push(m.action);if(m.action==='hello')queueMicrotask(()=>listener({data:{type:'sports-cave-desktop',request_id:m.request_id,action:'capabilities',ok:true,capabilities:['openPhotoshop']}}));}};});
 await page.route('**/*',r=>{if(r.request().method()==='GET')return r.fulfill({contentType:'text/html',body:html});if(r.request().postDataJSON().action==='preview')return r.fulfill({contentType:'image/jpeg',body:Buffer.from([255,216,255,217])});grants++;return r.fulfill({json:{name:'Synthetic.psd',ticket:'test',secret:'test'}})});
 await page.goto('http://fixture.test/api/files-psd-open?product_gid=synthetic');await page.waitForTimeout(250);
 const idle=await page.evaluate(()=>sent.length);await page.locator('#artwork').click();await page.waitForFunction(()=>created.length===1);await page.evaluate(()=>SportsCavePsdDismiss());
 console.log(JSON.stringify({version,unsolicited_grant_requests:grants,idle_desktop_messages:idle,retained_preview_urls:await page.evaluate(()=>created.length-revoked.length)}));await page.close();
}
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
