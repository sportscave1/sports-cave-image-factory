// Actual Streamlit composer, disposable PostgreSQL, mocked Shopify, no sends.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const results=[];
 for(const channel of (process.env.EDITOR_CHANNEL?[process.env.EDITOR_CHANNEL]:['chrome','msedge']))for(const width of (process.env.EDITOR_WIDTH?[Number(process.env.EDITOR_WIDTH)]:[1440,430])){
  console.log('Checking',channel,width);const browser=await chromium.launch({channel,headless:true});let page;
  try{
   page=await browser.newPage({viewport:{width,height:950}});const errors=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('framenavigated',f=>{if(f===page.mainFrame())console.log('Main location:',f.url());});
   await page.route('**/*',route=>new URL(route.request().url()).hostname==='127.0.0.1'?route.continue():route.abort());
   await page.goto('http://127.0.0.1:8544/?fixture_checkout=1&fixture_run='+Date.now());
   await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
   await page.getByRole('tab',{name:'Editor',exact:true}).click();
   const controls=page.frameLocator('iframe[title="crm_section_ui.crm_middle_sections_v2"]');
   await controls.getByRole('button',{name:'Visible section — click to hide'}).first().waitFor();
   const preview=page.frameLocator('.st-key-crm-composer-preview iframe');
   await preview.getByText('Still thinking it over?',{exact:true}).waitFor();
   // Measure in-browser click-to-DOM completion, excluding Playwright overhead.
   const hide=await controls.locator('body').evaluate(async()=>{
    const button=document.querySelector('.visibility'),started=performance.now();button.click();
    await new Promise(requestAnimationFrame);return performance.now()-started;
   });
   await assert.doesNotReject(()=>preview.getByText('Still thinking it over?',{exact:true}).waitFor({state:'hidden',timeout:200}));
   assert.equal(await controls.getByRole('textbox',{name:'Abandoned Checkout HTML'}).count(),1);
   await controls.getByRole('button',{name:'Hidden section — click to show'}).click();
   await preview.getByText('Still thinking it over?',{exact:true}).waitFor({timeout:200});
   await controls.getByRole('button',{name:'Duplicate section',exact:true}).first().click();
   assert.equal(await controls.locator('.section').count(),2);
   assert.equal(await preview.locator('[data-section-id]').count(),2);
   const ids=await controls.locator('.section').evaluateAll(nodes=>nodes.map(n=>n.dataset.id));assert.equal(new Set(ids).size,2);
   const move=controls.locator('.section').last().getByRole('button',{name:'Drag to reorder section; Alt + Up or Down'});
   await move.focus();await page.keyboard.press('Alt+ArrowUp');
   assert.deepEqual(await controls.locator('.section').evaluateAll(ns=>ns.map(n=>n.dataset.id)),ids.slice().reverse());
   assert.deepEqual(await preview.locator('[data-section-id]').evaluateAll(ns=>ns.map(n=>n.dataset.sectionId)),ids.slice().reverse());
   for(let n=0;n<8;n++){await page.keyboard.press(n%2?'Alt+ArrowUp':'Alt+ArrowDown');}
   await controls.locator('.section').first().getByRole('button',{name:'Delete section',exact:true}).click();
   await controls.getByRole('button',{name:'Confirm delete section'}).click();
   assert.equal(await preview.locator('[data-section-id]').count(),1);
   await controls.getByRole('button',{name:'Undo delete section'}).click();
   assert.equal(await preview.locator('[data-section-id]').count(),2);
   await controls.locator('textarea').first().fill('<p>Newest local draft</p><script>throw Error("unsafe")</script>');
   await preview.getByText('Newest local draft',{exact:true}).waitFor({timeout:500});
   assert.equal(await preview.locator('#sc-local-sections script').count(),0);
   await controls.getByText('Saved · Draft',{exact:true}).waitFor({timeout:15000});
   assert.equal(await page.getByTestId('stException').count(),0);
   await page.locator('.st-key-crm-preview-devices button:visible').nth(1).click();
   await preview.getByText('Newest local draft',{exact:true}).waitFor();
   const before=await controls.locator('.section').evaluateAll(ns=>ns.map(n=>n.dataset.id));
   await page.getByRole('button',{name:'Flow',exact:true}).click();
   await page.getByRole('button',{name:'Edit Email',exact:true}).first().click();
   await page.getByRole('tab',{name:'Editor',exact:true}).click();
   await controls.locator('.section').first().waitFor();
   assert.deepEqual(await controls.locator('.section').evaluateAll(ns=>ns.map(n=>n.dataset.id)),before);
   await preview.getByText('Newest local draft',{exact:true}).waitFor();
   // Cached insertion and error recovery must be local, including while hidden.
   const count=await controls.locator('.section').count();
   await controls.locator('#add > summary').click();
   await controls.locator('[data-add="html"]').click();
   assert.equal(await controls.locator('.section').count(),count+1);
   await controls.locator('textarea').last().fill('<p>{{unsupported}}</p>');
   await preview.getByRole('alert').waitFor({timeout:500});
   await controls.locator('textarea').last().fill('<p>Corrected section</p><img width="1" height="1" src="https://pixel.example/pixel.png">');
   await preview.getByText('Corrected section',{exact:true}).waitFor({timeout:500});
   assert.equal(await preview.locator('img[src*="pixel.example"]').count(),0);
   await controls.locator('#add > summary').click();
   await controls.locator('[data-add="checkout"]').click();
   assert.equal(await controls.locator('.section').count(),count+2);
   await preview.getByText('Still thinking it over?',{exact:true}).last().waitFor({timeout:200});
   await controls.getByText('Saved · Draft',{exact:true}).waitFor({timeout:15000});
   assert.deepEqual(errors,[]);results.push({channel,width,hideMs:hide});
   await page.screenshot({path:`tmp/local-editor-${channel}-${width}.png`,fullPage:true});
  }catch(error){if(page){fs.writeFileSync('tmp/local-editor-failure.txt',page.url()+'\n'+await page.locator('body').innerText());await page.screenshot({path:'tmp/local-editor-failure.png',fullPage:true});}throw error;}finally{await browser.close();}
 }
 fs.writeFileSync('tmp/local-editor-browser.json',JSON.stringify(results,null,2));console.log(results);
})().catch(error=>{console.error(error);process.exit(1)});
