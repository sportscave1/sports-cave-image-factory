// Actual editor widgets, autosave and preview; offline fixture only.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
const port=process.env.SMART_UI_PORT||'18736';
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const open=async page=>{
  await page.getByRole('button',{name:'Reopen saved editor fixture',exact:true}).waitFor();
  await page.getByRole('link',{name:'Open Catalogue fixture',exact:true}).click();
  await page.getByRole('tab',{name:'Editor',exact:true}).click();
 };
 try{
  for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:1100}});
   await page.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
   await page.goto(`http://127.0.0.1:${port}`);
   await open(page);
   const frame=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
   await frame.locator('.catalogue button.title').click();
   const smart=frame.getByRole('checkbox',{name:'Smart recommendations'});
   if(await smart.isChecked())await smart.uncheck();
   await frame.getByRole('button',{name:'Select products',exact:false}).click();
   const dialog=page.getByRole('dialog');
   const checkbox=dialog.getByRole('checkbox',{name:'Select Artwork 2',exact:true});
   if(!await checkbox.isChecked())await dialog.locator('label').filter({has:page.getByRole('checkbox',{name:'Select Artwork 2',exact:true})}).click();
   await dialog.getByRole('button',{name:'Add selected',exact:true}).click();
   await frame.locator('.catalogue .product-info').filter({hasText:'Artwork 2'}).waitFor();
   await smart.check();
   await page.getByRole('button',{name:'Preview customer',exact:false}).waitFor();
   await page.getByRole('button',{name:'Preview customer',exact:false}).click();
   await page.getByRole('combobox',{name:/Customer$/}).click();
   await page.getByRole('option',{name:'Fixture Alice',exact:true}).click();
   await page.getByText('Email Preview',{exact:true}).click();
   const preview=()=>page.frames().find(f=>f.url()==='about:srcdoc'||f.url().startsWith(`http://127.0.0.1:${port}/media/`));
   await page.waitForFunction(()=>document.querySelector('.sc-email-size')?.textContent.includes('SAFE'));
   await page.waitForTimeout(900);
   if(!preview()){console.log(page.frames().map(f=>f.url()));console.log(await page.locator('body').innerText());throw Error('Preview iframe missing');}
   assert.match(await preview().locator('body').innerText(),/Artwork 2/);
   assert.match(await preview().locator('body').innerText(),/Artwork 4/);
   const quantity=frame.getByRole('combobox',{name:'Smart product quantity',exact:true});
   assert.equal(await quantity.inputValue(),'4');
   const row=await frame.locator('.smart-row').boundingBox();const selector=await quantity.boundingBox();
   assert.ok(selector.width<=60&&selector.y>=row.y&&selector.y+selector.height<=row.y+row.height+1);
   for(const count of [1,4,8,12]){
    await quantity.selectOption(String(count));
    await page.waitForFunction(n=>[...window.scEmailDrafts.values()].some(s=>Object.values(s.model?.resolved||{}).some(r=>r.section?.settings?.smart_count===n&&r.products?.length===n)),count);
    await page.waitForTimeout(250);
    const rendered=(await preview().locator('body').innerText()).match(/Artwork \d+/g)||[];
    assert.equal(new Set(rendered).size,count);
   }
   await page.reload();await page.getByRole('tab',{name:'Editor',exact:true}).click();
   await frame.locator('.catalogue button.title').click();assert.equal(await quantity.inputValue(),'12');
   await quantity.selectOption('4');

   await page.getByRole('button',{name:'Preview customer',exact:false}).click();
   await page.getByRole('combobox',{name:/Customer$/}).click();
   await page.getByRole('option',{name:'Fixture Bob',exact:true}).click();
   await page.getByText('Email Preview',{exact:true}).click();await page.waitForTimeout(900);
   await page.waitForFunction(()=>[...document.querySelectorAll('iframe')].some(f=>f.contentDocument?.body?.textContent.includes('Artwork 9')));
   const bob=await preview().locator('body').innerText();
   assert.match(bob,/Artwork 9/);assert.doesNotMatch(bob,/Artwork 2/);
   const size=await page.locator('.sc-email-size').innerText();
   assert.match(size,/SAFE/);assert.equal(await page.getByRole('progressbar').count(),1);
   await page.getByRole('button',{name:'smartphone',exact:true}).click();
   await page.waitForTimeout(400);assert.match(await preview().locator('body').innerText(),/Artwork 9/);
   await page.reload();await page.getByRole('tab',{name:'Editor',exact:true}).click();
   await frame.locator('.catalogue button.title').click();
   assert.equal(await smart.isChecked(),true);
   await smart.uncheck();await page.waitForTimeout(1100);
   assert.match(await preview().locator('body').innerText(),/Artwork 2/);
   assert.doesNotMatch(await preview().locator('body').innerText(),/Artwork 9/);
   const html=frame.locator('textarea').first(),original=await html.inputValue();
   await html.fill('<p>'+('x'.repeat(80*1024))+'</p>');await html.press('Tab');
   await page.waitForFunction(()=>document.querySelector('.sc-email-size')?.textContent.includes('NEAR LIMIT'));
   await html.fill('<p>'+('x'.repeat(96*1024))+'</p>');await html.press('Tab');
   await page.waitForFunction(()=>document.querySelector('.sc-email-size')?.textContent.includes('TOO LARGE'));
   await html.fill(original);await html.press('Tab');
   await page.waitForFunction(()=>document.querySelector('.sc-email-size')?.textContent.includes('SAFE'));
   assert.equal(await page.locator('[data-testid="stException"]').count(),0);
   await page.screenshot({path:`.tmp-preview-performance/smart-editor-${width}.png`,fullPage:true});
   console.log(JSON.stringify({width,manual:true,smart:true,recipientSwitch:true,reopen:true,size}));
   await page.close();
  }
  const fallback=await browser.newPage({viewport:{width:1440,height:1100}});
  await fallback.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
  await fallback.goto(`http://127.0.0.1:${port}/?offline=1`);
  await open(fallback);
  const composer=fallback.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
  await composer.locator('.catalogue button.title').click();
  await composer.getByRole('checkbox',{name:'Smart recommendations'}).check();
  await fallback.waitForFunction(()=>[...window.scEmailDrafts.values()].some(s=>Object.values(s.model?.resolved||{}).some(r=>r.section?.settings?.smart&&r.products?.length===0)));
  assert.equal(await fallback.locator('[data-testid="stException"]').count(),0);
  console.log(JSON.stringify({apiFailureHidesSection:true,unrelatedFallback:false}));
  await fallback.close();
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
