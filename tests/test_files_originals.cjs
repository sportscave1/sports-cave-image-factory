// Synthetic Chrome acceptance: selection, exact original downloads, honest clipboard limits.
const fs=require('node:fs'), assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'), {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const context=await browser.newContext({viewport:{width:1280,height:800},permissions:['clipboard-read','clipboard-write']});
  const page=await context.newPage();page.setDefaultTimeout(6000);
  const errors=[],originals=[],downloads=[],report={browser:browser.version()};
  page.on('pageerror',e=>errors.push(e.message));
  await page.setContent('<canvas id="c" width="64" height="48"></canvas>');
  const bytes=Buffer.from(await page.evaluate(()=>{const c=document.querySelector('canvas');c.getContext('2d').fillRect(0,0,64,48);return c.toDataURL('image/webp').split(',')[1]}),'base64');
  const secondBytes=Buffer.from(await page.evaluate(()=>{const c=document.querySelector('canvas');c.getContext('2d').fillStyle='red';c.getContext('2d').fillRect(0,0,64,48);return c.toDataURL('image/webp').split(',')[1]}),'base64');
  const sourceBytes=name=>parseInt(name,10)%2?secondBytes:bytes;
  const items=Array.from({length:400},(_,i)=>({id:'id:'+i,path:'/Synthetic/'+String(i).padStart(3,'0')+'.webp',name:String(i).padStart(3,'0')+'.webp',desktop_relative_path:String(i).padStart(3,'0')+'.webp',tag:'file',kind:'image',extension:'webp',type:'WEBP',revision:'r1'}));
  let baseline=false;
  await context.route('**/*',async route=>{
   const u=new URL(route.request().url());assert.equal(u.hostname,'files.synthetic.test');
   if(u.pathname==='/files-window'||u.pathname==='/files-image-viewer'||u.pathname==='/files-original-actions.js'){
    const name=u.pathname==='/files-original-actions.js'?'components/files_original_actions.js':'components/'+(u.pathname==='/files-window'?'files_window':'files_image_viewer')+'/index.html';
    return route.fulfill({contentType:name.endsWith('.js')?'text/javascript':'text/html',body:baseline?execFileSync('git',['show','HEAD:'+name],{encoding:'utf8'}):fs.readFileSync(name,'utf8')});
   }
   if(u.pathname==='/api/files-list') return route.fulfill({json:{root_path:'/Synthetic',current_path:'/Synthetic',items,has_more:false}});
   if(u.pathname==='/api/files-preview') return route.fulfill({contentType:'image/webp',body:bytes});
   if(u.pathname==='/api/files-download'){
    const name=(u.searchParams.get('path')||u.searchParams.get('relative_path')).split('/').pop();originals.push(name);
    return route.fulfill({headers:{'content-type':'image/webp','content-disposition':`attachment; filename="${name}"`},body:sourceBytes(name)});
   }
   return route.fulfill({status:404,body:''});
  });
  page.on('download',d=>downloads.push(d));
  // Reproduce both original handlers before changing behavior. This is a real
  // browser clipboard write; decoded PNG success is not native file success.
  baseline=true;await page.goto('https://files.synthetic.test/files-window');await page.waitForFunction(()=>state.items.length===400);
  await page.locator('.file-item').first().click({button:'right'});await page.locator('#menu').getByText('Copy',{exact:true}).click();
  await page.waitForFunction(()=>elements.toastText.textContent.includes('PNG clipboard')||elements.toastText.textContent.includes('Download Original'));
  report.baselineCard=await page.locator('#toastText').textContent();
  report.baselineClipboard=await page.evaluate(async()=> (await navigator.clipboard.read()).map(x=>x.types));
  await page.locator('.file-item').first().dblclick();
  const frame=page.frameLocator('#previewFrame');await frame.locator('#copyImageButton').click();
  await frame.locator('#dimensions').filter({hasText:/PNG clipboard|Download Original/}).waitFor();
  report.baselinePreview=await frame.locator('#dimensions').textContent();
  baseline=false;await page.goto('https://files.synthetic.test/files-window');await page.waitForFunction(()=>state.items.length===400);originals.length=0;
  report.rejections=await page.evaluate(async()=>{const results={};for(const type of ['webp','multiple']){try{await navigator.clipboard.write(type==='webp'?[new ClipboardItem({'image/webp':new Blob(['synthetic'],{type:'image/webp'})})]:[new ClipboardItem({'text/plain':new Blob(['one'],{type:'text/plain'})}),new ClipboardItem({'text/plain':new Blob(['two'],{type:'text/plain'})})]);results[type]='success';}catch(e){results[type]=e.message;}}return results;});
  assert(report.rejections.webp.includes('not supported'));assert(report.rejections.multiple.includes('multiple'));
  report.support=await page.evaluate(()=>Object.fromEntries(['image/webp','application/octet-stream','text/uri-list','image/png'].map(t=>[t,ClipboardItem.supports(t)])));
  const row=i=>page.locator(`.file-item[data-index="${i}"]`);
  const selected=()=>page.evaluate(()=>[...state.selection]);
  await row(0).click();assert.equal((await selected()).length,1);assert(await page.locator('#previewPanel').isHidden());
  await row(2).click({modifiers:['Control']});assert.equal((await selected()).length,2);
  await row(5).click({modifiers:['Shift']});assert.equal((await selected()).length,4);
  await page.keyboard.press('Escape');assert.equal((await selected()).length,0);
  await row(0).click();await page.keyboard.press('Control+a');assert.equal((await selected()).length,400);
  await page.locator('#searchInput').focus();await page.keyboard.press('Control+a');assert.equal((await selected()).length,400);
  await page.locator('#searchInput').press('Control+c');assert(await page.locator('#toast').evaluate(e=>!e.classList.contains('visible')));
  await row(0).click();await page.keyboard.press('Control+c');await page.getByText('Copy unavailable',{exact:true}).waitFor();
  assert((await page.locator('#toastText').textContent()).includes('Native file copying is unavailable'));assert.equal(originals.length,0);
  await page.waitForTimeout(2100);assert.equal(await page.locator('#copyButton .command-label').innerText(),'Copy');
  // Copy on a selected card snapshots all selected files, then failure fallback
  // downloads that snapshot even if selection/navigation changes afterwards.
  await page.evaluate(()=>{window.originalCopy=FilesOriginal.copy;FilesOriginal.copy=items=>{window.copySnapshot=items;return new Promise((resolve,reject)=>window.rejectCopy=reject)}});
  await row(1).click({modifiers:['Control']});
  await row(0).click({button:'right'});await page.locator('#menu').getByText('Copy 2 files',{exact:true}).click();
  await page.waitForFunction(()=>window.copySnapshot?.length===2);assert.equal(await page.locator('#copyButton .command-label').innerText(),'Copying…');
  await row(5).click();await page.evaluate(()=>window.rejectCopy(new Error('Native file copying is unavailable')));
  await page.getByText('Copy unavailable',{exact:true}).waitFor();
  const before=downloads.length;await page.locator('#toastAction').click();
  await page.waitForTimeout(700);
  assert.equal(downloads.length,before+2);
  while(downloads.length<before+2)await page.waitForTimeout(50);
  for(const [i,d] of downloads.slice(before).entries()) {assert.equal(d.suggestedFilename(),items[i].name);assert.deepEqual(fs.readFileSync(await d.path()),sourceBytes(d.suggestedFilename()));}
  await page.evaluate(()=>FilesOriginal.copy=window.originalCopy);
  await row(7).click({button:'right'});await page.locator('#menu').getByText('Copy',{exact:true}).click();assert.equal((await selected()).length,1);
  // Original downloads are unchanged and exact. Selection never fetches originals.
  const previous=originals.length;
  async function rectangle(reverse=false){
   await page.evaluate(()=>{elements.results.scrollTop=0;setView('medium');});
   const b=await page.locator('#results').boundingBox(),r=await row(0).boundingBox(),last=await row(10).boundingBox();
   const start={x:b.x+2,y:b.y+3},end={x:last.x+last.width/2,y:last.y+last.height/2};
   await page.mouse.move(reverse?end.x:start.x,reverse?b.y+2:start.y); // empty top padding in either direction
   if(reverse){start.x=end.x;start.y=b.y+2;end.x=r.x+r.width/2;end.y=r.y+r.height/2;}
   await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:8});
   assert(await page.locator('.selection-rectangle').isVisible());
   const expected=await page.evaluate(({start,end})=>[...elements.items.querySelectorAll('.file-item')].filter(row=>{const r=row.getBoundingClientRect();return r.left<=Math.max(start.x,end.x)&&r.right>=Math.min(start.x,end.x)&&r.top<=Math.max(start.y,end.y)&&r.bottom>=Math.min(start.y,end.y)}).map(row=>row.dataset.path),{start,end});
   await page.mouse.up();assert.deepEqual((await selected()).sort(),expected.sort());assert(expected.length>0);
   assert.equal(await page.locator('.selection-rectangle').count(),0);
  }
  await rectangle();await rectangle(true);
  // Reverse vertical drag starts in the inter-card gap, not on a card.
  const a=await row(0).boundingBox(),z=await row(10).boundingBox(),area=await page.locator('#results').boundingBox();
  await page.mouse.move(area.x+2,z.y+z.height);await page.mouse.down();await page.mouse.move(a.x+a.width/2,a.y+5,{steps:8});await page.mouse.up();assert((await selected()).length>0);
  for(const zoom of [0.8,1.25]){await page.evaluate(z=>document.body.style.zoom=z,zoom);await rectangle();}
  await page.evaluate(()=>document.body.style.zoom='1');
  await page.evaluate(()=>elements.results.scrollTop=0);
  const bounds=await page.locator('#results').boundingBox();await page.mouse.move(bounds.x+2,bounds.y+2);await page.mouse.down();await page.mouse.move(bounds.x+200,bounds.y+bounds.height-2,{steps:8});await page.waitForTimeout(500);
  assert(await page.evaluate(()=>elements.results.scrollTop>100));const paths=await selected();assert(paths.length>10);await page.mouse.up();
  // Empty click and Escape clear; mouse/touch controls retain their normal actions.
  await page.mouse.click(bounds.x+2,bounds.y+2);assert.equal((await selected()).length,0);
  await page.locator('#results').focus();await page.keyboard.press('Control+a');await page.keyboard.press('Escape');assert.equal((await selected()).length,0);
  assert.equal(originals.length,previous);
  await page.evaluate(()=>{elements.results.scrollTop=0;renderVirtualRows();});
  await row(0).dblclick();await frame.locator('#copyImageButton').click();await frame.locator('#dimensions').filter({hasText:'Native file copying is unavailable'}).waitFor();assert.equal(originals.length,previous);
  await frame.locator('#closeButton').click();await page.locator('#previewPanel').waitFor({state:'hidden'});
  // Repeated immediate failures must refresh the toast's snapshot action.
  await row(2).click();await page.locator('#copyButton').click();
  await row(3).click();await page.locator('#copyButton').click();
  const oneDownload=page.waitForEvent('download');await page.locator('#toastAction').click();
  assert.equal((await oneDownload).suggestedFilename(),'003.webp');
  await page.locator('#searchInput').fill('00');await page.waitForTimeout(250);
  await page.locator('#results').focus();await page.keyboard.press('Control+a');
  assert.equal((await selected()).length,13);
  await page.locator('#searchInput').fill('');await page.waitForTimeout(250);
  // Same geometry in the non-virtual grid, list and details views.
  await page.evaluate(()=>{state.items=state.items.slice(0,30);elements.results.scrollTop=0;renderItems();});
  for(const view of ['medium','large','small','list','details']){
   await page.evaluate(view=>setView(view),view);
   const r=await row(0).boundingBox(),b=await page.locator('#results').boundingBox();
   await page.mouse.move(b.x+2,r.y+1);await page.mouse.down();await page.mouse.move(r.x+r.width/2,r.y+r.height/2,{steps:5});await page.mouse.up();
   assert((await selected()).includes(items[0].path),view);
  }
  await page.locator('#viewButton').click();assert.equal(await page.locator('.selection-rectangle').count(),0);await page.keyboard.press('Escape');
  assert.deepEqual(errors,[]);
  report.downloads=downloads.map(d=>d.suggestedFilename());report.status='Selection and exact original download fallback passed; native file copy unavailable; ChatGPT/Explorer paste unverified.';
  fs.mkdirSync('test-results/files-selection',{recursive:true});fs.writeFileSync('test-results/files-selection/report.json',JSON.stringify(report,null,2));
  await page.screenshot({path:'test-results/files-selection/desktop.png'});console.log(JSON.stringify(report,null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
