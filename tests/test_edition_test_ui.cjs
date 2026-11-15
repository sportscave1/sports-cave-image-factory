const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
for(const width of [1366,390])for(const fail of [false,true]){
 const ctx=await browser.newContext({viewport:{width,height:850},acceptDownloads:true}),page=await ctx.newPage();let loads=0,prepares=0,starts=0;
 const bytes=Buffer.from('synthetic test JPEG fixture'),sha=crypto.createHash('sha256').update(bytes).digest('hex');
 await ctx.route('**/*',route=>{const u=new URL(route.request().url());if(u.hostname==='127.0.0.1')return route.fulfill({contentType:'text/html',body:`<script>const nonce=location.hash.slice(1);addEventListener('message',e=>{const d=e.data;if(e.source!==opener||d.nonce!==nonce)return;const send=(type,extra={})=>opener.postMessage({studio:1,nonce,type,...extra},e.origin);if(d.type==='request')send('catalog');if(d.type==='edition-test')send('edition-result',${fail?"{error:'Session or permission rejected'}":`{result:{test_only:true,validated:true,edition:'002 / 100',job_id:'fixture',dimensions:[2835,2004]}}`});if(d.type==='edition-download')send('edition-download',{result:{test_only:true,validated:true,edition:'002 / 100',job_id:'fixture',filename:'TEST-NOT-PRINT-READY.jpg',jpg_base64:'${bytes.toString('base64')}',jpg_sha256:'${sha}'}});});</script>`});
 if(u.pathname==='/'){loads++;return route.fulfill({contentType:'text/html',body:'<a id="pilot" href="/edition-jpg-download#Download JPG">Download JPG</a><iframe src="/component"></iframe>'});}
 if(u.pathname==='/component')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/psd_picker/index.html','utf8')});
 if(u.pathname==='/edition-jpg-download')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/edition_test/index.html','utf8')});
 if(u.pathname==='/api/edition-jpg-test/prepare'){prepares++;return route.fulfill({json:{ok:true,grant:{base_url:u.origin,ticket:'synthetic',secret:'synthetic'}}});}
 return route.abort();});
 await page.goto('https://edition-oneclick.local.test/');await page.waitForFunction(()=>!!window.SportsCavePsdPicker);const downloads=[];page.on('download',d=>downloads.push(d));await page.locator('#pilot').click();const frame=page.frameLocator('dialog iframe');await frame.locator('#status').waitFor();
 assert.equal(await frame.locator('input').count(),0);assert.equal(await frame.locator('button').count(),0);
 if(fail){await frame.locator('#status').filter({hasText:'permission rejected'}).waitFor();assert.equal(downloads.length,0);}else{await frame.locator('#download').waitFor();for(let i=0;i<40&&!downloads.length;i++)await page.waitForTimeout(100);assert.equal(downloads.length,1);assert.equal(downloads[0].suggestedFilename(),'TEST-NOT-PRINT-READY.jpg');}
 assert.equal(prepares,1);assert.equal(await frame.locator('body').evaluate(e=>e.scrollWidth<=innerWidth),true);await frame.locator('#status').evaluate(e=>{e.tabIndex=0;e.focus()});await page.keyboard.press('Escape');await page.locator('dialog').waitFor({state:'detached'});assert.equal(loads,1);await ctx.close();
}
console.log('4 one-click desktop/mobile scenarios passed: automatic preparation/download, no manual controls, denied-job blocking, Escape/focus and no reload.');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
