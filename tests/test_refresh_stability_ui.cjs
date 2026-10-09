// Real local Streamlit UI with background fragment ticks and mocked archives.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const metrics=[];
for(const channel of ['chrome','msedge']){
 const browser=await chromium.launch({channel,headless:true});
 try{for(const count of [4,5,6]){
  const context=await browser.newContext({viewport:{width:1024,height:950}});
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const page=await context.newPage();page.setDefaultTimeout(15000);
  let began=Date.now();await page.goto(`http://127.0.0.1:${process.env.REFRESH_UI_PORT||8557}/?format=Carousel&count=${count}&stress=1`);
  const field=page.getByRole('textbox',{name:'Card 1 headline',exact:true});await field.waitFor();
  const openingMs=Date.now()-began;const text=`Retained ${channel} ${count}`;await field.fill(text);await field.press('Tab');
  const timings=[];
  const heapBefore=await page.evaluate(()=>performance.memory?.usedJSHeapSize||null);
  for(let i=0;i<60;i++){
   let strip;for(const frame of page.frames())if(await frame.locator('.strip').count()){strip=frame.locator('.strip');break;}
   assert.ok(strip);const start=Date.now();await strip.press(i%2?'ArrowLeft':'ArrowRight');timings.push(Date.now()-start);
   if(i%3===0){await page.getByRole('button',{name:'Replay winner handoff',exact:true}).click();await field.waitFor();}
   assert.equal(await field.inputValue(),text);
  }
  await page.getByRole('button',{name:'Fail source media',exact:true}).click();
  await page.getByRole('button',{name:'Retry source images',exact:true}).waitFor();
  assert.equal(await field.inputValue(),text);
  await page.getByRole('button',{name:'Restore source media',exact:true}).click();
  await field.waitFor();assert.equal(await field.inputValue(),text);
  await page.waitForTimeout(15000);assert.equal(await field.inputValue(),text);
  await page.getByRole('button',{name:'Replay winner handoff',exact:true}).click();await field.waitFor();
  await page.getByText('Archive reads: '+count*3,{exact:true}).waitFor();
  const reads=Number((await page.getByText(/^Archive reads:/).innerText()).split(': ')[1]);assert.equal(reads,count*3);
  const ticks=(await page.getByText(/^Background ticks:/).innerText()).split(': ')[1];assert.ok(Number(ticks)>5);
  assert.equal(await page.getByTestId('stException').count(),0);
  metrics.push({channel,count,openingMs,cardActionMedianMs:timings.sort((a,b)=>a-b)[30],ticks:Number(ticks),archiveReads:reads,actions:60,heapBefore,heapAfter:await page.evaluate(()=>performance.memory?.usedJSHeapSize||null)});
  await context.close();
 }}finally{await browser.close();}
}
fs.writeFileSync('tmp/refresh-stability-browser.json',JSON.stringify(metrics,null,2));console.log(JSON.stringify(metrics));
})().catch(e=>{console.error(e);process.exitCode=1;});
