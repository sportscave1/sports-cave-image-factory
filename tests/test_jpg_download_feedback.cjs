// Isolated HTTP fixtures only: no credentials, provider access or real orders.
const {chromium}=require('playwright');
const http=require('node:http'),fs=require('node:fs'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const inline=fs.readFileSync('components/psd_picker/inline.js','utf8');
const standalone=fs.readFileSync('components/auto_editions/download.html','utf8');
const job='b'.repeat(64),filename='SC3287-005-TEST.jpg',chunk=Buffer.alloc(64*1024,73),chunks=32;
const expected=crypto.createHash('sha256');for(let i=0;i<chunks;i++)expected.update(chunk);
const expectedHash=expected.digest('hex');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 let mode='success',starts=0,files=0,completed=0,aborted=0,releaseFirstFile=false;
 const server=http.createServer(async(req,res)=>{
  const u=new URL(req.url,'http://localhost'),id=u.searchParams.get('allocation_id');
  const json=(value,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
  if(u.pathname==='/'){
   res.writeHead(200,{'Content-Type':'text/html'});
   return res.end(`<html><body><a href="/auto-editions/download?allocation_id=42#Download JPG">Download JPG</a><button onclick="this.textContent='Other control worked'">Other control</button><input aria-label="Search" value="kept"><script>window.opens=0;window.SportsCaveFilesWindow={open(){window.opens++}};window.beats=0;setInterval(()=>window.beats++,20);</script><script>${inline}</script></body></html>`);
  }
  if(u.pathname==='/auto-editions/download'){res.writeHead(200,{'Content-Type':'text/html'});return res.end(standalone);}
  if(u.pathname==='/api/auto-editions/start'){
   starts++;if(mode==='timeout'){req.on('close',()=>aborted++);return;}
   await delay(200);return json(mode==='prepareFail'?{error:'Preparation unavailable fixture'}:{job_id:job,status:'Queued'},mode==='prepareFail'?503:200);
  }
  if(u.pathname==='/api/auto-editions/state'){await delay(200);return json({job_id:job,status:'Ready',filename});}
  if(u.pathname==='/api/auto-editions/file'){
   files++;assert.equal(u.searchParams.get('job_id'),job);const token=u.searchParams.get('download_token');assert.match(token,/^[a-f0-9]{32}$/);
   if(mode==='handoffTimeout')return;
   await delay(350);
   // Hold headers until the test has observed the transfer stage, even when
   // another local SQL/browser suite temporarily delays automation commands.
   while(!releaseFirstFile&&!res.destroyed)await delay(20);
   res.setHeader('Set-Cookie',`sc-jpg-${token}=${mode==='transferFail'?'error':'started'}; Path=/; SameSite=Strict`);
   if(mode==='transferFail')return json({error:'Verified JPG temporarily unavailable fixture'},409);
   res.writeHead(200,{'Content-Type':'image/jpeg','Content-Disposition':`attachment; filename="${filename}"`,'Content-Length':chunk.length*chunks});
   for(let i=0;i<chunks;i++){if(res.destroyed)return;res.write(chunk);await delay(40);}
   completed++;res.end();return;
  }
  res.writeHead(404);res.end();
 });
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin=`http://127.0.0.1:${server.address().port}`;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const context=await browser.newContext({acceptDownloads:true});
  const page=await context.newPage();let fileFetches=0;
  page.on('request',r=>{if(r.url().includes('/api/auto-editions/file')&&r.resourceType()==='fetch')fileFetches++;});
  await page.goto(origin+'/?page=orders');
  await page.evaluate(()=>{document.addEventListener('pointerdown',()=>window.clickedAt=performance.now(),{once:true,capture:true});new MutationObserver(()=>{if(window.feedbackMs===undefined&&document.querySelector('#sc-jpg-progress-42'))window.feedbackMs=performance.now()-window.clickedAt;}).observe(document.body,{childList:true,subtree:true});});
  const downloading=page.waitForEvent('download');
  await page.getByRole('link',{name:'Download JPG',exact:true}).click();
  await page.getByRole('link',{name:'Preparing JPG…',exact:true}).waitFor();
  await page.getByRole('link',{name:'Preparing JPG…',exact:true}).dispatchEvent('click');
  await page.getByRole('button',{name:'Other control',exact:true}).click();
  await page.getByRole('link',{name:'Downloading…',exact:true}).waitFor();
  await page.getByRole('link',{name:'Downloading…',exact:true}).dispatchEvent('click');
  releaseFirstFile=true;
  const download=await downloading;
  await page.getByText('Download started',{exact:true}).waitFor();
  assert.equal(completed,0,'Handoff must restore UI before slow body completes');
  assert.equal(await page.getByRole('link',{name:'Open',exact:true}).getAttribute('aria-busy'),'false');
  assert.equal(await page.getByRole('textbox',{name:'Search'}).inputValue(),'kept');
  assert.equal(await page.getByRole('button',{name:'Other control worked'}).count(),1);
  assert.equal(await page.evaluate(()=>window.opens),1);
  assert.equal(starts,1);assert.equal(files,1);assert.equal(fileFetches,0);
  const feedbackMs=await page.evaluate(()=>window.feedbackMs);assert(feedbackMs<100);
  const beats=await page.evaluate(()=>window.beats);await delay(150);assert(await page.evaluate(()=>window.beats)>beats+3);
  fs.mkdirSync('output/jpg-feedback',{recursive:true});
  await page.screenshot({path:'output/jpg-feedback/handoff.png'});
  assert.equal(download.suggestedFilename(),filename);
  const path=await download.path();assert.equal(await download.failure(),null);
  assert.equal(fs.statSync(path).size,chunk.length*chunks);
  assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path)).digest('hex'),expectedHash);
  console.log(JSON.stringify({fixture:'synthetic local HTTP, 2MiB throttled native attachment',feedbackMs,bytes:chunk.length*chunks,hash:expectedHash,starts,files,JSFileFetches:fileFetches}));
  // Preparation failure retries the duplicate-safe start, not regeneration/retry.
  mode='prepareFail';await page.goto(origin+'/?page=orders');
  await page.getByRole('link',{name:'Download JPG',exact:true}).click();
  await page.getByRole('alert').getByText('Preparation unavailable fixture').waitFor();
  mode='transferFail';await page.getByRole('alert').getByRole('button',{name:'Retry',exact:true}).click();
  await page.getByRole('button',{name:'Retry download',exact:true}).waitFor();
  const startsBefore=starts,filesBefore=files;mode='success';
  const retried=page.waitForEvent('download');await page.getByRole('button',{name:'Retry download',exact:true}).click();
  const retryDownload=await retried;await page.getByText('Download started',{exact:true}).waitFor();await retryDownload.path();
  assert.equal(starts,startsBefore,'Transfer retry must reuse exact ready job');assert.equal(files,filesBefore+1);
  assert.equal(await page.locator('#sc-edition-error').count(),0);
  // Deadline and navigation: no late automatic download or stuck busy state.
  mode='timeout';await page.goto(origin+'/?page=orders');await page.clock.install();
  await page.getByRole('link',{name:'Download JPG',exact:true}).click();
  await page.clock.fastForward(21000);await page.getByRole('alert').filter({hasText:'timed out'}).waitFor();
  assert.equal(await page.getByRole('link',{name:'Retry',exact:true}).getAttribute('aria-busy'),'false');
  await page.clock.resume();
  // Native delivery without response headers has a separate bounded deadline.
  mode='handoffTimeout';await page.goto(origin+'/?page=orders');const beforeTimeout=files;
  await page.getByRole('link',{name:'Download JPG',exact:true}).click();
  while(files===beforeTimeout)await delay(20);
  await page.clock.fastForward(121000);
  await page.getByRole('alert').filter({hasText:'did not start in time'}).waitFor();
  assert.equal(await page.locator('iframe[title="JPG download delivery"]').count(),0);
  assert.equal(await page.getByRole('link',{name:'Retry',exact:true}).getAttribute('aria-busy'),'false');
  await page.clock.resume();
  mode='success';await page.goto(origin+'/?page=orders');const priorFiles=files;
  await page.getByRole('link',{name:'Download JPG',exact:true}).click();
  await page.evaluate(()=>{history.pushState({},'', '?page=other');document.querySelector('a').remove();});
  await delay(1100);assert.equal(files,priorFiles);assert.equal(await page.locator('#sc-jpg-progress-42').count(),0);
  // Standalone fallback uses same observable stages; Retry does not reload/start again.
  mode='transferFail';await page.goto(origin+'/auto-editions/download?allocation_id=42');
  await page.locator('#retry').waitFor();const fallbackStarts=starts;mode='success';
  const fallback=page.waitForEvent('download');await page.locator('#retry').click();await page.locator('#retry').evaluate(e=>e.click());
  const fallbackDownload=await fallback;await page.locator('#state').filter({hasText:'Download started'}).waitFor();await fallbackDownload.path();
  assert.equal(starts,fallbackStarts);assert.equal(await page.locator('#state').getAttribute('class'),'');
  await context.close();
  console.log('PASS: immediate feedback, staged handoff before body completion, exact bytes/name, duplicates, responsive controls, preparation/transfer Retry, request timeout, navigation and standalone fallback.');
 }finally{releaseFirstFile=true;await browser.close();server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{console.error(e);process.exitCode=1;});
