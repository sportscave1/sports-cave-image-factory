// Local synthetic UI only. Never runs against a production URL or clicks Send Test.
const {chromium}=require('playwright');
const fs=require('node:fs');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:900},permissions:['clipboard-read','clipboard-write']});
 await context.route('**/*',route=>{
   const url=new URL(route.request().url());
   return ['127.0.0.1','localhost'].includes(url.hostname)?route.continue():route.abort();
 });
 const page=await context.newPage();
 const out='output/campaigns-v1';fs.mkdirSync(out,{recursive:true});
 try {
 await page.goto('http://127.0.0.1:8517');
 await page.getByRole('button',{name:'+ New Campaign',exact:true}).click();
 await page.getByRole('textbox',{name:'Campaign name',exact:true}).fill('Browser verified collector draft');
 await page.getByRole('button',{name:'Save campaign',exact:true}).click();
 await page.getByText('Campaign saved. Changes invalidate the previous test approval.',{exact:true}).waitFor();
 await page.getByText('2 · Audience',{exact:true}).click();
 await page.getByRole('button',{name:'Recalculate eligibility',exact:true}).click();
 await page.getByRole('button',{name:'Continue calculation',exact:true}).click();
 await page.getByText(/^Complete ·/).waitFor();
 await page.screenshot({path:out+'/audience-1440.png'});
 await page.getByText('3 · Email creator',{exact:true}).click();
 for (const [name,value] of [['Subject','A moment worth collecting'],['Preheader','Discover Sports Cave collector art'],['Headline','For the moments that stay with you'],['Body copy','Explore the latest Sports Cave collection. Art for the moments you remember.'],['CTA label','Explore the collection'],['CTA URL','https://www.sportscaveshop.com']]) {
   await page.getByRole('textbox',{name,exact:true}).fill(value);
 }
 await page.getByText('I reviewed facts, subject, offer and urgency for accuracy.',{exact:true}).click();
 await page.getByRole('button',{name:'Generate Sports Cave Prompt',exact:true}).click();
 await page.waitForFunction(()=>Array.from(document.querySelectorAll('iframe')).some(f=>f.contentDocument?.getElementById('copy')));
 const frames=page.frames();let copied=false;
 for(const f of frames){if(await f.getByRole('button',{name:'Copy Prompt',exact:true}).count()){
   await f.getByRole('button',{name:'Copy Prompt',exact:true}).click();
   await f.getByRole('button',{name:'Prompt copied',exact:true}).waitFor();copied=true;break;
 }}
 assert(copied,'Copy Prompt must work');
 const clipboard=await page.evaluate(()=>navigator.clipboard.readText());
 assert(clipboard.includes('SPORTS CAVE — LOCKED CAMPAIGN COPY BRIEF'));
 await page.screenshot({path:out+'/creator-1440.png'});
 await page.getByRole('button',{name:'Save campaign',exact:true}).click();
 await page.getByText('4 · Preview + test',{exact:true}).click();
 await page.getByText('Layout preview width',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Send campaign',exact:true}).count(),0);
 await page.getByText('LIVE MARKETING DELIVERY: DISABLED',{exact:true}).waitFor();
 assert.equal(await page.getByRole('textbox',{name:'Manual test recipient',exact:true}).inputValue(),'');
 await page.locator('[data-testid="stMain"]').evaluate(e=>e.scrollTop=0);
 await page.screenshot({path:out+'/preview-1440.png'});
 await page.setViewportSize({width:1920,height:1080});
 await page.screenshot({path:out+'/preview-1920.png'});
 // Exercise every email width through the actual preview slider.
 const slider=page.getByRole('slider');
 await slider.focus();await page.keyboard.press('ArrowLeft');
 for(const [i,width] of [320,375,390,430,600].entries()){
   if(i)await page.keyboard.press('ArrowRight');
   await page.waitForFunction(w=>Array.from(document.querySelectorAll('iframe')).some(f=>Math.round(f.getBoundingClientRect().width)===w),width);
   // Locate email frame by content instead of assuming a frame index.
   let emailFrame;
   for(const f of page.frames())if(await f.locator('body').count() && (await f.locator('body').innerText()).includes('production link not activated')){
     if(f!==page.mainFrame())emailFrame=f;
   }
   assert(emailFrame,'Rendered email frame exists');
   const metrics=await emailFrame.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth,body:document.body.innerText}));
   assert(metrics.scroll<=metrics.viewport+1,`No horizontal overflow at ${width}`);
   assert(metrics.body.includes('Unsubscribe'));
   await page.locator('iframe').first().screenshot({path:out+`/email-${width}.png`});
 }
 fs.writeFileSync(out+'/verification.json',JSON.stringify({viewports:['1440x900','1920x1080'],emailWidths:[320,375,390,430,600],creation:true,editing:true,audience:true,copyPrompt:true,noLiveSend:true,noEmailSent:true},null,2));
 console.log('Campaign browser checks passed. Screenshots: '+out);
 } catch(error) {await page.screenshot({path:out+'/failure.png'});console.error(await page.locator('body').innerText());throw error;} finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
