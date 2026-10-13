const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});try{
for(const kind of ['abandoned','welcome','post_purchase','win_back','fulfilled']){
 const p=await b.newPage({viewport:{width:1440,height:1000}});
 await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await p.goto('http://127.0.0.1:18752/?flow='+kind);
 const summary=p.locator('summary').first();await summary.click();
 const frame=p.locator('iframe').first(),f=p.frameLocator('iframe').first();await frame.waitFor({state:'visible'});
 await f.locator('tbody tr').nth(49).waitFor();
 await f.locator('.wrap').evaluate(e=>e.scrollTop=210);await p.waitForTimeout(250);
 await summary.click();await frame.waitFor({state:'hidden'});await p.waitForTimeout(300);
 await summary.click();await frame.waitFor({state:'visible'});await p.waitForTimeout(400);
 assert.equal(await f.locator('.wrap').evaluate(e=>e.scrollTop),210,kind+' warm scroll');
 const search=p.getByRole('textbox',{name:'Search and filter',exact:true});
 await search.fill('fixture1@example.test');await search.press('Enter');
 await f.getByRole('button',{name:'Details Fixture customer 1',exact:true}).waitFor();
 if(kind!=='abandoned'){
  const sort=p.getByRole('combobox',{name:'Sort',exact:true});await sort.click();await p.getByRole('option',{name:'Oldest',exact:true}).click();
  const status=p.getByRole('combobox',{name:'Status',exact:true});await status.click();await p.getByRole('option',{name:kind==='fulfilled'?'Active':'New',exact:true}).click();
  await p.getByRole('button',{name:/Date filters/}).click();
  for(const [part,value] of [['year','2030'],['month','01'],['day','01']]){
   const segment=p.getByRole('spinbutton',{name:part+', From',exact:true});await segment.click();await segment.pressSequentially(value);
  }
  await p.keyboard.press('Tab');await p.keyboard.press('Escape');
  await f.getByText(/No matching/).waitFor();
  await summary.click();await frame.waitFor({state:'hidden'});await p.waitForTimeout(300);await summary.click();await frame.waitFor({state:'visible'});await p.waitForTimeout(400);
  assert.equal(await search.inputValue(),'fixture1@example.test');
  assert.match(await sort.evaluate(e=>e.value??e.textContent),/Oldest/);
  await f.getByText(/No matching/).waitFor();
 }
 await p.setViewportSize({width:390,height:900});await p.waitForTimeout(300);
 assert.equal(await p.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.equal(await p.getByTestId('stException').count(),0);
 console.log('PASS warm scroll, retained controls, narrow layout: '+kind);await p.close();
}
for(const kind of ['abandoned','welcome','post_purchase','win_back','fulfilled']){
 const p=await b.newPage();await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await p.goto('http://127.0.0.1:18752/?flow='+kind+'&fail=1');await p.locator('summary').first().click();
 await p.getByRole('button',{name:'Retry recipients',exact:true}).waitFor();
 assert.equal(await p.getByTestId('stException').count(),0);
 await p.getByRole('button',{name:'Restore fixture reads',exact:true}).click();
 await p.getByRole('button',{name:'Retry recipients',exact:true}).click();
 await p.frameLocator('iframe').first().locator('tbody tr').first().waitFor();
 console.log('PASS failed initial read and explicit recovery: '+kind);await p.close();
}
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
