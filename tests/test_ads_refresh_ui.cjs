// Real local Streamlit renderer; all provider work is mocked in refresh_ui.py.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const label=process.env.REFRESH_BROWSER_LABEL||'after';
(async()=>{const browser=await chromium.launch({...(process.platform==='win32'?{channel:'msedge'}:{}),headless:true});
try{
 const context=await browser.newContext({permissions:['clipboard-read','clipboard-write']});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const metrics={};
 for(const kind of ['Instant Experience','Carousel']){
  const page=await context.newPage();page.setDefaultTimeout(20000);
  await page.setViewportSize({width:1366,height:900});
  const began=Date.now();await page.goto('http://127.0.0.1:8557/?format='+encodeURIComponent(kind));
  const saveButton=page.locator('[class*="st-key-ads-images-save-open"] button');
  try {await saveButton.waitFor();}
  catch(error){console.log((await page.locator('body').innerText()).slice(-12000));await page.screenshot({path:'tmp/refresh-browser-error.png',fullPage:true});throw error;}
  await page.waitForTimeout(500);
  assert.equal(await page.getByTestId('stException').count(),0);
  const loadedMs=Date.now()-began;
  metrics[kind]={loadedMs,viewports:{}};
  for(const width of [1366,1024,750,390]){
   await page.setViewportSize({width,height:900});await page.waitForTimeout(150);
   const sizes=await page.evaluate(()=>{
    const main=document.querySelector('[data-testid="stMain"]');
    const body=document.querySelector('[data-testid="stMainBlockContainer"]');
    return {height:main.scrollHeight,overflow:body.scrollWidth>body.clientWidth+2,headingY:document.querySelector('h1').getBoundingClientRect().y,
     coverPanels:[...document.querySelectorAll('[class*="st-key-ads-ie-concept-"]')].filter(e=>!e.className.includes('copy-field')).map(e=>{const b=e.getBoundingClientRect();return {x:b.x,y:b.y,width:b.width};})};
   });
   metrics[kind].viewports[width]=sizes;
   if(label==='after')assert.equal(sizes.overflow,false,kind+' overflow at '+width);
   if(label==='after'&&kind==='Instant Experience'){
    assert.equal(sizes.coverPanels.length,3);
    if(width===1366)assert.equal(new Set(sizes.coverPanels.map(p=>p.y)).size,1,'Three covers together');
    else assert.equal(new Set(sizes.coverPanels.map(p=>p.x)).size,1,'Narrow layouts stack');
    assert.ok(sizes.headingY>=60,'Heading clears Streamlit header');
   }
   await page.screenshot({path:`tmp/refresh-${label}-${kind==='Carousel'?'carousel':'ie'}-${width}.png`,fullPage:true});
   if(label==='after'&&kind==='Instant Experience'){
    const grid=page.locator('.st-key-ads-refresh-ie-grid');
    await grid.scrollIntoViewIfNeeded();
    await page.screenshot({path:`tmp/refresh-after-ie-outputs-${width}.png`});
    await page.getByTestId('stMain').evaluate(e=>e.scrollTo(0,0));
   }
  }
  if(label==='after'){
   await page.setViewportSize({width:1366,height:900});
   let copyFrame;
   for(const frame of page.frames())if(await frame.getByRole('button',{name:'Copy Prompt',exact:true}).count()){copyFrame=frame;break;}
   assert.ok(copyFrame,'Master Copy Prompt present');
   await copyFrame.getByRole('button',{name:'Copy Prompt',exact:true}).click();
   await copyFrame.locator('[role="status"]').filter({hasText:'Prompt copied'}).waitFor();
   const copied=await page.evaluate(()=>navigator.clipboard.readText());
   const expected=JSON.parse(fs.readFileSync('tmp/refresh-expected-prompts.json','utf8'))[kind];
   assert.equal(copied.replace(/\r\n/g,'\n'),expected.replace(/\r\n/g,'\n'),'Complete prompt copied exactly');
   assert.ok(copied.includes(kind==='Carousel'?'TRUE WINNER CAROUSEL REFRESH':'INSTANT EXPERIENCE WINNER REFINEMENT'));
   assert.ok(copied.includes('Legends Never Die'));
   if(kind==='Instant Experience'){
    await page.locator('[class*="st-key-ads-ie-concept-"]:not([class*="copy-field"]) input[type="file"]').first().setInputFiles('tmp/refresh-test-upload.png');
    await page.getByText(/refresh-test-upload.png · 1024/).waitFor();
    metrics[kind].uploadAndPreview=true;
   }else{
    await page.getByRole('button',{name:/^(?:table_view )?CSV$/}).click();
    await page.locator('[class*="st-key-ads-carousel-copy-csv-import"] input[type="file"]').setInputFiles('tmp/refresh-test-copy.csv');
    await page.getByRole('textbox',{name:'Card 1 headline',exact:true}).waitFor();
    await page.waitForFunction(()=>[...document.querySelectorAll('input')].some(e=>e.value==='Local CSV Review'));
    await page.keyboard.press('Escape');
    await page.waitForFunction(()=>document.querySelector('[class*="st-key-ads-images-save-open"] button')?.disabled===true);
    await page.getByRole('button',{name:/^(?:table_view )?CSV$/}).click();
    await page.locator('[class*="st-key-ads-carousel-copy-csv-import"] input[type="file"]').setInputFiles('tmp/refresh-test-copy-valid.csv');
    await page.waitForFunction(()=>[...document.querySelectorAll('input')].some(e=>e.value==='The Rivalry'));
    await page.keyboard.press('Escape');metrics[kind].csvImport=true;
   }
   const start=Date.now();await saveButton.click();
   await page.getByRole('button',{name:kind==='Carousel'?'Save 5 images here':'Save Instant Experience Package here',exact:true}).click();
   assert.equal(await page.getByRole('button',{name:'POST NOW',exact:true}).count(),0,'Save succeeds before visual sign-off');
   await page.getByText('Final visual verification — required before POST NOW',{exact:true}).click();
   await page.getByText('I checked every refreshed image against its product and winner references',{exact:true}).click();
   await page.getByRole('button',{name:'POST NOW',exact:true}).waitFor();metrics[kind].mockSaveMs=Date.now()-start;
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.getByRole('button',{name:'POST NOW',exact:true}).click();
   await page.getByText('Posting handoff ready',{exact:true}).waitFor();
   await page.getByText(kind==='Carousel'?'5 saved assets':'3 saved assets',{exact:true}).waitFor();
   metrics[kind].copyAndSaveAndPost=true;
  }
  await page.close();
 }
 fs.writeFileSync(`tmp/refresh-browser-${label}.json`,JSON.stringify(metrics,null,2));console.log(JSON.stringify(metrics));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1);});
