// Files Open is embedded on every platform, even inside a companion WebView.
const assert=require('node:assert/strict'),fs=require('node:fs');
const {chromium}=require('playwright');
const source=fs.readFileSync('components/files_window/index.html','utf8');
const viewer=fs.readFileSync('components/files_image_viewer/index.html','utf8');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 let scenarios=0;
 try{
  const seed=await browser.newPage();await seed.setContent('<h1>Safe synthetic PDF</h1><div style="break-before:page"><h1>Second synthetic page</h1></div>');const pdf=await seed.pdf();
  const png=Buffer.from(await seed.evaluate(()=>{let c=document.createElement('canvas');c.width=800;c.height=600;let x=c.getContext('2d');x.fillStyle='#3079b0';x.fillRect(0,0,800,600);x.fillStyle='white';x.font='32px sans-serif';x.fillText('Synthetic preview',80,200);return c.toDataURL().split(',')[1];}),'base64');await seed.close();
  for(const platform of ['Win32','MacIntel','iPhone','WebView']){
   const context=await browser.newContext({viewport:{width:platform==='iPhone'?390:1280,height:800}});
   await context.addInitScript(platform=>{
    Object.defineProperty(navigator,'platform',{value:platform==='WebView'?'Win32':platform});
    window.helperTraffic=[];window.popupAttempts=[];
    window.chrome=window.chrome||{};window.chrome.webview={postMessage:m=>window.helperTraffic.push(m),addEventListener:()=>window.helperTraffic.push('listen'),removeEventListener:()=>{}};
    window.open=(...args)=>{window.popupAttempts.push(args);throw Error('Files must not open a new window');};
   },platform);
   const page=await context.newPage();const errors=[],requests=[],operations=[],previewRequests=[];
   context.on('page',p=>p.on('pageerror',e=>errors.push(e.message)));page.on('pageerror',e=>errors.push(e.message));
   const root='/Synthetic',make=(name,folder=root)=>({id:'id:'+name.replace(/\W/g,''),path:folder+'/'+name,desktop_relative_path:folder.slice(root.length+1)+(folder===root?'':'/')+name,name,tag:name==='Nested'?'folder':'file',kind:name==='Nested'?'folder':/\.(jpg|png|webp)$/.test(name)?'image':name.endsWith('.psd')?'photoshop':'file',extension:name.split('.').pop(),size:35000000,revision:'r1',type:'File'});
   let items=['Art.jpg','Art.png','Art.webp','Master.psd','Manual.pdf','Unsupported.txt','Nested'].map(n=>make(n));let deny=false,slow=false;
   await context.route('**/*',async route=>{
    const u=new URL(route.request().url());requests.push(u.href);
    if(u.hostname!=='files-web.test')return route.abort();
    if(u.pathname.startsWith('/files-preview-assets/6.4.299/')){const asset=u.pathname.split('/6.4.299/')[1];return route.fulfill({contentType:asset.endsWith('.mjs')||asset.endsWith('.js')?'text/javascript':asset.endsWith('.wasm')?'application/wasm':'application/octet-stream',body:fs.readFileSync('components/files_image_viewer/pdfjs-6.4.299/'+asset)});}
    if(u.pathname==='/files-window')return route.fulfill({contentType:'text/html',body:source});
    if(u.pathname==='/files-image-viewer')return route.fulfill({contentType:'text/html',body:viewer});
    if(u.pathname==='/api/files-list'){const folder=u.searchParams.get('path')||root;return route.fulfill({json:{ok:true,root_path:root,root_name:'Synthetic',current_path:folder,can_delete:true,cache_namespace:'synthetic',items:folder===root?items:[make('Child.jpg',folder)]}});}
    if(u.pathname==='/api/files-image-preview'){previewRequests.push(u);if(slow)await delay(400);return route.fulfill(deny?{status:403,body:'Denied'}:{contentType:'image/png',body:png}).catch(()=>{});}
    if(u.pathname==='/api/files-pdf-preview')return route.fulfill({contentType:'application/pdf',body:pdf});
    if(u.pathname==='/api/files-download'){operations.push({action:'download',query:u.search});return route.fulfill({contentType:'application/octet-stream',body:'synthetic'});}
    if(u.pathname==='/api/files-folder'){const d=route.request().postDataJSON();operations.push({action:'folder',...d});items.push({...make(d.name),tag:'folder',kind:'folder'});return route.fulfill({json:{ok:true}});}
    if(u.pathname==='/api/files-rename'){const d=route.request().postDataJSON();operations.push({action:'rename',...d});items=items.map(i=>i.path===d.path?{...make(d.name),id:i.id}:i);return route.fulfill({json:{ok:true}});}
    if(u.pathname==='/api/files-delete'){const d=route.request().postDataJSON();operations.push({action:'delete',...d});items=items.filter(i=>!d.paths.includes(i.path));return route.fulfill({json:{ok:true,deleted:d.paths}});}
    if(u.pathname==='/api/files-paste'){const d=route.request().postDataJSON();operations.push({action:'paste',...d});return route.fulfill({json:{ok:true,successful:d.paths.map(path=>({source_path:root+'/'+path})),failed:[],skipped:[]}});}
    return route.fulfill({status:404,json:{message:'Unexpected fixture request: '+u.pathname}});
   });
   await page.goto('https://files-web.test/files-window');await page.locator('.file-item').first().waitFor();
   const row=name=>page.locator('.file-item').filter({has:page.locator('.file-name',{hasText:name})});
   // Match exact file via accessible metadata, avoiding Art.jpg matching other content.
   const file=name=>page.locator('.file-item').filter({hasText:name});
   const frame=()=>page.frames().find(f=>f.url().includes('/files-image-viewer'));
   const loaded=async()=>{await page.locator('#previewPanel').waitFor();await page.waitForFunction(()=>state.imageViewerReady);await frame().waitForFunction(()=>state.naturalWidth>0);};
   const close=async()=>{await frame().locator('#closeButton').click();await page.locator('#previewPanel').waitFor({state:'hidden'});};
   await file('Art.jpg').dblclick();await loaded();assert.equal(context.pages().length,1);assert(previewRequests.every(u=>u.searchParams.get('representation')==='screen'));await close();
   assert.equal(await page.locator('.file-item.selected').count(),1);
   const calls=previewRequests.length;await file('Art.jpg').click({button:'right'});await page.locator('#menu').getByRole('button',{name:'Open',exact:true}).click();await loaded();assert.equal(previewRequests.length,calls);await close();
   await file('Art.png').click();await page.locator('#openButton').click();await loaded();assert.equal(await frame().evaluate(()=>state.path),'Art.png');await close();
   await file('Art.webp').click();await page.keyboard.press('Enter');await loaded();assert.equal(await frame().evaluate(()=>state.path),'Art.webp');
   await frame().locator('#zoomInButton').click();await frame().locator('#stage').hover();await page.mouse.down();await page.mouse.move(240,220);await page.mouse.up();await frame().locator('#fitButton').click();await frame().locator('#stage').press('Escape');await page.locator('#previewPanel').waitFor({state:'hidden'});
   await file('Master.psd').dblclick();await loaded();await frame().locator('#actualButton').click();assert(previewRequests.every(u=>u.searchParams.get('representation')==='screen'));await close();
   assert(!requests.some(u=>u.includes('/files-preview-assets/')),'PDF renderer must be lazy');
   await file('Manual.pdf').dblclick();await page.waitForFunction(()=>state.imageViewerReady);await frame().locator('#pdf canvas').waitFor();assert(await frame().locator('#pdf canvas').evaluate(c=>{let d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let ink=0;for(let i=0;i<d.length;i+=4)if(d[i]<100&&d[i+1]<100&&d[i+2]<100&&d[i+3]>0)ink++;return ink>100;}));await frame().locator('#zoomInButton').click();await frame().locator('#pdf[data-rendered-page="1"] canvas').waitFor();await frame().locator('#nextButton').click();await frame().locator('#pdf[data-rendered-page="2"] canvas').waitFor();await frame().locator('#previousButton').click();await frame().locator('#pdf[data-rendered-page="1"] canvas').waitFor();await page.screenshot({path:'test-results/files-web-pdf-'+platform+'.png'});assert(requests.some(u=>u.includes('pdf.worker.min.mjs')));await close();
   const pdfCalls=requests.filter(u=>u.includes('/api/files-pdf-preview')).length;await file('Manual.pdf').dblclick();await frame().locator('#pdf canvas').waitFor();assert.equal(requests.filter(u=>u.includes('/api/files-pdf-preview')).length,pdfCalls);await close();
   const originalCalls=previewRequests.length;await file('Unsupported.txt').dblclick();await frame().getByText('Unsupported Preview. Use Download to save this file.',{exact:true}).waitFor();assert.equal(previewRequests.length,originalCalls);await frame().locator('#downloadButton').click();await page.waitForFunction(()=>document.querySelector('iframe[src*="files-download"]'));assert.equal(operations.filter(x=>x.action==='download').length,1);await close();
   await file('Nested').dblclick();await page.waitForFunction(()=>state.currentPath.endsWith('/Nested'));assert(await page.locator('#previewPanel').isHidden());await page.locator('#backButton').click();await file('Art.jpg').waitFor();
   // Actual file-operation dialogs: no stale references to the deleted helper state.
   await page.locator('#newButton').click();await page.locator('#newFolderName').fill('Created');await page.getByRole('button',{name:'Create',exact:true}).click();await page.locator('#modalBackdrop').waitFor({state:'hidden'});await file('Created').waitFor();
   await file('Unsupported.txt').click();await page.locator('#renameButton').click();await page.locator('#renameName').fill('Renamed.txt');await page.locator('#modal').getByRole('button',{name:'Rename',exact:true}).click();await file('Renamed.txt').waitFor();
   await file('Renamed.txt').click();await page.locator('#deleteButton').click();await page.locator('#modal').getByRole('button',{name:'Delete 1 item',exact:true}).click();await file('Renamed.txt').waitFor({state:'hidden'});
   await file('Art.jpg').click();await page.keyboard.press('Control+c');await file('Nested').dblclick();await page.waitForFunction(()=>state.currentPath.endsWith('/Nested'));await page.keyboard.press('Control+v');await page.waitForFunction(()=>!state.clipboardBusy);await delay(30);assert(operations.some(x=>x.action==='paste'&&x.operation==='copy'));
   await page.locator('#backButton').click();await file('Art.jpg').click();await page.keyboard.press('Control+x');await file('Nested').dblclick();await page.waitForFunction(()=>state.currentPath.endsWith('/Nested'));await page.keyboard.press('Control+v');await page.waitForFunction(()=>!state.clipboardBusy);await delay(30);assert(operations.some(x=>x.action==='paste'&&x.operation==='move'));
   await page.locator('#backButton').click();await file('Art.jpg').click();await page.locator('#searchInput').fill('Master');await page.waitForFunction(()=>document.querySelectorAll('.file-item').length===1);await page.locator('#searchInput').fill('');await page.waitForFunction(()=>document.querySelectorAll('.file-item').length>1);
   // Closing cancels an obsolete preview; late data must not reopen or change Files.
   await frame().evaluate(()=>{state.previewCache.forEach(c=>URL.revokeObjectURL(c.url));state.previewCache.clear();});slow=true;await file('Art.jpg').dblclick();await page.locator('#previewClose').click();await delay(450);assert(await page.locator('#previewPanel').isHidden());assert.equal(await frame().evaluate(()=>state.naturalWidth),0);slow=false;
   deny=true;await file('Art.jpg').dblclick();await frame().getByText('Files access expired. Sign in again.',{exact:true}).waitFor();await close();
   for(const f of page.frames()){assert.deepEqual(await f.evaluate(()=>window.helperTraffic),[]);assert.deepEqual(await f.evaluate(()=>window.popupAttempts),[]);}
   assert(!requests.some(u=>/files-native-|files-desktop-helper|localhost|127\.0\.0\.1/.test(u)));
   assert.equal(context.pages().length,1);assert.deepEqual(errors,[]);assert(await page.locator('body').evaluate(el=>el.scrollWidth<=innerWidth));
   await context.close();scenarios++;
  }
  console.log(`Files web-only: ${scenarios} platform journeys passed: embedded JPG/PNG/WebP/PSD/PDF, all Open actions, cache reuse, unsupported Download, close cancellation, permissions, create/rename/delete/copy/move/search, zero helper traffic or windows.`);
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
