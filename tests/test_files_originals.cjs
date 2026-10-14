// Synthetic browser acceptance: original pixels, preview isolation, context menus, downloads.
const fs=require('node:fs'),assert=require('node:assert/strict');
const {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const context=await browser.newContext({permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage();page.setDefaultTimeout(8000);
  await page.setContent('<canvas id="maker"></canvas>');
  const assets=await page.evaluate(()=>{
   const c=document.querySelector('canvas'),g=c.getContext('2d');
   const make=(w,h,type)=>{c.width=w;c.height=h;g.fillStyle='#123456';g.fillRect(0,0,w,h);g.fillStyle='#ffcc00';g.fillRect(w-10,h-10,10,10);return c.toDataURL(type).split(',')[1]};
   return {png:make(2400,1600,'image/png'),jpg:make(2400,1600,'image/jpeg'),webp:make(2400,1600,'image/webp'),preview:make(256,170,'image/jpeg')};
  });
  Object.assign(assets,{"gif":"R0lGODdhIAAYAIEAAP8AAAAAAAAAAAAAACwAAAAAIAAYAEAILwABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDihxJsqTJjQEBADs=","bmp":"Qk02CQAAAAAAADYAAAAoAAAAIAAAABgAAAABABgAAAAAAAAJAADEDgAAxA4AAAAAAAAAAAAAAAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/AAD/","animatedGif":"R0lGODlhIAAYAIEAAP8AAAAAAAAAAAAAACH/C05FVFNDQVBFMi4wAwEAAAAh+QQACgAAACwAAAAAIAAYAAAILwABCBxIsKDBgwgTKlzIsKHDhxAjSpxIsaLFixgzatzIsaPHjyBDihxJsqTJjQEBACH5BAEKAAEALAAAAAAgABgAgQAA/wAAAAAAAAAAAAgvAAEIHEiwoMGDCBMqXMiwocOHECNKnEixosWLGDNq3Mixo8ePIEOKHEmypMmNAQEAOw==","animatedPng":"iVBORw0KGgoAAAANSUhEUgAAACAAAAAYCAIAAAAUMWhjAAAACGFjVEwAAAACAAAAAPONk3AAAAAaZmNUTAAAAAAAAAAgAAAAGAAAAAAAAAAAAAEACgAAmQlOvAAAADBJREFUeJzt0MENAAAIwkB0/511hL749QaApHPp2vJ+PEAmQiZCJkImQiZCJkL1RA/xyAEvXzQdXQAAABpmY1RMAAAAAQAAACAAAAAYAAAAAAAAAAAAAQAKAAACeqRoAAAAN2ZkQVQAAAACeJzt0cENADAIw8CU/XemI5hPfr4BgmResmma6no8cOAPkImQiZCJkImQiVA90QfvygEvUdqnawAAAABJRU5ErkJggg==","animatedWebp":"UklGRuQAAABXRUJQVlA4WAoAAAACAAAAHwAAFwAAQU5JTQYAAAAAAAAAAABBTk1GXAAAAAAAAAAAAB8AABcAAGQAAAJWUDggRAAAALADAJ0BKiAAGAA+bTSWR6QjIiEoCACADYllAMkCgH4AAtaQY7UAAP7wm0P/yC5YXXI1//ID/kB/yA//kB/+m9mp84AAQU5NRlQAAAAAAAAAAAAfAAAXAABkAAAAVlA4IDwAAADUAgCdASogABgAPm00lkeCgIAAANiWUAdgAExQ4dowAP75Hdv//kB//kB//kB//ID//iF3shz/9P4AAAA="});
  const calls=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
  let failure=false;
  const item=(ext='jpg')=>({id:'id:art',path:'/Synthetic/Nested/art.'+ext,desktop_relative_path:'Nested/art.'+ext,name:'art.'+ext,tag:'file',kind:'image',extension:ext,revision:'r1',size:200000,type:'Image',thumbnail_key:'art',thumbnail_url:'/api/files-thumbnail?path=Nested/art.'+ext});
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());assert.equal(u.hostname,'originals.synthetic.test','no external requests');
   if(u.pathname==='/files-original-actions.js')return route.fulfill({contentType:'text/javascript',body:fs.readFileSync('components/files_original_actions.js','utf8')});
   if(u.pathname==='/files-window'||u.pathname==='/files-image-viewer')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/'+(u.pathname==='/files-window'?'files_window':'files_image_viewer')+'/index.html','utf8')});
   if(u.pathname==='/api/files-list')return route.fulfill({json:{root_path:'/Synthetic',current_path:'/Synthetic/Nested',root_name:'Files',cache_namespace:'synthetic',items:[item()],has_more:false}});
   if(u.pathname==='/api/files-image-preview')assert.equal(u.searchParams.get('representation'),'screen','viewing never requests original');
   if(u.pathname==='/api/files-thumbnail'||u.pathname==='/api/files-image-preview')return route.fulfill({contentType:'image/jpeg',body:Buffer.from(assets.preview,'base64')});
   if(u.pathname==='/api/files-download'){
    const path=u.searchParams.get('path')||u.searchParams.get('relative_path');calls.push(path);
    if(failure)return route.fulfill({status:403,body:'denied'});
    const ext=path.split('.').pop();
    if(ext==='psd')return route.fulfill({contentType:'application/octet-stream',body:'8BPS original unsupported'});
    if(path.includes('animated'))return route.fulfill({contentType:'image/'+ext,body:Buffer.from(assets['animated'+({gif:'Gif',png:'Png',webp:'Webp'})[ext]],'base64')});
    return route.fulfill({contentType:'image/'+(ext==='jpg'?'jpeg':ext),headers:{'Content-Disposition':'attachment; filename="art.'+ext+'"'},body:Buffer.from(assets[ext],'base64')});
   }
   return route.fulfill({status:404,body:''});
  });
  const clipboard=()=>page.evaluate(async()=>{
   const entries=await navigator.clipboard.read(),blob=await entries[0].getType('image/png');
   const bmp=await createImageBitmap(blob),c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;c.getContext('2d').drawImage(bmp,0,0);
   const pixels=c.getContext('2d').getImageData(0,0,bmp.width,bmp.height).data;
   const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',pixels))).join(',');
   return {width:bmp.width,height:bmp.height,digest,corner:Array.from(c.getContext('2d').getImageData(bmp.width-1,bmp.height-1,1,1).data)};
  });
  await page.goto('https://originals.synthetic.test/files-image-viewer?path=Nested/art.jpg');
  await page.waitForFunction(()=>state.naturalWidth===256);
  await page.locator('#actualButton').click();
  assert.equal(calls.length,0,'browsing and 1:1 must never fetch original');
  await page.locator('#copyImageButton').click();
  await page.waitForFunction(()=>elements.dimensions.textContent.includes('Original image copied')).catch(async e=>{console.error(await page.locator('#dimensions').textContent(),calls,errors);throw e});
  let copied=await clipboard();assert.deepEqual([copied.width,copied.height],[2400,1600]);
  assert.equal(await page.evaluate(()=>state.naturalWidth),256,'copy must not replace preview');
  assert.deepEqual(calls,['Nested/art.jpg']);
  const originalDigest=await page.evaluate(async data=>{
   const blob=new Blob([Uint8Array.from(atob(data),c=>c.charCodeAt(0))],{type:'image/jpeg'});
   const bmp=await createImageBitmap(blob),c=document.createElement('canvas');c.width=bmp.width;c.height=bmp.height;c.getContext('2d').drawImage(bmp,0,0);
   return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',c.getContext('2d').getImageData(0,0,bmp.width,bmp.height).data))).join(',');
  },assets.jpg);
  assert.equal(copied.digest,originalDigest,'lossless conversion preserves every decoded source pixel');
  // The native image menu must be intercepted even when the displayed image is tiny.
  await page.locator('#image').click({button:'right'});
  await page.getByRole('menuitem',{name:/^Copy image$/i}).click();
  await page.waitForFunction(()=>elements.dimensions.textContent.includes('Original image copied')).catch(async e=>{console.error(await page.locator('#dimensions').textContent(),calls,errors);throw e});
  await page.waitForTimeout(200);assert.equal(calls.length,2);
  const downloadPromise=page.waitForEvent('download');
  await page.getByRole('button',{name:'Download Original',exact:true}).click();
  const download=await downloadPromise;assert.equal(download.suggestedFilename(),'art.jpg');
  assert.deepEqual(fs.readFileSync(await download.path()),Buffer.from(assets.jpg,'base64'));
  // PNG pass-through and lossless conversion of WebP both retain native dimensions.
  for(const ext of ['png','webp','gif','bmp']){
   await page.evaluate(ext=>FilesOriginal.copy('/api/files-download?relative_path=Nested/art.'+ext),ext);
   copied=await clipboard();assert.deepEqual([copied.width,copied.height],['gif','bmp'].includes(ext)?[32,24]:[2400,1600]);
   if(ext==='png')assert.deepEqual(copied.corner,[255,204,0,255]);
  }
  for(const ext of ['psd']) {
   const error=await page.evaluate(async ext=>{try{await FilesOriginal.copy('/api/files-download?relative_path=Nested/art.'+ext);return ''}catch(e){return e.message}},ext);
   assert(error,'unsupported original must reject, never copy preview');
  }
  for(const ext of ['gif','png','webp']) {
   const error=await page.evaluate(async ext=>{try{await FilesOriginal.copy('/api/files-download?relative_path=Nested/animated.'+ext);return ''}catch(e){return e.message}},ext);
   assert(error,'animated originals must offer Download Original, not silently lose frames');
  }
  failure=true;
  await page.locator('#copyImageButton').click();
  await page.waitForFunction(()=>elements.dimensions.textContent.includes('Download Original'));
  failure=false;
  // All folder layouts use the same item Copy and explicit Copy Image actions.
  for(const view of ['large','medium','small','list','details']){
   await page.goto('https://originals.synthetic.test/files-window?view='+view);
   await page.waitForFunction(()=>state.items.length===1);
   const before=calls.length;
   await page.locator('.file-item').first().click({button:'right'});
   await page.getByText('Copy Image',{exact:true}).click();
   await page.waitForTimeout(200);
   assert.equal(calls.length,before+1,view+' original request');
   copied=await clipboard();assert.deepEqual([copied.width,copied.height],[2400,1600]);
   await page.locator('.file-item').first().click({button:'right'});
   await page.getByText('Copy',{exact:true}).click();
   await page.waitForTimeout(200);assert.equal(calls.length,before+2,view+' Copy uses original');
   assert.equal(await page.evaluate(()=>state.clipboard.items.length),1,'internal copy/paste reference retained');
  }
  // Embedded/enlarged preview uses the same original route and leaves its preview small.
  await page.locator('.file-item').first().dblclick();
  const viewer=page.frameLocator('#previewFrame');
  await viewer.locator('#image').waitFor({state:'visible'});
  await viewer.locator('#copyImageButton').click();
  await viewer.locator('#dimensions').filter({hasText:'Original image copied'}).waitFor();
  copied=await clipboard();assert.deepEqual([copied.width,copied.height],[2400,1600]);
  const embeddedDownload=page.waitForEvent('download');
  await viewer.locator('#downloadButton').click();
  const embeddedFile=await embeddedDownload;
  assert.deepEqual(fs.readFileSync(await embeddedFile.path()),Buffer.from(assets.jpg,'base64'));
  const beforeUnsupported=calls.length;
  const unsupported=await page.evaluate(async()=>{
   Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});
   try {await FilesOriginal.copy('/api/files-download?relative_path=Nested/art.jpg');return ''}
   catch(e){return e.message} finally {delete navigator.clipboard}
  });
  assert(unsupported.includes('unavailable'));assert.equal(calls.length,beforeUnsupported);
  assert.deepEqual(errors,[]);
  console.log('PASS: native clipboard dimensions/pixels, JPEG/PNG/WebP, original download bytes/name, right-click, five folder views, denied/unsupported assets, no browse-time original fetch.');
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
