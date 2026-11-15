// Real final email and unsaved editor layout, offline synthetic image responses only.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const data=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
 const browser=await chromium.launch({channel:'chrome',headless:true});let checks=0;
 try{
  const page=await browser.newPage();
  await page.route('**/*',route=>{
   const portrait=route.request().url().includes('fixture-1');
   if(route.request().resourceType()==='image')return route.fulfill({contentType:'image/svg+xml',body:`<svg xmlns="http://www.w3.org/2000/svg" width="600" height="${portrait?800:400}"><rect width="100%" height="100%" fill="#bfa572"/></svg>`});
   return route.abort();
  });
  for(const width of [280,320,375,390,768,1440])for(const sample of data.cases)for(const source of ['email','manual-preview','smart-preview','no-head-css']){
   await page.setViewportSize({width,height:1000});
   if(source==='email'||source==='no-head-css')await page.setContent(source==='email'?sample.html:sample.html.replace(/<style>[\s\S]*?<\/style>/g,''));
   else{
    await page.setContent('<body style="margin:0"><div id="fixture" style="max-width:600px"></div>');
    await page.addScriptTag({content:fs.readFileSync('components/crm_sections/preview.js','utf8')});
    await page.evaluate(({sample,data,source})=>{
     const s=structuredClone(sample.section),model={resolved:{},tags:data.tags,css:data.css};
     if(source==='smart-preview'){s.settings.smart=true;s.settings.smart_count=s.products.length;model.resolved[s.id]={section:{settings:{smart:true}},products:s.products};}
     document.querySelector('#fixture').innerHTML=SCPreview.sectionHtml(s,model);
    },{sample,data,source});
   }
   await page.evaluate(()=>Promise.all([...document.images].map(i=>i.decode().catch(()=>{}))));
   const result=await page.evaluate(()=>{
    const pairs=[...document.querySelectorAll('table')].filter(t=>t.rows.length>1&&t.rows[0].cells.length===2&&t.rows[0].cells[0].getAttribute('width')==='50%');
    const rect=n=>{const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
    return {overflow:document.documentElement.scrollWidth>innerWidth,pairs:pairs.map(t=>[...t.rows].map(row=>[...row.cells].map(c=>({rect:rect(c),child:c.firstElementChild?rect(c.firstElementChild):null,text:c.textContent,button:c.querySelector(':scope > table a, :scope > table span')?rect(c.querySelector(':scope > table a, :scope > table span')):null})))),images:[...document.images].filter(i=>i.src.includes('fixture-')).map(i=>({r:rect(i),ratio:i.naturalWidth/i.naturalHeight})),titles:document.body.textContent};
   });
   const label=`${width}/${sample.name}/${source}`;
   assert(!result.overflow,`overflow ${label}`);
   assert.equal(result.pairs.length,Math.ceil(sample.section.products.length/2),label);
   for(const pair of result.pairs)for(const cells of pair){
    assert(Math.abs(cells[0].rect.y-cells[1].rect.y)<1,`row y ${label}`);
    assert(Math.abs(cells[0].rect.h-cells[1].rect.h)<1,`row height ${label}`);
    if(cells.every(c=>c.child)){
     assert(Math.abs(cells[0].child.y-cells[1].child.y)<1,`field top ${label}`);
     assert(Math.abs(cells[0].rect.w-cells[1].rect.w)<1,`width ${label}`);
     if(cells.every(c=>c.button)){
      assert(Math.abs(cells[0].button.h-cells[1].button.h)<1,`CTA height ${label}`);
      assert(Math.abs(cells[0].button.w-cells[1].button.w)<1,`CTA width ${label}`);
      assert(cells[0].button.h>=42,`CTA target ${label}`);
     }
    }
   }
   if(sample.name==='4'){
    const titleRow=sample.section.settings.display.image?1:0;
    assert(result.pairs[0][titleRow][0].rect.h>result.pairs[1][titleRow][0].rect.h,`independent title heights ${label}`);
   }
   for(const i of result.images)assert(Math.abs(i.r.w/i.r.h-i.ratio)<0.02,`aspect ${label}`);
   for(const p of sample.section.products)assert(result.titles.includes(p.title),`full title ${label}`);
   if(sample.name==='4'&&width===390&&source==='email')await page.screenshot({path:process.argv[3],fullPage:true});
   if(sample.name==='4'&&width===1440&&source==='email')await page.screenshot({path:process.argv[3].replace('.png','-desktop.png'),fullPage:true});
   checks++;
  }
  console.log(JSON.stringify({passed:checks,widths:[280,320,375,390,768,1440],sources:['final email','manual preview','smart preview','no head CSS'],counts:'1-12',edgeCases:['mixed aspect ratios','long titles','missing edition fields','display toggles','unbroken titles','long custom CTA']},null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
