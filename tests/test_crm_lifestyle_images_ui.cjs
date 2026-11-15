const {chromium}=require('playwright'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const context=await browser.newContext({viewport:{width:1440,height:1000}});
 await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('http://127.0.0.1:8893/?fixture_checkout=1&fixture_wall_preview=1&fixture_lifestyle=1&fixture_run=lifestyle'+Date.now());
 await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
 const subject=await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue();
 const editor=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
 for(const n of [1,2,3]){
   await page.getByRole('tab',{name:'Templates',exact:true}).click();
   await page.locator('.st-key-library_builtin-lifestyle-image-'+n).getByRole('button',{name:'Use',exact:true}).click();
   await page.getByRole('tab',{name:'Editor',exact:true}).click();
   await editor.getByText('Lifestyle Image '+n,{exact:true}).filter({visible:true}).first().waitFor();
 }
 const preview=page.frameLocator('.st-key-crm-composer-preview iframe');
 for(const n of [2,3,4])await preview.locator('img[src*="lifestyle-'+n+'.jpg"]').waitFor({state:'attached'});
 await preview.getByText(/complete your order/i).first().waitFor();
 await page.getByRole('button',{name:'Flow',exact:true}).click();
 await page.reload();await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
 assert.equal(await page.getByRole('textbox',{name:'Subject',exact:true}).inputValue(),subject);
 await page.getByRole('tab',{name:'Editor',exact:true}).click();
 for(const n of [1,2,3])await editor.getByText('Lifestyle Image '+n,{exact:true}).filter({visible:true}).first().waitFor();
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 // Check the authored responsive geometry independently of blocked CDN images.
 const fs=require('node:fs');const markup=fs.readFileSync('templates/lifestyle_image.html','utf8');
 for(const width of [320,375,600,1200]){
   await page.setViewportSize({width,height:800});await page.setContent(markup);
   const box=await page.locator('img').boundingBox();assert.ok(box.width<=520&&box.width<=width);
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
 }
 console.log('PASS three inserts, gallery mapping, checkout preserved, draft reopening, responsive 320/375/600/1200 widths, no browser exceptions');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
