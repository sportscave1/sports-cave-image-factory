const {chromium}=require('playwright');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{
  const page=await browser.newPage();let external=0;
  await page.route('**/*',r=>{if(new URL(r.request().url()).hostname==='127.0.0.1')r.continue();else{external++;r.abort()}});
  const start=Date.now();await page.goto('http://127.0.0.1:8534/?case=Existing');
  await page.locator('.sc-auto-name').filter({hasText:'Reminder 1'}).waitFor();const rowMs=Date.now()-start;
  await page.waitForFunction(()=>!document.querySelector('.sc-home-unresolved')&&!document.body.innerText.includes('Loading recent activity…'));
  async function sample(){await page.getByRole('button',{name:'Fixture sample counters',exact:true}).click();await page.waitForTimeout(200);return JSON.parse(await page.locator('#fixture-counters').innerText())}
  const before=await sample();assert.equal(before.pending,0);
  await page.waitForTimeout(60000);const after=await sample();
  assert.equal(after.queries,before.queries,'Background query loop while settled');assert.equal(after.pending,0);assert.equal(after.futures,before.futures);
  for(let i=0;i<10;i++){
   await page.getByRole('button',{name:'Fixture leave Automations',exact:true}).click();await page.getByRole('heading',{name:'Lightweight fixture page',exact:true}).waitFor();
   await page.getByRole('button',{name:'Fixture return Automations',exact:true}).click();await page.locator('.sc-auto-name').filter({hasText:'Reminder 1'}).waitFor();
  }
  const final=await sample();assert.ok(final.futures<=8);assert.equal(final.pending,0);assert.equal(external,0);
  console.log(JSON.stringify({freshProcessRowMs:rowMs,before,idle60:after,after10Navigation:final,externalRequests:external}));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
