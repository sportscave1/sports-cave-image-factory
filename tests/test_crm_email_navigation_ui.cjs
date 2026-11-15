// Real shared composer and offline fixture servers; every external request blocked.
const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try{
  for(const kind of ['campaign','automation'])for(const width of [1440,390]){
   const page=await browser.newPage({viewport:{width,height:950}});page.setDefaultTimeout(20000);
   await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
   if(kind==='campaign'){
    await page.goto(`http://127.0.0.1:${process.env.CAMPAIGN_UI_PORT||18776}`);
    await page.getByRole('link',{name:'Open Catalogue fixture',exact:true}).click();
   }else{
    await page.goto(`http://127.0.0.1:${process.env.AUTOMATION_UI_PORT||18777}/?fixture_checkout=1&fixture_run=nav-${width}-${Date.now()}`);
    await page.getByRole('button',{name:/Edit Email/}).first().click();
   }
   const tab=name=>page.getByRole('tab',{name,exact:true});
   await tab('Editor').click();
   const frame=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
   const html=frame.locator('textarea').first();await html.waitFor();
   const source='<p style="color:#123456">Hello {{first_name}}, preview check.</p><a href="https://example.com/art">Explore</a>';
   await html.fill(source);await html.press('Tab');
   await page.waitForFunction(()=>[...document.querySelectorAll('iframe')].some(f=>f.contentDocument?.body?.textContent.includes('preview check.')));
   assert.ok(!await page.locator('body').innerText().then(t=>t.includes('Unresolved template variable')));
   if(kind==='campaign'){
    for(const name of ['Fixture Alice','Fixture Bob']){
     await page.getByRole('button',{name:'Preview customer',exact:false}).click();
     await page.getByRole('combobox',{name:/Customer$/}).click();
     await page.getByRole('option',{name,exact:true}).click();
     await page.getByText('Email Preview',{exact:true}).click();
     await page.waitForFunction(name=>[...document.querySelectorAll('iframe')].some(f=>f.contentDocument?.body?.textContent.includes('Hello '+name+', preview check.')),name);
    }
   }
   // Create genuine editor overflow through existing section actions.
   for(let i=0;i<3;i++){
    await frame.locator('summary').filter({hasText:'Add section'}).click();
    await frame.getByRole('button',{name:'Add HTML',exact:false}).click();
   }
   const panel=page.locator('.st-key-crm-composer-controls');
   await page.evaluate(()=>{const main=document.querySelector('[data-testid="stMain"]');if(main)main.scrollTop=0;window.scrollTo(0,0)});
   await panel.evaluate(e=>{e.scrollTop=0});
   const style=await tab('Editor').evaluate(e=>({color:getComputedStyle(e.querySelector('p')).color,border:getComputedStyle(e).borderBottomColor,height:e.parentElement.getBoundingClientRect().height,background:getComputedStyle(e.parentElement).backgroundColor}));
   assert.equal(style.background,'rgb(17, 17, 17)');assert.equal(style.color,'rgb(198, 160, 68)');assert.equal(style.border,'rgb(198, 160, 68)');assert.ok(style.height>=48&&style.height<=54);
   const before=await tab('Editor').boundingBox();
   const scroll=await panel.evaluate(e=>{e.scrollTop=350;return {top:e.scrollTop,max:e.scrollHeight-e.clientHeight}});
   assert.ok(scroll.top>50,JSON.stringify(scroll));
   await page.waitForTimeout(100);
   const after=await tab('Editor').boundingBox();
   assert.ok(Math.abs(before.y-after.y)<2,JSON.stringify({before,after,scroll}));
   assert.equal(await tab('Editor').getAttribute('aria-selected'),'true');
   assert.equal(await html.inputValue(),source);
   const overlap=await tab('Editor').evaluate(e=>{const r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))});
   assert.ok(overlap,'sticky navigation must remain on top '+JSON.stringify({kind,width,before,after}));
   await tab('Settings').click();const subject=page.getByRole('textbox',{name:'Subject',exact:true});
   const subjectText='Navigation draft '+width;await subject.fill(subjectText);await subject.press('Tab');
   await tab('Templates').click();await tab('Editor').click();assert.equal(await html.inputValue(),source);
   await tab('Settings').click();assert.equal(await subject.inputValue(),subjectText);
   await tab('Settings').focus();await page.keyboard.press('ArrowRight');
   await page.waitForFunction(()=>document.activeElement?.getAttribute('role')==='tab'&&document.activeElement.textContent==='Editor');
   await page.keyboard.press('Enter');await html.waitFor();
   await page.waitForFunction(()=>!document.querySelector('.st-key-crm-composer-controls [data-stale="true"]'));
   assert.equal(await html.inputValue(),source);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.screenshot({path:`.tmp-preview-performance/email-navigation-${kind}-${width}.png`});
   console.log(JSON.stringify({kind,width,sticky:true,draftPreserved:true,keyboard:true,personalised:true,overflow:false,height:style.height}));
   await page.close();
  }
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exit(1)});
