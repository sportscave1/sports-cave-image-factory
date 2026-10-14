const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage();
  const errors=[],requests=[];page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<canvas id="c" width="256" height="192"></canvas>');
  const thumbnail=Buffer.from(await page.evaluate(()=>{const x=c.getContext('2d');x.fillStyle='#317a9f';x.fillRect(0,0,256,192);return c.toDataURL('image/webp',.76).split(',')[1];}),'base64');
  const root='/Synthetic';let active=0,peak=0,delay=150;
  const item=i=>({id:'id:'+i,path:root+'/Art '+i+'.jpg',desktop_relative_path:'Art '+i+'.jpg',name:'Art '+i+'.jpg',tag:'file',kind:'image',extension:'jpg',revision:'r1',size:35000000,type:'Image',thumbnail_key:'id:'+i+'|r1',thumbnail_url:'/api/files-thumbnail?path=Art%20'+i+'.jpg&rev=r1'});
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());if(u.hostname!=='thumbnails.synthetic.test')return route.abort();
   if(u.pathname==='/files-window')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/files_window/index.html','utf8')});
   if(u.pathname==='/files-image-viewer')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/files_image_viewer/index.html','utf8')});
   if(u.pathname==='/api/files-list')return route.fulfill({json:{root_path:root,current_path:root,root_name:'Files',cache_namespace:'worker',items:Array.from({length:500},(_,i)=>item(i)),has_more:false}});
   if(u.pathname==='/api/files-thumbnail'){
    requests.push(u.href);active++;peak=Math.max(peak,active);
    await new Promise(r=>setTimeout(r,delay));active--;
    if(u.searchParams.get('rev')==='denied')return route.fulfill({status:403,body:''});
    return route.fulfill({contentType:'image/webp',body:thumbnail});
   }
   if(u.pathname==='/api/files-image-preview'){assert.equal(u.searchParams.get('representation'),'screen');await new Promise(r=>setTimeout(r,300));return route.fulfill({contentType:'image/webp',body:thumbnail});}
   return route.fulfill({status:404,body:''});
  });
  await page.goto('http://thumbnails.synthetic.test/files-window');
  await page.waitForFunction(()=>state.items.length===500&&state.thumbnailActive>0);
  await page.evaluate(()=>{window.peakLive=state.thumbnailActive;window.sampler=setInterval(()=>window.peakLive=Math.max(window.peakLive,state.thumbnailActive),5);});
  const before=await page.locator('.file-item').first().boundingBox();
  assert(await page.locator('.thumbnail-skeleton').count()>0);
  assert(await page.locator('.file-icon:has(img.thumbnail) > svg').evaluateAll(nodes=>nodes.every(n=>getComputedStyle(n).visibility==='hidden')));
  await page.screenshot({path:'test-results/files-v4-skeleton.png'});
  await page.locator('.file-item').first().locator('.has-thumbnail').waitFor();
  const after=await page.locator('.file-item').first().boundingBox();assert.deepEqual(after,before);
  const cached=await page.evaluate(()=>{
   const start=performance.now(),item=visibleItems()[0];
   const row=createItemElement(item,0),image=row.querySelector('img.thumbnail');
   return {ms:performance.now()-start,src:image.getAttribute('src'),key:image.dataset.thumbnailKey,expected:state.thumbnailCache.get(item.thumbnail_key).url};
  });
  assert.equal(cached.src,cached.expected,'cache is attached synchronously before observer/DOM insertion');
  const changed=await page.evaluate(()=>{
   const row=createItemElement({...visibleItems()[0],revision:'r2',thumbnail_key:'id:0|r2'},0);
   return row.querySelector('img.thumbnail').getAttribute('src');
  });assert.equal(changed,null,'a different revision never borrows the old thumbnail');
  await page.locator('.file-item').first().dblclick();
  const view=await page.locator('#previewFrame').elementHandle().then(e=>e.contentFrame());
  await view.waitForFunction(()=>elements.dimensions.textContent.startsWith('Small preview'));
  await view.waitForFunction(()=>elements.dimensions.textContent.startsWith('Preview'));
  await view.locator('#closeButton').click();
  await page.locator('#previewPanel').waitFor({state:'hidden'});
  await page.screenshot({path:'test-results/files-v4-thumbnails.png'});
  const callsBefore=requests.length;
  await page.evaluate(()=>{elements.results.scrollTop=20000;renderVirtualRows();});
  await page.waitForTimeout(350);
  assert(requests.length<150,'only visible and bounded nearby rows are requested, not 500 images');
  assert(await page.locator('.file-item').count()<150);
  const interrupted=requests.length;
  await page.evaluate(()=>{stopThumbnailLoading();elements.items.replaceChildren();});
  await page.waitForTimeout(350);assert.equal(requests.length,interrupted);
  await page.evaluate(()=>{state.items=[{...state.items[0],revision:'denied',thumbnail_key:'denied',thumbnail_url:'/api/files-thumbnail?path=Art.jpg&rev=denied'}];renderItems();});
  await page.locator('.thumbnail-failed').waitFor();
  assert.equal(await page.locator('.thumbnail-failed > svg').evaluate(n=>getComputedStyle(n).visibility),'visible');
  const peakLive=await page.evaluate(()=>{clearInterval(window.sampler);return window.peakLive;});assert(peakLive<=4);
  await page.evaluate(()=>{
   const payload={root_path:'/Synthetic',current_path:'/Synthetic',cache_namespace:'other-worker',items:[]};
   applyFolderPayload(payload);
  });
  assert.equal(await page.evaluate(()=>state.thumbnailCache.size),0);
  assert.equal(await page.locator('#previewFrame').count(),0);
  assert.deepEqual(errors,[]);
  const result={environment:'Chrome, synthetic 500-image listing, 150 ms thumbnail/300 ms screen network fixture',cachedAttachMs:cached.ms,thumbnailBytes:thumbnail.length,thumbnailRequests:requests.length,requestsBeforeScroll:callsBefore,peakMockInflightIncludingAborted:peak,peakLiveBrowserRequests:peakLive,layoutShift:false,cachedAttachedBeforeObserver:true};
  fs.writeFileSync('test-results/files-thumbnails-v4.json',JSON.stringify(result,null,2));console.log(result);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
