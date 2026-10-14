const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const ctx=await browser.newContext({acceptDownloads:true});let starts=0,ready=false,missing=false;
 await ctx.route('**/*',async route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<a href="/auto-editions/'+(ready?'open?allocation_id=42&job_id=verified#Open':'download?allocation_id=42#Download JPG')+'">'+(ready?'Open':'Download JPG')+'</a><button id="other">Other row</button><iframe src="/component"></iframe>'});
  if(u.pathname.endsWith('/inline.js'))return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('components/psd_picker/inline.js','utf8')});
  if(u.pathname==='/component')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/psd_picker/index.html','utf8')});
  if(u.pathname==='/api/auto-editions/start'){starts++;assert.equal(route.request().postData(),'{}');await new Promise(r=>setTimeout(r,300));return route.fulfill({json:{job_id:'verified',status:'Queued'}});}
  if(u.pathname==='/api/auto-editions/state'){await new Promise(r=>setTimeout(r,300));ready=true;return route.fulfill({json:{status:'Ready',job_id:'verified',filename:'edition-005-TEST.jpg'}});}
  if(u.pathname==='/api/auto-editions/location')return route.fulfill({status:missing?409:200,json:missing?{error:'Saved JPG is unavailable'}:{ok:true,file_id:'id:exact'}});
  if(u.pathname==='/auto-editions/open')return route.fulfill({contentType:'text/html',body:'Saved file location'});
  if(u.pathname==='/api/auto-editions/file')return route.fulfill({contentType:'image/jpeg',headers:{'Content-Disposition':'attachment; filename="edition-005-TEST.jpg"'},body:Buffer.from('synthetic fixture')});
  return route.abort();
 });
 const page=await ctx.newPage();page.on('pageerror',e=>console.error('PAGE ERROR',e.message));await page.goto('https://cloud-edition.local.test');await page.waitForFunction(()=>!!window.SportsCavePsdPicker);
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download JPG',exact:true}).click();
 await page.getByRole('link',{name:/Generating/}).waitFor();
 await page.getByRole('button',{name:'Other row'}).click();
 await page.getByRole('link',{name:'Generating…',exact:true}).click();
 assert.equal((await download).suggestedFilename(),'edition-005-TEST.jpg');
 await page.getByRole('link',{name:'Open',exact:true}).waitFor();
 assert.equal(starts,1);assert.equal(await page.getByRole('dialog').count(),0);
 await ctx.pages()[1].waitForURL('**/auto-editions/open?allocation_id=42&job_id=verified');
 await page.getByRole('link',{name:'Open',exact:true}).click();assert.equal(starts,1);
 await page.reload();await page.waitForFunction(()=>!!window.SportsCavePsdPicker);
 await page.getByRole('link',{name:'Open',exact:true}).click();assert.equal(starts,1);
 missing=true;await page.getByRole('link',{name:'Open',exact:true}).click();await page.getByRole('link',{name:'Retry Open',exact:true}).waitFor();assert.equal(starts,1);
 const blocked=await browser.newContext({acceptDownloads:true});await blocked.addInitScript(()=>window.open=()=>null);
 await blocked.route('**/*',route=>route.fulfill({contentType:'text/html',body:'<a href="/auto-editions/open?allocation_id=42&job_id=verified#Open">Open</a>'}));
 // Popup denial must not throw or remove the saved Open action.
 const bp=await blocked.newPage();await bp.goto('https://cloud-edition.local.test');
 await bp.evaluate(code=>{const child=document.createElement('iframe');document.body.append(child);child.contentWindow.eval(code);},fs.readFileSync('components/psd_picker/inline.js','utf8'));
 await bp.evaluate(()=>{window.SportsCaveAutoEditions.connect(()=>{});window.SportsCaveAutoEditions.openSaved('/auto-editions/open?allocation_id=42&job_id=verified');});
 assert.equal(blocked.pages().length,1);await blocked.close();
 console.log('Inline generation, no modal, automatic location, repeated Open, refresh, missing archive and popup restrictions checked.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
