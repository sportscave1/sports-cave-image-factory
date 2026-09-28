// Synthetic local fixture only. Delivery is mocked in the fixture; no real email.
const {chromium}=require('playwright');
const fs=require('node:fs');const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:900},permissions:['clipboard-read','clipboard-write']});
 await context.route('**/*',route=>{
  const url=new URL(route.request().url());
  if(['127.0.0.1','localhost'].includes(url.hostname))return route.continue();
  if(url.hostname==='cdn.shopify.com')return route.fulfill({contentType:'image/svg+xml',body:'<svg xmlns="http://www.w3.org/2000/svg" width="800" height="600"><rect width="800" height="600" fill="#f0eade"/><rect x="145" y="55" width="510" height="490" fill="#202020"/><rect x="165" y="75" width="470" height="450" fill="#c6a05b"/><text x="400" y="270" text-anchor="middle" font-family="Arial" font-size="44" fill="#161616">COLLECTOR ART</text><text x="400" y="325" text-anchor="middle" font-family="Arial" font-size="24" fill="#161616">SYNTHETIC TEST FIXTURE</text></svg>'});
  return route.abort();
 });
 const page=await context.newPage();page.setDefaultTimeout(15000);
 const out='output/campaigns-first';fs.mkdirSync(out,{recursive:true});
 const button=name=>page.getByRole('button',{name,exact:true});
 async function settle(){await page.waitForTimeout(350);await page.waitForFunction(()=>document.querySelector('[data-testid=stApp]')?.getAttribute('data-test-script-state')!=='running');}
 async function click(name){await button(name).click();await settle();}
 async function select(label,value){await page.getByTestId('stSelectbox').filter({has:page.getByText(label,{exact:true})}).getByRole('combobox').click();await page.getByRole('option',{name:value.trim(),exact:true}).click();await settle();}
 async function fill(label,value){const input=page.getByRole('textbox',{name:label,exact:true});await input.fill(value);await input.press('Tab');await settle();}
 try{
 await page.goto('http://127.0.0.1:8517');await button('+ New Campaign').waitFor();
 const sidebar=await page.getByTestId('stSidebar').innerText();for(const name of ['Campaigns','Flows','Settings'])assert(sidebar.includes(name));
 await page.getByText('Settings',{exact:true}).click();await select('CRM Settings','Connections & Tracking');
 await click('Check Shopify connection and read scopes');await page.getByText(/^Reported scopes:/).waitFor();
 await select('CRM Settings','Branding');await select('Email typography','Georgia');await select('Button style','Outlined black');await click('Save branding');
 await select('Email typography','Arial');await select('Button style','Solid black');await click('Save branding');
 await select('CRM Settings','Sending & Compliance');
 await fill('Internal-test allowlist (one email per line)','internal@example.test');await click('Save internal-test settings');
 await page.getByText('Campaigns',{exact:true}).click();await click('+ New Campaign');
 const name='Browser collector draft '+Date.now();await fill('Campaign name',name);await click('Create draft');
 await button('Recalculate eligibility').waitFor();await click('Recalculate eligibility');
 for(let i=0;i<3;i++){await button('Continue calculation').waitFor({state:'visible'});await click('Continue calculation');}
 await page.getByText(/^Complete ·/).waitFor();await page.screenshot({path:out+'/recipients-1440.png'});
 await click('Next →');await fill('Subject','A moment worth collecting');await fill('Preheader','Discover the collector edit');
 await page.getByText('Choose template / starter',{exact:true}).click();await select('Starter layout','New Editions');await click('Use starter');
 await select('Edit block','3 · product_grid · ');await fill('Search Shopify products','Collector');await click('Search products');await click('Select product');
 await select('Edit block','3 · product_grid · ');await fill('Search Shopify products','Collector');await click('Search products');await select('Shopify product','Second collector artwork');await click('Select product');
 await select('Edit block','3 · product_grid · ');await click('Load variants / market price');await click('Use verified market price');
 await select('Edit block','4 · button · Explore the collection');await fill('Button HTTPS URL','https://www.sportscaveshop.com/collections/all');
 await page.getByText('I reviewed facts, offer and subject for accuracy',{exact:true}).click();
 await click('Save draft');await page.getByText('Saved. Your draft is stored in the CRM database.',{exact:true}).waitFor();
 await page.getByText('Choose template / starter',{exact:true}).click();await settle();
 await page.getByText('Prompt factory',{exact:true}).click();await click('Generate Sports Cave Prompt');
 let copied=false;for(const f of page.frames())if(await f.getByRole('button',{name:'Copy Prompt',exact:true}).count()){
  await f.getByRole('button',{name:'Copy Prompt',exact:true}).click();await f.getByRole('button',{name:'Prompt copied',exact:true}).waitFor();copied=true;break;}
 assert(copied);assert((await page.evaluate(()=>navigator.clipboard.readText())).includes('schema_version'));
 await page.getByText('Prompt factory',{exact:true}).click();await page.getByTestId('stMain').evaluate(e=>e.scrollTop=0);
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
 await page.screenshot({path:out+'/message-1440.png'});await page.setViewportSize({width:1920,height:1080});await page.screenshot({path:out+'/message-1920.png'});
 for(const width of [600,375,320,430]){
  await select('Layout width',String(width));
  let frame;for(const f of page.frames())if(f!==page.mainFrame()&&(await f.locator('body').innerText()).includes('production link not activated'))frame=f;
  assert(frame);const metrics=await frame.evaluate(()=>({width:innerWidth,scroll:document.documentElement.scrollWidth}));
  assert.equal(metrics.width,width);assert(metrics.scroll<=width+1);await (await frame.frameElement()).screenshot({path:out+'/email-'+width+'.png'});
  const complete=await context.newPage();await complete.setViewportSize({width,height:900});
  await complete.setContent(await frame.content());await complete.locator('img').evaluateAll(async images=>{await Promise.all(images.map(i=>i.decode().catch(()=>{})));});
  assert(await complete.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  assert((await complete.locator('body').innerText()).includes('Unsubscribe'));
  await complete.screenshot({path:out+'/email-full-'+width+'.png',fullPage:true});await complete.close();
 }
 await select('Preview mode','Images off');await select('Preview mode','Plain text');await select('Preview mode','Images on');
 await click('Save draft');await click('Campaign list');await button('+ New Campaign').waitFor();
 await fill('Search campaigns',name);await click('Open');await click('Next →');assert.equal(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),'A moment worth collecting');
 // Full browser reload must recover the persisted draft from the campaign list.
 await page.reload();await button('+ New Campaign').waitFor();await fill('Search campaigns',name);await click('Open');await click('Next →');
 assert.equal(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),'A moment worth collecting');
 await click('Preview');assert.equal(await button('Send campaign').count(),0);
 assert.equal(await page.getByRole('textbox',{name:'Manual internal test recipient',exact:true}).inputValue(),'');
 await page.getByTestId('stMain').evaluate(e=>e.scrollTop=0);await page.screenshot({path:out+'/review-1920.png'});await page.setViewportSize({width:1440,height:900});await page.screenshot({path:out+'/review-1440.png'});
 await fill('Manual internal test recipient','internal@example.test');await page.getByText('I confirm one internal mailbox and the TEST ONLY footer / inactive unsubscribe warnings.',{exact:true}).click();
 await click('Send internal test');await page.getByText('Test accepted by Resend',{exact:true}).waitFor();
 assert.equal(await page.getByTestId('stException').count(),0);
 fs.writeFileSync(out+'/verification.json',JSON.stringify({viewports:['1440x900','1920x1080'],emailWidths:[600,375,320,430],navigation:true,creation:true,audienceCalculation:true,templates:true,productPicker:true,marketPrice:true,editing:true,persistenceAndReload:true,promptCopy:true,connectionScopes:true,brandingPresets:true,mockedInternalTest:true,noRealEmail:true,noLiveCampaignAction:true},null,2));
 console.log('Campaigns-first browser flow passed; screenshots at '+out);
 }catch(error){await page.screenshot({path:out+'/failure.png'});console.error((await page.locator('body').innerText()).slice(-10000));throw error;}finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
