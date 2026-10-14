const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
 const ctx=await browser.newContext({acceptDownloads:true});let starts=0,localRequests=0;
 await ctx.route('**/*',route=>{const u=new URL(route.request().url());
  if(u.hostname==='127.0.0.1'){localRequests++;return route.abort();}
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<a href="/auto-editions/download?allocation_id=42#Download JPG">Download JPG</a><iframe src="/component"></iframe>'});
  if(u.pathname.endsWith('/inline.js'))return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('components/psd_picker/inline.js','utf8')});
  if(u.pathname==='/component')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/psd_picker/index.html','utf8')});
  if(u.pathname==='/auto-editions/download')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/auto_editions/download.html','utf8')});
  if(u.pathname==='/api/auto-editions/start'){starts++;assert.equal(route.request().postData(),'{}');return route.fulfill({json:{job_id:'verified',status:'Queued'}});}
  if(u.pathname==='/api/auto-editions/state')return route.fulfill({json:{status:'Ready',job_id:'verified',filename:'edition-005-TEST.jpg'}});
  if(u.pathname==='/api/auto-editions/file')return route.fulfill({contentType:'image/jpeg',headers:{'Content-Disposition':'attachment; filename="edition-005-TEST.jpg"'},body:Buffer.from('synthetic fixture')});
  return route.abort();
 });
 const page=await ctx.newPage();await page.goto('https://cloud-edition.local.test');await page.waitForFunction(()=>!!window.SportsCavePsdPicker);
 await page.evaluate(()=>{const box=document.createElement('div');box.dataset.testid='stDataFrame';const canvas=document.createElement('canvas');box.append(canvas);document.body.append(box);canvas.getContext('2d').fillText('Generating',10,20);});
 assert(await page.getByRole('status').isVisible());assert.match(await page.getByRole('status').textContent(),/Generating/);
 await page.evaluate(()=>document.querySelector('canvas').getContext('2d').fillText('View',10,20));assert.equal(await page.getByRole('status').count(),0);
 const download=page.waitForEvent('download');await page.getByRole('link',{name:'Download JPG',exact:true}).click();
 assert.equal((await download).suggestedFilename(),'edition-005-TEST.jpg');assert.equal(starts,1);assert.equal(localRequests,0);assert.equal(ctx.pages().length,1);
 assert.equal(await page.getByRole('dialog').count(),0);
 await page.getByRole('link',{name:'View',exact:true}).waitFor();
 assert(await page.getByRole('link',{name:'Download',exact:true}).isVisible());
 const again=page.waitForEvent('download');await page.getByRole('link',{name:'Download',exact:true}).click();await again;assert.equal(starts,2);
 await page.reload();await page.waitForFunction(()=>!!window.SportsCavePsdPicker);
 await page.getByRole('link',{name:'Download JPG',exact:true}).click();await page.getByRole('link',{name:'View',exact:true}).waitFor();
 await page.getByRole('link',{name:'View',exact:true}).click();
 assert(await page.getByRole('dialog',{name:'Edition artwork'}).isVisible());
 assert.equal(starts,3);
 console.log('Cloud UI regression: one click, one job, automatic download plus View and fallback; no localhost, popup or companion.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
