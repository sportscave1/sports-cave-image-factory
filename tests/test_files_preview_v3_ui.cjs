// Actual viewer HTML, synthetic network only; preparation, reopen and cancellation.
const assert=require('node:assert/strict'), fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const context=await browser.newContext(); const page=await context.newPage();
  const errors=[], requests=[]; page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<canvas id="c" width="800" height="600"></canvas>');
  const image=Buffer.from(await page.evaluate(()=>{c.getContext('2d').fillRect(0,0,800,600);return c.toDataURL().split(',')[1];}),'base64');
  const counts={};
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());
   if(u.hostname!=='preview.synthetic.test')return route.abort();
   if(u.pathname==='/files-image-viewer')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/files_image_viewer/index.html','utf8')});
   if(u.pathname==='/api/files-image-preview'){
    assert.equal(u.searchParams.get('representation'),'screen');
    const path=u.searchParams.get('path');requests.push(path);counts[path]=(counts[path]||0)+1;
    if(path==='Changed.jpg')return route.fulfill({status:409,json:{message:'Changed'}});
    if(path==='Denied.jpg')return route.fulfill({status:403,json:{message:'Denied'}});
    if(path==='Waiting.jpg'||(path==='Artwork.jpg'&&counts[path]<3))return route.fulfill({status:202,json:{state:'preparing'},headers:{'Retry-After':'1'}});
    return route.fulfill({contentType:'image/png',body:image});
   }
   return route.fulfill({status:404,body:'No other network permitted'});
  });
  await page.goto('http://preview.synthetic.test/files-image-viewer?embedded=1&path=Artwork.jpg&name=Artwork.jpg&rev=r1');
  await page.waitForFunction(()=>elements.stage.getAttribute('aria-busy')==='true');
  assert(await page.locator('#closeButton').isEnabled());
  const ticks=await page.evaluate(async()=>{let n=0;for(let i=0;i<10;i++){await new Promise(requestAnimationFrame);n++;}return n;});assert.equal(ticks,10);
  await page.waitForFunction(()=>state.naturalWidth===800); assert.equal(counts['Artwork.jpg'],3);
  const warm=await page.evaluate(async()=>{const t=performance.now();await loadImage('Artwork.jpg',{name:'Artwork.jpg'});return performance.now()-t;});
  assert.equal(counts['Artwork.jpg'],3);
  await page.evaluate(()=>{void loadImage('Waiting.jpg',{name:'Waiting.jpg'});});
  await page.waitForFunction(()=>elements.stage.getAttribute('aria-busy')==='true');
  await page.evaluate(()=>loadImage('Next.webp',{name:'Next.webp'}));
  await page.waitForFunction(()=>elements.image.alt==='Next.webp');
  await page.waitForTimeout(1400);assert.equal(counts['Waiting.jpg'],1,'obsolete polling must stop');
  await page.evaluate(()=>loadImage('Changed.jpg',{name:'Changed.jpg'}));
  await page.waitForFunction(()=>elements.dimensions.textContent.includes('file changed')||elements.imageErrorDetail.textContent.includes('file changed'));
  await page.evaluate(()=>loadImage('Denied.jpg',{name:'Denied.jpg'}));
  await page.locator('#imageError.visible').waitFor();
  assert((await page.locator('#imageErrorDetail').textContent()).includes('expired'));
  assert.equal(context.pages().length,1);assert.deepEqual(errors,[]);
  const result={fixture:'synthetic preparation statuses; actual Chrome/viewer',warmReopenMs:warm,requests,animationFramesWhilePreparing:ticks};
  fs.writeFileSync('test-results/files-preview-v3-ui.json',JSON.stringify(result,null,2));
  console.log('V3 preparation, warm reuse, cancellation, revision and permission UI checks passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
