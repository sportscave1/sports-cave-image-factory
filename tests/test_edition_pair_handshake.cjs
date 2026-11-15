const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{const ctx=await browser.newContext({acceptDownloads:true});let starts=0;const bytes=Buffer.from('synthetic fixture'),output={test_only:true,validated:true,edition:'002 / 100',job_id:'fixture',dimensions:[2835,2004],filename:'TEST-NOT-PRINT-READY.jpg',jpg_base64:bytes.toString('base64'),jpg_sha256:crypto.createHash('sha256').update(bytes).digest('hex')};
 await ctx.addInitScript(()=>{if(location.hostname==='127.0.0.1')localStorage.setItem('studio-approved-origin','https://edition-handshake.local.test');});
 await ctx.route('**/*',async route=>{const u=new URL(route.request().url());let file;
 if(u.hostname==='127.0.0.1'){
 if(u.pathname==='/pair')file='scripts/studio/ui/pair.html';if(u.pathname==='/pair.js')file='scripts/studio/ui/pair.js';if(u.pathname==='/pair.css')file='scripts/studio/ui/pair.css';
 if(u.pathname==='/api/device')return route.fulfill({json:{token:'synthetic-local-token'}});
 if(u.pathname==='/api/action'){const a=route.request().postDataJSON().action;if(a==='edition-test-start')starts++;return route.fulfill({json:a==='catalog'?{rows:[]}:a==='edition-test-start'?{job_id:'fixture'}:a==='edition-test-status'?{status:'Ready'}:output});}
 }else{
 if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<a id="open" href="/edition-jpg-download#Download JPG">Download JPG</a><iframe src="/component"></iframe>'});
 if(u.pathname==='/component')file='components/psd_picker/index.html';
 if(u.pathname==='/edition-jpg-download'){await new Promise(r=>setTimeout(r,250));file='components/edition_test/index.html';}
 if(u.pathname==='/api/edition-jpg-test/prepare')return route.fulfill({json:{ok:true,grant:{base_url:u.origin,ticket:'synthetic',secret:'synthetic'}}});
 }
 if(file)return route.fulfill({contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html',body:fs.readFileSync(file,'utf8')});return route.abort();});
 const page=await ctx.newPage();await page.goto('https://edition-handshake.local.test');await page.waitForFunction(()=>!!window.SportsCavePsdPicker);
 const companion=page.waitForEvent('popup');const downloaded=page.waitForEvent('download',{timeout:15000});await page.locator('#open').click();const result=await downloaded;assert.equal(starts,1);assert.equal(result.suggestedFilename(),'TEST-NOT-PRINT-READY.jpg');await page.waitForTimeout(300);assert.equal((await companion).isClosed(),true);assert.equal(ctx.pages().filter(p=>!p.url().startsWith('edge://')).length,1);console.log('Actual pair.js saved-trust startup and prefixed nonce: one automatic job/download; no manual approval; companion closes.');
 }finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
