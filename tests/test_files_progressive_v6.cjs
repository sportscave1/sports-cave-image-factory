// Real Chromium rendering; all artwork and network responses are synthetic.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const sources={before:execFileSync('git',['show','c07119e4:components/files_image_viewer/index.html'],{encoding:'utf8'}),after:fs.readFileSync('components/files_image_viewer/index.html','utf8')};
  const maker=await browser.newPage();const assets={};
  for(const width of [256,1024,1600,2048]) assets[width]=await maker.evaluate(width=>{
   const c=document.createElement('canvas');c.width=width;c.height=width*3/4;
   const g=c.getContext('2d');g.fillStyle='#102334';g.fillRect(0,0,c.width,c.height);
   g.fillStyle='#eac36d';g.font=`${width/28}px serif`;
   for(let y=width/15;y<c.height;y+=width/12)g.fillText('SPORTS CAVE • Collector Edition 001 / 100',width/35,y);
   return c.toDataURL('image/jpeg',0.92).split(',')[1];
  },width);
  await maker.close();
  const samples={before:[],after:[]},pages={},logs={before:[],after:[]};
  for(const label of ['before','after']){
   const context=await browser.newContext({viewport:{width:900,height:700},deviceScaleFactor:1});
   const page=await context.newPage();pages[label]=page;
   await context.route('**/*',async route=>{
    const u=new URL(route.request().url());assert.equal(u.hostname,'v6.synthetic.test');
    if(u.pathname==='/viewer')return route.fulfill({contentType:'text/html',body:sources[label]});
    if(u.pathname==='/api/files-image-preview'){
     assert.equal(u.searchParams.get('representation'),'screen','ordinary viewing must not transfer Original');
     const tier=Number(u.searchParams.get('tier')||1024),path=u.searchParams.get('path');logs[label].push({tier,path,bytes:Buffer.from(assets[tier],'base64').length});
     await new Promise(r=>setTimeout(r,path==='slow.jpg'?700:180));
     return route.fulfill({contentType:'image/jpeg',body:Buffer.from(assets[tier],'base64')});
    }
    return route.fulfill({status:404,body:''});
   });
   await page.goto('http://v6.synthetic.test/viewer?embedded=1');
   await page.evaluate(data=>{window.quickURL=URL.createObjectURL(new Blob([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],{type:'image/jpeg'}));},assets[256]);
  }
  for(let i=0;i<12;i++)for(const label of i%2?['after','before']:['before','after']){
   samples[label].push(await pages[label].evaluate(async i=>{
    const start=performance.now();void loadImage(`art${i}.jpg`,{name:`art${i}.jpg`,revision:'r1'});showQuickPreview(quickURL);
    await new Promise(resolve=>{const tick=()=>state.naturalWidth===256?resolve():requestAnimationFrame(tick);tick();});
    const quick=performance.now()-start;
    await new Promise(resolve=>{const tick=()=>state.naturalWidth>=1024?resolve():requestAnimationFrame(tick);tick();});
    const sharp=performance.now()-start;const warmStart=performance.now();await loadImage(state.path,{name:state.name});
    return {quick,sharp,warm:performance.now()-warmStart};
   },i));
  }
  const page=pages.after;
  await page.evaluate(()=>{void loadImage('geometry.jpg',{name:'geometry.jpg',revision:'r1'});showQuickPreview(quickURL);});
  await page.waitForFunction(()=>state.naturalWidth===256);
  const before=await page.evaluate(()=>{state.sizingMode='custom';state.scale*=1.15;state.panX=42;state.panY=-19;state.rotation=90;applyTransform();return {width:state.naturalWidth*state.scale,panX:state.panX,panY:state.panY,rotation:state.rotation};});
  await page.waitForFunction(()=>state.previewTier===1024);
  const after=await page.evaluate(()=>({width:state.naturalWidth*state.scale,panX:state.panX,panY:state.panY,rotation:state.rotation}));
  assert.deepEqual(after,before,'upgrade preserves visible scale, pan and rotation');
  await page.evaluate(()=>zoomBy(3));await page.waitForFunction(()=>state.previewTier===2048);
  assert.equal(await page.evaluate(()=>state.panX),42);
  await page.screenshot({path:'test-results/files-v6-sharp.png'});
  await page.evaluate(()=>{void loadImage('slow.jpg',{name:'slow.jpg'});void loadImage('new.jpg',{name:'new.jpg',revision:'r2'});});
  await page.waitForFunction(()=>elements.image.alt==='new.jpg');await page.waitForTimeout(750);
  assert.equal(await page.locator('#image').getAttribute('alt'),'new.jpg');
  await page.evaluate(()=>{void loadImage('slow.jpg',{name:'slow.jpg'});closePreview();});await page.waitForTimeout(750);
  assert.equal(await page.evaluate(()=>state.naturalWidth),0);
  assert.equal(await page.locator('#stage').getAttribute('aria-busy'),'false');
  assert(!fs.readFileSync('components/files_window/index.html','utf8').includes('showToast(`Opening'));
  assert(!sources.after.includes('Opening preview'));assert(!sources.after.includes('Opening PDF'));
  // High-DPR mobile chooses a tier for its physical viewport, capped at provider detail.
  const dprContext=await browser.newContext({viewport:{width:390,height:700},deviceScaleFactor:3});
  const dprPage=await dprContext.newPage();await dprPage.route('**/*',route=>route.fulfill({contentType:'text/html',body:sources.after}));
  await dprPage.goto('http://v6.synthetic.test/viewer?embedded=1');
  const dprTier=await dprPage.evaluate(()=>desiredTier());assert.equal(dprTier,2048);
  const report={environment:'synthetic JPEG artwork; 180 ms fake image response; interleaved 12 per version',samples,summary:{},bytes:Object.fromEntries(Object.entries(assets).map(([k,v])=>[k,Buffer.from(v,'base64').length])),dprTier,geometryPreserved:true,originalTransfers:0};
  for(const label of ['before','after']){report.summary[label]={};for(const metric of ['quick','sharp','warm']){const sorted=samples[label].map(s=>s[metric]).sort((a,b)=>a-b);report.summary[label][metric]={p50:sorted[6],p95:sorted[11]};}}
  const client=await page.context().newCDPSession(page);await client.send('Performance.enable');
  report.browserMetrics=(await client.send('Performance.getMetrics')).metrics.filter(m=>['JSHeapUsedSize','Nodes'].includes(m.name));
  fs.writeFileSync('test-results/files-v6-progressive.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report.summary));
  console.log('Progressive geometry, silent navigation, DPR tiers, zoom detail, cancellation and no-original checks passed.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
