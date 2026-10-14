const assert = require('node:assert/strict');
const fs = require('node:fs');
const {execFileSync} = require('node:child_process');
const {chromium} = require('playwright');
const root = '/Synthetic Files';
const baselineRef = process.env.FILES_BENCHMARK_BASELINE || '823a1966';
const source = fs.readFileSync('components/files_window/index.html','utf8');
const viewer = fs.readFileSync('components/files_image_viewer/index.html','utf8');
const baseline = execFileSync('git',['show',baselineRef+':components/files_window/index.html'],{encoding:'utf8',maxBuffer:2e6});
const oldViewer = execFileSync('git',['show',baselineRef+':components/files_image_viewer/index.html'],{encoding:'utf8',maxBuffer:2e6});
const delay = ms => new Promise(resolve=>setTimeout(resolve,ms));
const item = (i, folder=root, extension='psd') => ({id:'id:file'+i,path:`${folder}/Artwork ${i}.${extension}`,desktop_relative_path:`${folder.slice(root.length+1)}${folder===root?'':'/'}Artwork ${i}.${extension}`,name:`Artwork ${i}.${extension}`,tag:'file',kind:extension==='psd'?'photoshop':'image',extension,type:extension==='psd'?'Photoshop document':'Image',revision:'r1',size:35000000,size_label:'35 MB'});
const summary = values => {const sorted=[...values].sort((a,b)=>a-b);return {p50:+sorted[Math.floor(sorted.length/2)].toFixed(2),p95:+sorted[Math.ceil(sorted.length*.95)-1].toFixed(2),samples:values.map(x=>+x.toFixed(2))};};
let imageBytes;
async function fixture(browser, html=source, {count=2000,paginate=false,thumbnails=false,listingDelay=30,viewerHtml=viewer,launcherHtml=fs.readFileSync("components/files_window_launcher/index.html","utf8")}={}) {
 const context=await browser.newContext({viewport:{width:1280,height:800}});
 const log={lists:[],previews:[],downloads:0,thumbs:0,activeThumbs:0,maxThumbs:0,errors:[]};
 context.on('page',p=>p.on('pageerror',e=>log.errors.push(e.message)));
 await context.route('**/*',async route=>{
  const u=new URL(route.request().url());
  if(u.hostname!=='files.synthetic.test')return route.abort();
  if(u.pathname==='/files-window'||u.pathname==='/files-component')return route.fulfill({contentType:'text/html',body:html});
  if(u.pathname==='/launcher')return route.fulfill({contentType:'text/html',body:launcherHtml});
  if(u.pathname==='/files-image-viewer')return route.fulfill({contentType:'text/html',body:viewerHtml});
  if(u.pathname==='/api/files-list'){
   const path=u.searchParams.get('path')||(u.searchParams.get('relative_path')?root+'/'+u.searchParams.get('relative_path'):root);
   log.lists.push(path);
   await delay(path.endsWith('/Slow')?350:listingDelay);
   const end=paginate?Math.min(count,Number(u.searchParams.get('page')||0)+100):count;
   const items=Array.from({length:end},(_,i)=>item(i,path,thumbnails?'jpg':'psd'));
   if(thumbnails)items.forEach(i=>{i.thumbnail_url='/api/files-thumbnail?path='+encodeURIComponent(i.path);i.thumbnail_key=i.path+'|r1';});
   return route.fulfill({json:{ok:true,root_path:root,root_name:'Synthetic Files',current_path:path,cache_namespace:'synthetic-worker',cached_for_seconds:30,can_delete:true,items,has_more:end<count,next_page:end<count?String(end):'',complete:end===count}}).catch(()=>{});
  }
  if(u.pathname==='/api/files-image-items')return route.fulfill({json:{ok:true,images:[{path:'Artwork 0.jpg',name:'Artwork 0.jpg'}]}});
  if(u.pathname==='/api/files-image-preview'){
   const small=u.searchParams.has('representation');log.previews.push({small,path:u.searchParams.get('path')});
   await delay(u.searchParams.get('path').includes('Slow')?250:40);
   return route.fulfill({contentType:'image/jpeg',body:small?imageBytes.preview:imageBytes.original}).catch(()=>{});
  }
  if(u.pathname==='/api/files-thumbnail'){
   log.thumbs++;log.activeThumbs++;log.maxThumbs=Math.max(log.maxThumbs,log.activeThumbs);await delay(60);log.activeThumbs--;
   return route.fulfill({contentType:'image/jpeg',body:imageBytes.preview}).catch(()=>{});
  }
  if(u.pathname==='/api/auto-editions/location')return route.fulfill({json:{file_id:'id:file1999',revision:'r1',folder_path:root,filename:'Artwork 1999.jpg'}});
  if(u.pathname==='/api/files-resolve') {const selected=item(1999,root,'jpg');return route.fulfill({json:{ok:true,item:selected,items:[selected],root_path:root,current_path:root,cache_namespace:'synthetic-worker',can_delete:true}});}
  if(u.pathname==='/api/files-download'){log.downloads++;return route.fulfill({status:403,body:'Synthetic download initiation; no remote transfer'});}
  if(u.pathname==='/api/files-upload/start')return route.fulfill({json:{upload_id:'synthetic',upload_secret:'synthetic',offset:0}});
  if(u.pathname==='/api/files-upload/chunk')return route.fulfill({json:{state:'completed',offset:4}});
  if(u.pathname==='/api/files-folder'||u.pathname==='/api/files-rename'||u.pathname==='/api/files-delete')return route.fulfill({json:{ok:true,successful:[]}});
  if(u.pathname==='/orders')return route.fulfill({contentType:'text/html',body:'<main data-testid="stMain"><div data-testid="stMainBlockContainer"><input id="orderSearch" value="keep order filter"></div></main>'});
  return route.fulfill({status:404});
 });
 const page=await context.newPage();
 return {context,page,log};
}
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const report={kind:'Synthetic Chrome, isolated requests; no Dropbox or production access',baseline:baselineRef,render:{},preview:{}};
 try{
  const imagePage=await browser.newPage();
  imageBytes={};
  for(const [key,width,height] of [['preview',1024,768],['original',7000,5000]]){
   const encoded=await imagePage.evaluate(({width,height})=>{const c=document.createElement('canvas');c.width=width;c.height=height;const ctx=c.getContext('2d');const g=ctx.createLinearGradient(0,0,width,height);g.addColorStop(0,'#1b3960');g.addColorStop(1,'#dca749');ctx.fillStyle=g;ctx.fillRect(0,0,width,height);ctx.fillStyle='white';ctx.font='bold 100px sans-serif';ctx.fillText('SYNTHETIC ARTWORK',50,150);return c.toDataURL('image/jpeg',.9).split(',')[1];},{width,height});
   imageBytes[key]=Buffer.from(encoded,'base64');
  }
  imageBytes.original=Buffer.concat([imageBytes.original,Buffer.alloc(35*1024*1024-imageBytes.original.length)]);
  await imagePage.close();report.fixtureBytes={original:imageBytes.original.length,preview:imageBytes.preview.length};
  // Paired benchmark: identical source data, browser, viewport and fixed 30 ms mocked listing delay.
  for(const [label,html] of [['before',baseline],['after',source]])for(const count of [500,2000]){
   const samples=[];
   for(let run=0;run<6;run++){
    const {context,page,log}=await fixture(browser,html,{count});
    const cdp=await context.newCDPSession(page);await cdp.send('Performance.enable');
    const started=Date.now();await page.goto('http://files.synthetic.test/files-window');await page.waitForFunction(n=>state.items.length===n&&!state.loading,count);
    const cold=Date.now()-started;
    const sample=await page.evaluate(async()=>{
     let t=performance.now();renderItems();const rebuild=performance.now()-t;
     t=performance.now();document.querySelector('.file-item').click();const selection=performance.now()-t;
     t=performance.now();await loadFolder(state.currentPath);const warm=performance.now()-t;
     t=performance.now();await navigateTo(state.rootPath+'/Benchmark');const folder=performance.now()-t;
     t=performance.now();await navigateBack();const back=performance.now()-t;
     t=performance.now();await navigateForward();const forward=performance.now()-t;
     t=performance.now();elements.searchInput.value='Artwork 1999';elements.searchInput.dispatchEvent(new Event('input'));await new Promise(requestAnimationFrame);const search=performance.now()-t;
     elements.searchInput.value='';elements.searchInput.dispatchEvent(new Event('input'));await new Promise(requestAnimationFrame);
     return {rebuild,selection,warm,folder,back,forward,search,rows:document.querySelectorAll('.file-item').length,dom:document.querySelectorAll('*').length,shell:performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd};
    });
    const metrics=(await cdp.send('Performance.getMetrics')).metrics;
    sample.heap=metrics.find(m=>m.name==='JSHeapUsedSize').value;
    sample.scriptCpuMs=metrics.find(m=>m.name==='ScriptDuration').value*1000;
    samples.push({...sample,cold});assert.equal(log.lists.length,2);assert.deepEqual(log.errors,[]);await context.close();
   }
   report.render[label+count]=Object.fromEntries(['cold','shell','rebuild','selection','warm','folder','back','forward','search','heap','scriptCpuMs'].map(k=>[k,summary(samples.map(s=>s[k]))]));
   report.render[label+count].rows=samples[0].rows;report.render[label+count].dom=samples[0].dom;
  }
  report.launcher={};
  for (const [label,launcherHtml] of [['before',execFileSync('git',['show',baselineRef+':components/files_window_launcher/index.html'],{encoding:'utf8'})],['after',fs.readFileSync('components/files_window_launcher/index.html','utf8')]]) {
   const {context,page,log}=await fixture(browser,source,{count:500,launcherHtml});
   await page.goto('http://files.synthetic.test/launcher');
   await page.evaluate(()=>document.querySelector('#launcher').addEventListener('click',()=>{window.clickedAt=Date.now();},true));
   const [popup]=await Promise.all([page.waitForEvent('popup'),page.locator('#launcher').click()]);
   await popup.locator('#results').waitFor();const clickAt=await page.evaluate(()=>window.clickedAt);
   const shell=await popup.evaluate(()=>performance.timeOrigin+performance.getEntriesByType('navigation')[0].domContentLoadedEventEnd);
   await popup.waitForFunction(()=>state.items.length===500);const calls=log.lists.length;
   await page.locator('#launcher').click();await delay(150);
   report.launcher[label]={clickToShellMs:Math.round(shell-clickAt),warmReopenListingRequests:log.lists.length-calls};
   assert.equal(context.pages().length,2);if(label==='after')assert.equal(log.lists.length,calls);
   assert.deepEqual(log.errors,[]);await context.close();
  }
  // Measure the actual file double-click through close/reopen, including the old popup.
  report.openJourney={};
  for (const [label,html,viewerHtml] of [['before',baseline,oldViewer],['after',source,viewer]]) {
   const cold=[],warm=[];
   for(let run=0;run<4;run++) {
    const {context,page,log}=await fixture(browser,html,{count:500,thumbnails:true,viewerHtml});
    await page.goto('http://files.synthetic.test/files-window');await page.waitForFunction(()=>state.items.length===500);
    await page.evaluate(()=>document.querySelector('.file-item').addEventListener('dblclick',()=>window.openClickedAt=Date.now(),true));
    for(const samples of [cold,warm]) {
     let view;
     if(label==='before') { [view]=await Promise.all([page.waitForEvent('popup'),page.locator('.file-item').first().dblclick()]); }
     else { await page.locator('.file-item').first().dblclick();view=await page.locator('#previewFrame').elementHandle().then(el=>el.contentFrame()); }
     await view.waitForFunction(()=>state.naturalWidth>0);samples.push(Date.now()-await page.evaluate(()=>window.openClickedAt));
     if(label==='before') await view.close();
     else await view.locator('#closeButton').click();
     if(label==='after')await page.locator('#previewPanel').waitFor({state:'hidden'});
     else await delay(650); // Existing duplicate-open guard on the baseline.
    }
    assert.deepEqual(log.errors,[]);await context.close();
   }
   report.openJourney[label]={cold:summary(cold),warm:summary(warm)};
  }
  // Actual production viewer, synthetic 35 MiB JPEG vs generated representation.
  for(const [label,viewerHtml] of [['before',oldViewer],['after',viewer]]){
   const samples=[],warm=[];let transferCount=0;
   for(let run=0;run<4;run++){
    const {context,page,log}=await fixture(browser,source,{count:1,viewerHtml});
    const start=Date.now();await page.goto('http://files.synthetic.test/files-image-viewer?path=Artwork%200.jpg&name=Artwork%200.jpg');
    await page.waitForFunction(()=>state.naturalWidth>0);samples.push(Date.now()-start);
    warm.push(await page.evaluate(async()=>{const start=performance.now();loadImage(state.path,{name:state.name});await new Promise(resolve=>{const tick=()=>elements.dimensions.textContent.includes('pixels')?resolve():requestAnimationFrame(tick);tick();});return performance.now()-start;}));
    if(label==='after'){assert(log.previews.every(p=>p.small));assert.equal(log.previews.length,1);await page.locator('#actualButton').click();await page.waitForFunction(()=>elements.dimensions.textContent.startsWith('Original'));assert.equal(log.previews.filter(p=>!p.small).length,1);}
    transferCount+=log.previews.length;assert.deepEqual(log.errors,[]);await context.close();
   }
   report.preview[label]={cold:summary(samples),warm:summary(warm),requestsIncludingExplicitOriginal:transferCount};
  }
  {
   const {context,page,log}=await fixture(browser,source,{count:2000});
   await page.goto('http://files.synthetic.test/files-window');await page.waitForFunction(()=>state.items.length===2000);
   fs.mkdirSync('test-results',{recursive:true});
   await page.screenshot({path:'test-results/files-grid-desktop.png'});
   await page.setViewportSize({width:390,height:800});await delay(80);await page.screenshot({path:'test-results/files-grid-mobile.png'});
   assert(await page.locator('body').evaluate(e=>e.scrollWidth<=innerWidth));await page.setViewportSize({width:1280,height:800});await delay(80);
   const frames=await page.evaluate(async()=>{
     const deltas=[];let previous=performance.now();
     for(let i=0;i<60;i++){await new Promise(requestAnimationFrame);const now=performance.now();deltas.push(now-previous);previous=now;elements.results.scrollTop+=40;}
     return deltas.slice(1);
   });report.scrolling=summary(frames);
   for(const view of ['large','medium','small','list','details']){
    await page.evaluate(view=>setView(view),view);assert(await page.locator('.file-item').count()<220,view);
    await page.keyboard.press('End');assert.equal(await page.evaluate(()=>[...state.selection][0]),root+'/Artwork 1999.psd');
    assert.equal(await page.evaluate(()=>document.activeElement.dataset.path),root+'/Artwork 1999.psd');await page.keyboard.press('Home');
   }
   await page.locator('#searchInput').fill('Artwork 1999');await page.waitForFunction(()=>document.querySelectorAll('.file-item').length===1);assert.equal(log.lists.length,1);
   await page.locator('#searchInput').fill('');await page.waitForFunction(()=>visibleItems().length===2000);await page.locator('#searchInput').blur();
   await page.keyboard.press('End');const scroll=await page.evaluate(()=>elements.results.scrollTop);
   await page.evaluate(()=>navigateTo(state.rootPath+'/Nested'));await page.waitForFunction(()=>state.currentPath.endsWith('/Nested')&&!state.loading);
   await page.locator('#backButton').click();await page.waitForFunction(()=>state.currentPath==='/Synthetic Files');
   assert.equal(await page.evaluate(()=>elements.results.scrollTop),scroll);assert.equal(await page.evaluate(()=>[...state.selection][0]),root+'/Artwork 1999.psd');
   const calls=log.lists.length;await page.locator('#forwardButton').click();await page.waitForFunction(()=>state.currentPath.endsWith('/Nested'));assert.equal(log.lists.length,calls);
   await page.evaluate(()=>{void navigateTo(state.rootPath+'/Slow');void navigateTo(state.rootPath+'/Fast');});await page.waitForFunction(()=>state.currentPath.endsWith('/Fast')&&!state.loading);await delay(400);assert.equal(await page.evaluate(()=>state.currentPath),root+'/Fast');
   await page.evaluate(()=>{setSingleSelection(state.items[0].path);startDownload();startDownload();});await page.waitForFunction(()=>document.querySelector('iframe[src*="files-download"]'));
   assert.equal(log.downloads,1);
   await page.evaluate(()=>addFiles([new File(['test'],'safe.txt')]));await page.waitForFunction(()=>state.uploadRows[0]?.status==='completed');
   assert.deepEqual(log.errors,[]);await context.close();
  }
  {
   const {context,page,log}=await fixture(browser,source,{count:500,paginate:true,listingDelay:100});
   await page.goto('http://files.synthetic.test/files-window');assert(await page.locator('#openButton').isVisible());
   await page.waitForFunction(()=>state.items.length===100&&state.loadingMore);await page.locator('.file-item').first().click();assert.equal(await page.locator('.file-item.selected').count(),1);
   await page.waitForFunction(()=>state.items.length===500&&!state.loadingMore);assert.equal(log.lists.length,5);assert.equal(await page.locator('.file-item.selected').count(),1);assert.deepEqual(log.errors,[]);await context.close();
  }
  {
   const {context,page,log}=await fixture(browser,source,{count:1000,thumbnails:true});
   await page.goto('http://files.synthetic.test/files-window');await page.waitForFunction(()=>state.items.length===1000);await delay(300);
   await page.evaluate(()=>{window.peakActiveThumbnails=state.thumbnailActive;window.thumbnailSampler=setInterval(()=>window.peakActiveThumbnails=Math.max(window.peakActiveThumbnails,state.thumbnailActive),2);});
   await page.keyboard.press('End');await delay(300);assert(log.thumbs<100);assert(log.maxThumbs<=8,'at most four live requests plus aborted mock responses');
   // Open from the actual Files UI, preserve Files selection, and reuse its metadata.
   await page.locator('.file-item.focused').dblclick();
   const popup=await page.locator('#previewFrame').elementHandle().then(el=>el.contentFrame());
   await popup.waitForFunction(()=>state.naturalWidth>0);assert(log.previews.every(p=>p.small));await delay(350);
   assert.equal(log.lists.length,1,'viewer receives folder metadata without a second listing');
   await page.screenshot({path:'test-results/files-preview.png'});
   await popup.locator('#zoomInButton').click();await popup.locator('#stage').hover();await page.mouse.down();await page.mouse.move(700,450);await page.mouse.up();await popup.locator('#fitButton').click();
   await popup.locator('#closeButton').click();assert.equal(await page.locator('.file-item.selected').count(),1);
   report.thumbnails={requestsForTwoViewports:log.thumbs,peakLiveBrowserRequests:await page.evaluate(()=>{clearInterval(window.thumbnailSampler);return window.peakActiveThumbnails;}),peakMockInflightIncludingAborts:log.maxThumbs};
   assert(report.thumbnails.peakLiveBrowserRequests<=4);
   assert.deepEqual(log.errors,[]);await context.close();
  }
  {
   const {context,page,log}=await fixture(browser,source,{count:2000,paginate:true,listingDelay:180});
   // Reuse the unchanged production Orders/Files overlay installer.
   await page.goto('http://files.synthetic.test/orders');
   const topbar=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
   const installer=topbar.slice(topbar.indexOf('  if (!parentWindow.SportsCaveInternalFiles)'),topbar.indexOf('  const STYLE_ID'));
   await page.evaluate(code=>{const parentWindow=window,doc=document;eval(code);window.addEventListener("popstate",()=>SportsCaveInternalFiles.handlePop());},installer);
   const start=Date.now();await page.evaluate(()=>SportsCaveInternalFiles.open({allocation:'7',job:'a'.repeat(64)}));
   const frame=page.frameLocator('#sc-internal-files iframe');await frame.locator('body[data-edition-selected="id:file1999"]').waitFor();
   report.exactEditionSelectionMs=Date.now()-start;assert.equal(await frame.locator('.file-item.selected').textContent().then(x=>x.includes('Artwork 1999.jpg')),true);
   assert(log.lists.length<=1,'exact file usable before pagination');assert.equal(log.previews.length,0);
   await page.getByRole('button',{name:'Back to Orders'}).click();await page.waitForFunction(()=>!document.body.classList.contains('sc-files-internal'));
   assert.equal(await page.locator('#orderSearch').inputValue(),'keep order filter');assert.deepEqual(log.errors,[]);await context.close();
  }
  {
   const {context,page,log}=await fixture(browser,source,{count:500,paginate:true,listingDelay:50});
   await page.route('**/api/files-list*',route=>new URL(route.request().url()).searchParams.has('page')?route.fulfill({status:503,json:{message:'Synthetic continuation failure'}}):route.fallback());
   await page.goto('http://files.synthetic.test/files-window');await page.waitForFunction(()=>state.incomplete===true);
   assert.equal(await page.locator('.file-item').count(),100);assert((await page.locator('#itemCount').textContent()).includes('incomplete'));
   await context.close();
  }
  {
   const {context,page,log}=await fixture(browser,source,{count:2});
   await page.goto('http://files.synthetic.test/files-image-viewer?path=Artwork.psd&name=Artwork.psd');await page.waitForFunction(()=>state.naturalWidth>0);
   await page.locator('#actualButton').click();assert(log.previews.every(p=>p.small),'PSD never downloads as a preview');
   for(const extension of ['png','webp','jpg']){
    await page.evaluate(ext=>loadImage('Artwork.'+ext,{name:'Artwork.'+ext}),extension);await page.waitForFunction(ext=>elements.image.alt==='Artwork.'+ext&&elements.dimensions.textContent.includes('pixels'),extension);
   }
   await page.evaluate(()=>{void loadImage('Slow.jpg');void loadImage('Final.webp',{name:'Final.webp'});});await page.waitForFunction(()=>elements.image.alt==='Final.webp'&&state.naturalWidth>0);await delay(300);
   assert.equal(await page.locator('#image').getAttribute('alt'),'Final.webp');assert(log.previews.every(p=>p.small));
   await page.route('**/api/files-image-preview*',route=>route.fulfill({status:403,body:'Synthetic revoked session'}));
   await page.evaluate(()=>loadImage('Denied.jpg'));await page.locator('#imageError.visible').waitFor();assert((await page.locator('#imageErrorDetail').textContent()).includes('expired'));
   assert.deepEqual(log.errors,[]);await context.close();
  }
  {
   const {context,page}=await fixture(browser,source,{count:1});
   await page.route('**/api/files-resolve*',route=>route.fulfill({status:409,json:{message:'Saved revision changed'}}));
   await page.goto('http://files.synthetic.test/files-window?edition_allocation=7&edition_job='+('a'.repeat(64)));
   await page.waitForFunction(()=>document.querySelector('#toastText').textContent.includes('Saved revision changed'));
   assert.equal(await page.locator('.file-item.selected').count(),0);assert.equal(await page.locator('body').getAttribute('data-edition-selected'),null);await context.close();
  }
  fs.mkdirSync('test-results',{recursive:true});fs.writeFileSync('test-results/files-performance-v2.json',JSON.stringify(report,null,2));
  console.log(JSON.stringify(report,null,2));console.log('Files V2 browser acceptance passed.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
