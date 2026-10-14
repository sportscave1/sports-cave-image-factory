const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
const top=fs.readFileSync('components/sports_cave_top_bar/index.html','utf8');
const installer=top.slice(0,top.indexOf('  const STYLE_ID =')).replace('__SPORTS_CAVE_TOP_BAR_CONFIG__','{}')+'})();</script></body></html>';
for(const width of [1280,390]){
 const context=await browser.newContext({viewport:{width,height:800},acceptDownloads:true});
 let starts=0,locations=0,folders=0,frames=0,fullDownloads=0,missing=false,ready=false;
 const job='a'.repeat(64),folder='/Sportscave Team Folder/03_ASSETS/Auto Editions/Generated JPGs/SC3283/TEST';
 const item={id:'id:exact',path:folder+'/SC3283-Unit1-001-of-100-TEST.jpg',name:'SC3283-Unit1-001-of-100-TEST.jpg',tag:'file',kind:'image',extension:'jpg',type:'JPEG image',revision:'rev',size:35690518};
 await context.route('**/*',async route=>{const u=new URL(route.request().url());
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:`<style>body{margin:0}#sports-cave-os-top-bar{height:64px}[data-testid=stMain]{margin-left:${width>600?220:0}px;height:736px;overflow:auto}.grid{height:160px;overflow:auto}.tall{height:900px}</style><header id="sports-cave-os-top-bar">Sports Cave OS</header><section data-testid="stSidebar">Navigation</section><section data-testid="stMain"><div data-testid="stMainBlockContainer"><input aria-label="Search orders" value="SC3283"><div class="grid"><div class="tall">Orders table</div></div><a href="/auto-editions/${ready?'open?allocation_id=652&job_id='+job+'#Open':'download?allocation_id=652#Download JPG'}">${ready?'Open':'Download JPG'}</a><button>Other row</button><iframe src="/shell"></iframe><iframe src="/component"></iframe></div></section>`});
  if(u.pathname==='/shell')return route.fulfill({contentType:'text/html',body:installer});
  if(u.pathname==='/component')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/psd_picker/index.html','utf8')});
  if(u.pathname.endsWith('/inline.js'))return route.fulfill({contentType:'application/javascript',body:fs.readFileSync('components/psd_picker/inline.js','utf8')});
  if(u.pathname==='/files-window'){frames++;return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/files_window/index.html','utf8')});}
  if(u.pathname==='/api/auto-editions/start'){starts++;await new Promise(r=>setTimeout(r,300));return route.fulfill({json:{job_id:job,status:'Queued'}});}
  if(u.pathname==='/api/auto-editions/state'){await new Promise(r=>setTimeout(r,300));ready=true;return route.fulfill({json:{job_id:job,status:'Ready',filename:item.name}});}
  if(u.pathname==='/api/auto-editions/location'){locations++;return route.fulfill({status:missing?409:200,json:missing?{error:'Saved JPG unavailable. Return to Orders and Retry Open.'}:{ok:true,file_id:item.id,revision:item.revision,path:item.path,folder_path:folder}});}
  if(u.pathname==='/api/files-list'){folders++;return route.fulfill({json:{root_path:'/Sportscave Team Folder',current_path:folder,items:[item],cache_namespace:'worker',cached_for_seconds:180}});}
  if(u.pathname==='/api/auto-editions/file'){fullDownloads++;return route.fulfill({contentType:'image/jpeg',headers:{'Content-Disposition':'attachment; filename="'+item.name+'"'},body:Buffer.from('offline synthetic fixture')});}

  return route.fulfill({status:404});
 });
 const page=await context.newPage();await page.goto('https://edition-v9.local.test/?page=orders');await page.waitForFunction(()=>!!window.SportsCaveAutoEditions&&!!window.SportsCaveFilesWindow);
 await page.locator('.grid').evaluate(e=>e.scrollTop=125);
 // Real Streamlit links use canvas/window.open rather than DOM anchors.
 await page.evaluate(()=>{
  const host=document.createElement('div');host.dataset.testid='stDataFrame';host.style.position='relative';
  const canvas=document.createElement('canvas');canvas.width=200;canvas.height=40;host.append(canvas);
  document.querySelector('[data-testid=stMainBlockContainer]').prepend(host);
  const setup=document.createElement('a');setup.href='/auto-editions/setup?allocation_id=652';setup.textContent='Auto Editions setup';host.append(setup);
  const context=canvas.getContext('2d');context.font='12px system-ui';context.fillText('Download JPG',10,20);
  canvas.onclick=()=>window.open('/auto-editions/download?allocation_id=652#Download JPG');
 });
 await page.evaluate(()=>{document.addEventListener('pointerdown',()=>window.clickedAt=performance.now(),{once:true,capture:true});new MutationObserver(()=>{if(window.feedbackMs===undefined&&document.querySelector('.sc-edition-generating[role=status]'))window.feedbackMs=performance.now()-window.clickedAt;}).observe(document.body,{subtree:true,childList:true});});
 const popupPromise=context.waitForEvent('page',{predicate:p=>p.opener().then(o=>o===page)});popupPromise.catch(()=>{});
 const download=page.waitForEvent('download');download.catch(()=>{});const clicked=Date.now();await page.locator('canvas').click({position:{x:30,y:16}});
 await page.locator('.sc-edition-generating[role=status]').waitFor();const feedbackMs=await page.evaluate(()=>window.feedbackMs);console.log(JSON.stringify({width,clientFeedbackMs:feedbackMs,automationRoundTripMs:Date.now()-clicked}));assert(feedbackMs<150,'Canvas feedback must precede the delayed start response');
 await page.getByRole('link',{name:'Generating…',exact:true}).waitFor();await page.getByRole('button',{name:'Other row',exact:true}).click();await page.getByRole('link',{name:'Generating…',exact:true}).click();
 // A real Streamlit rerun retires the component realm during cloud polling.
 // Completion and later Open clicks must survive its stale refresh callback.
 await page.locator('iframe[src="/component"]').evaluate(e=>e.remove());
 const transfer=await download;assert.equal(transfer.suggestedFilename(),item.name);
 const popup=await popupPromise;
 assert(popup,'Existing Files popup should open');
 await popup.locator('.file-item.selected').waitFor();
 assert.equal(starts,1);assert.equal(locations,1);assert.equal(await page.getByRole('dialog').count(),0);
 assert.equal(await page.locator('#sc-edition-error').count(),0);
 assert.equal(await page.locator('a[href="/auto-editions/setup?allocation_id=652"]').textContent(),'Auto Editions setup');
 assert.equal(page.url(),'https://edition-v9.local.test/?page=orders');
 assert(await page.getByRole('textbox',{name:'Search orders'}).isVisible());
 assert.equal(await popup.locator('.file-item.selected').getAttribute('data-path'),item.path);
 assert.equal(await page.getByRole('textbox',{name:'Search orders'}).inputValue(),'SC3283');
 assert.equal(await page.locator('.grid').evaluate(e=>e.scrollTop),125);
 const warmStart=Date.now();await page.getByRole('link',{name:'Open',exact:true}).last().click();
 await popup.locator('body[data-edition-selected="id:exact"]').waitFor();
 assert.equal(frames,1);assert.equal(folders,1);assert.equal(starts,1);
 console.log(JSON.stringify({width,warmOpenMs:Date.now()-warmStart,starts,locations,folders,frames}));
 await popup.close();
 assert.equal(await page.getByRole('textbox',{name:'Search orders'}).inputValue(),'SC3283');
 // A denied popup must not navigate Orders or create a blank fallback tab.
 await page.evaluate(()=>window.open=()=>null);
 await page.getByRole('link',{name:'Open',exact:true}).last().click();
 assert.equal(page.url(),'https://edition-v9.local.test/?page=orders');assert.equal(starts,1);
 await context.close();
}
console.log('V12 Edge desktop/mobile popup, exact selection, unchanged Orders, duplicate prevention, download and blocked-popup checks passed.');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
