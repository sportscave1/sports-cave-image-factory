// Actual Chrome, synthetic files only. Visual/layout checks and paired rendering samples.
const fs=require('node:fs'), assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'),{chromium}=require('playwright');
const output='test-results/files-compact';fs.mkdirSync(output,{recursive:true});
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const sources={before:execFileSync('git',['show','e021e88b:components/files_window/index.html'],{encoding:'utf8'}),after:fs.readFileSync('components/files_window/index.html','utf8')};
  const folders=['Collector Editions','Formula One','Football Legends','Master Artwork','Motorsport Archives','New Releases','Signed Collections','Vintage Racing'];
  const types=[['jpg','image'],['psd','photoshop'],['pdf','pdf'],['csv','sheet'],['mp4','video'],['docx','document'],['zip','archive'],['webp','image']];
  const items=Array.from({length:2000},(_,i)=>{
   const folder=i<8,[ext,kind]=types[i%types.length],name=folder?folders[i]:`${String(i).padStart(4,'0')} Collector artwork with long descriptive title.${ext}`;
   return {id:'id:'+i,path:'/Synthetic/'+name,desktop_relative_path:name,name,tag:folder?'folder':'file',kind:folder?'folder':kind,extension:folder?'':ext,type:folder?'File folder':kind,revision:'r1',size_label:'35 MB',modified_label:'14 Oct 2026, 10:00 AM'};
  });
  const report={environment:'Synthetic 2000-item folder; actual Chrome. No provider network.',layouts:{before:[],after:[]},render:{before:[],after:[]}},pages={};
  for(const label of ['before','after']){
   const context=await browser.newContext({viewport:{width:1280,height:800}}),page=await context.newPage();pages[label]=page;
   await context.route('**/*',route=>{
    const u=new URL(route.request().url());if(u.hostname!=='compact.synthetic.test')return route.abort();
    if(u.pathname==='/files-window')return route.fulfill({contentType:'text/html',body:sources[label]});
    if(u.pathname==='/api/files-list')return route.fulfill({json:{root_path:'/Synthetic',root_name:'Files',current_path:u.searchParams.get('path')||'/Synthetic',cache_namespace:'synthetic',items,has_more:false}});
    return route.fulfill({status:404,body:''});
   });
   await page.goto('http://compact.synthetic.test/files-window');await page.waitForFunction(()=>state.items.length===2000);
   for(const width of [320,375,768,1024,1280,1440,1920]){
    await page.setViewportSize({width,height:800});await page.waitForTimeout(100);
    await page.evaluate(()=>{elements.results.scrollTop=0;setView('medium');});
    const layout=await page.evaluate(()=>{
     const rows=[...elements.items.querySelectorAll('.file-item')],r=rows[0].getBoundingClientRect();
     return {width:innerWidth,columns:state.virtual.columns,icon:rows[0].querySelector('.file-icon').getBoundingClientRect().width,cell:r.height,gap:state.virtual.gapX,rows:rows.length,scrollWidth:elements.results.scrollWidth,clientWidth:elements.results.clientWidth,bodyWidth:document.body.scrollWidth,
      overlap:rows.some((row,i)=>i&&row.getBoundingClientRect().top===rows[i-1].getBoundingClientRect().top&&row.getBoundingClientRect().left<rows[i-1].getBoundingClientRect().right-0.5),
      namesClamped:rows.every(row=>row.querySelector('.item-name').getBoundingClientRect().height<=34)};
    });
    report.layouts[label].push(layout);
    if(label==='after'){
     assert(layout.icon<=48);assert(!layout.overlap);assert(layout.namesClamped);assert(layout.scrollWidth<=layout.clientWidth+1);assert(layout.bodyWidth<=width);
     if(width===1280)assert(layout.columns>=8&&layout.columns<=10);
     for(const view of ['large','small','list','details']){
      await page.evaluate(view=>setView(view),view);
      assert(await page.evaluate(()=>elements.results.scrollWidth<=elements.results.clientWidth+1),`${width} ${view} overflows`);
      const clipped=await page.evaluate(()=>[...elements.items.children].some(row=>row.scrollWidth>row.clientWidth+1));
      assert(!clipped,`${width} ${view} clipped`);
     }
     await page.evaluate(()=>setView('medium'));
    }
    await page.screenshot({path:`${output}/${label}-${width}.png`});
   }
  }
  for(const page of Object.values(pages))await page.setViewportSize({width:1280,height:800});
  for(let i=0;i<20;i++)for(const label of i%2?['after','before']:['before','after']) report.render[label].push(await pages[label].evaluate(()=>{const start=performance.now();renderItems();return performance.now()-start;}));
  const page=pages.after;
  await page.locator('.file-item').first().click();assert.equal(await page.locator('.file-item.selected').count(),1);
  await page.locator('.file-item').first().press('ArrowDown');assert.equal(await page.evaluate(()=>[...state.selection][0]),await page.evaluate(()=>visibleItems()[state.virtual.columns].path));
  await page.keyboard.press('Shift+ArrowRight');assert.equal(await page.locator('.file-item.selected').count(),2);
  await page.locator('.file-item').first().click({button:'right'});await page.locator('#menu').waitFor({state:'visible'});await page.keyboard.press('Escape');
  assert(await page.locator('#viewButton').getAttribute('aria-label')==='View');
  await page.evaluate(()=>setView('large'));await page.reload();await page.waitForFunction(()=>state.items.length===2000);assert.equal(await page.evaluate(()=>state.view),'large');
  await page.evaluate(()=>{setView('medium');elements.results.scrollTop=16000;renderVirtualRows();});
  assert(await page.locator('.file-item').count()<200);
  const frames=await page.evaluate(async()=>{const values=[];let last=performance.now();for(let i=0;i<60;i++){await new Promise(requestAnimationFrame);elements.results.scrollTop+=40;renderVirtualRows();const now=performance.now();values.push(now-last);last=now;}return values.sort((a,b)=>a-b);});
  report.scroll={p50:frames[30],p95:frames[56]};
  await page.evaluate(()=>{state.items=state.items.slice(0,20);elements.results.scrollTop=0;renderItems();});
  assert.equal(await page.evaluate(()=>state.virtual),null);
  assert(await page.locator('.item-name').evaluateAll(nodes=>nodes.every(n=>n.title===n.textContent&&n.getBoundingClientRect().height<=34)));
  assert.equal(await page.locator('.file-item').count(),20);
  await page.locator('.file-item').first().click();await page.screenshot({path:`${output}/selection-1280.png`});
  for(const label of ['before','after']){const values=[...report.render[label]].sort((a,b)=>a-b);report[label]={renderP50:values[10],renderP95:values[18]};}
  // Coarse touch and device scaling use the same layout, with usable tap targets.
  const mobile=await browser.newContext({viewport:{width:375,height:812},deviceScaleFactor:3,isMobile:true,hasTouch:true});const touch=await mobile.newPage();
  await touch.route('**/*',route=>{const path=new URL(route.request().url()).pathname;return route.fulfill(path==='/files-window'?{contentType:'text/html',body:sources.after}:{json:{root_path:'/Synthetic',current_path:'/Synthetic',items,has_more:false}});});
  await touch.goto('http://compact.synthetic.test/files-window');await touch.waitForFunction(()=>state.items.length===2000);
  assert(await touch.locator('#viewButton').evaluate(e=>e.getBoundingClientRect().height>=44));
  await touch.screenshot({path:`${output}/touch-375-dpr3.png`});
  fs.writeFileSync(`${output}/measurements.json`,JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
