// Real Edge + repository HTML. Synthetic HTTP only; no live accounts/providers.
const {chromium}=require('playwright'),fs=require('node:fs'),http=require('node:http'),assert=require('node:assert/strict');
const pid='gid://shopify/Product/987',hash='a'.repeat(64);
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});let server;
 try{
  const gallery=fs.readFileSync('output/technical-flow/preview.html','utf8'),status=fs.readFileSync('components/auto_editions/status.html','utf8');
  // The JPEG is generated locally from real RGB/ICC bytes by the fixture command.
  const jpeg=fs.readFileSync('output/technical-flow/ui-thumbnail.jpg');
  let state='Uploading',approvals=0,polls=0,active=0,peak=0,images=0;
  server=http.createServer(async(req,res)=>{
   const u=new URL(req.url,'http://localhost');let body='';for await(const b of req)body+=b;
   if(u.pathname==='/auto-editions/bulk'){res.setHeader('content-type','text/html');res.end(gallery);return;}
   if(u.pathname==='/auto-editions/status'){res.setHeader('content-type','text/html');res.end(status);return;}
   res.setHeader('content-type','application/json');
   if(u.pathname==='/api/auto-editions/status'){
    active++;peak=Math.max(peak,active);polls++;
    await new Promise(r=>setTimeout(r,30));active--;
    res.end(JSON.stringify({rows:[{product_gid:pid,preparation_hash:hash,status:state,reason:state==='Uploading'?'Verifying retained package.':'Technical files verified. TEST downloads only.',checkpoint:'Verifying',actions:['preview']}]}));return;
   }
   if(u.pathname.endsWith('/list')){res.end(JSON.stringify({rows:[{product_gid:pid,hash,title:'Synthetic prepared artwork',status:state,reason:'Technical verification pending',eligible:false}],next_cursor:null,scanned:1,total_remaining:1}));return;}
   if(u.pathname.endsWith('/previews')){images++;res.end(JSON.stringify({rows:[{product_gid:pid,hash,jpeg:jpeg.toString('base64')}]}));return;}
   if(u.pathname.endsWith('/image')){images++;res.setHeader('content-type','image/jpeg');res.end(jpeg);return;}
   if(u.pathname.endsWith('/approve'))approvals++;
   res.statusCode=404;res.end('{}');
  });await new Promise(r=>server.listen(0,'127.0.0.1',r));const base='http://127.0.0.1:'+server.address().port;
  const measurements=[];
  for(const width of [1440,390]){
   state='Uploading';const context=await browser.newContext({viewport:{width,height:900}}),page=await context.newPage(),errors=[];
   page.on('pageerror',e=>errors.push(e.message));const start=performance.now();
   await page.goto(base+'/auto-editions/bulk?product_gid='+encodeURIComponent(pid));
   await page.locator('figure img').waitFor();await page.waitForFunction(()=>document.querySelector('figure img')?.naturalWidth>0);
   const firstImageMs=performance.now()-start;
   assert.equal(await page.locator('#approve').isVisible(),false);assert.equal(await page.locator('#select').isVisible(),false);
   assert.equal(await page.locator('input[type=checkbox]:visible').count(),0);
   await page.locator('figure img').click();await page.locator('#large[open]').waitFor();await page.locator('#close-large').click();
   await page.goto(base+'/auto-editions/status?product_gid='+encodeURIComponent(pid));
   await page.waitForFunction(()=>document.querySelector('#stage').textContent==='Uploading');
   assert.equal(await page.locator('#stage').evaluate(el=>getComputedStyle(el,'::before').animationName),'spin');
   state='Cloud Ready';await page.waitForFunction(()=>document.querySelector('#stage').textContent.includes('Cloud Ready'),{timeout:9000});
   assert.equal(await page.locator('#actions button:visible').allTextContents().then(v=>v.join(',')),'Preview artwork');
   await page.screenshot({path:`output/technical-flow/status-${width}.png`,fullPage:true});
   assert.deepEqual(errors,[]);measurements.push({width,firstImageMs:Math.round(firstImageMs),jpegBytes:jpeg.length});await context.close();
  }
  assert.equal(approvals,0);assert.equal(peak,1);
  console.log(JSON.stringify({measurements,statusRequests:polls,previewRequests:images,approvalRequests:approvals,maxOverlappingStatusRequests:peak}));
 }finally{await browser.close();if(server)await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});
