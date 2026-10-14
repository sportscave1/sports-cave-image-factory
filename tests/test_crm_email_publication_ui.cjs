const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});const results=[];
 try{for(const mode of ['enabled','disabled','paused','overview']){const paused=mode==='paused',disabled=mode==='disabled';
 const page=await browser.newPage({viewport:{width:1440,height:1000}});page.setDefaultTimeout(25000);const errors=[];
 page.on('pageerror',e=>errors.push(e.message));await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 try{
 await page.goto('http://127.0.0.1:18895/?fixture_email_publication=1&fixture_steps=3&fixture_run=publication-'+Date.now()+(paused?'&fixture_paused=1':'')+(disabled?'&fixture_disabled=1':''));
 const rows=page.locator('[class*="st-key-flow-row-"]');await rows.nth(2).waitFor();
 const states=()=>rows.locator('[class*="st-key-flow-state-"]').evaluateAll(els=>els.map(e=>e.className.match(/st-key-flow-state-(\w+)-/)[1]));
 assert.deepEqual(await states(),[paused?'paused':'live',disabled?'disabled':'draft',disabled?'disabled':'draft']);
 if(mode!=='overview'){await rows.nth(1).getByRole('button',{name:/Edit Email/}).click();
 await page.getByRole('tab',{name:'Settings',exact:true}).waitFor();await rows.first().waitFor({state:'hidden'});}
 const publish=page.locator('.st-key-toolbar-publish button:visible');await publish.waitFor();
 let start=Date.now();await publish.click();const dialog=page.getByRole('dialog');await dialog.getByRole('button',{name:'Publish All',exact:true}).waitFor();
 const latency=Date.now()-start,box=await dialog.boundingBox();if(!paused)await dialog.screenshot({path:'.tmp-flow-preview/publication-modal.png'});assert(box.width>=360&&box.width<=420,JSON.stringify(box));
 await dialog.getByRole('button',{name:'Cancel',exact:true}).focus();await page.keyboard.press('Enter');await dialog.waitFor({state:'hidden'});
 await publish.click();await dialog.getByRole('button',{name:'Publish All',exact:true}).waitFor();
 if(paused)await dialog.getByText('This flow will remain paused.',{exact:true}).waitFor();
 if(disabled){
  await dialog.getByText('2 disabled email(s) will remain excluded.',{exact:true}).waitFor();
  for(let i=0;i<2;i++){await dialog.locator('label').filter({has:page.getByRole('checkbox')}).nth(i).click();await page.waitForTimeout(250);}
 }
 await dialog.getByText('3 emails will '+(paused?'be published; the flow stays paused:':'be live for future eligible customers:'),{exact:true}).waitFor();
 await dialog.getByRole('button',{name:'Publish All',exact:true}).dblclick();
 await rows.nth(2).waitFor();await rows.nth(1).locator('[class*="st-key-flow-state-'+(paused?'paused':'live')+'-"]').waitFor();
 assert.deepEqual(await states(),[paused?'paused':'live',paused?'paused':'live',paused?'paused':'live']);
 await page.getByText('Flow published successfully.',{exact:true}).waitFor();
 await page.reload();await rows.nth(2).waitFor();assert.deepEqual(await states(),[paused?'paused':'live',paused?'paused':'live',paused?'paused':'live']);
 assert.equal(await page.getByTestId('stException').count(),0);assert.deepEqual(errors,[]);
 results.push({mode,paused,modal_ms:latency,modal_width:box.width,states:await states(),cancel:true,automatic_return:true,reload:true});
 }catch(e){console.log((await page.locator('body').innerText()).slice(0,6000));throw e;}finally{await page.close();}
 }
 const failure=await browser.newPage({viewport:{width:1440,height:1000}});failure.setDefaultTimeout(25000);
 await failure.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
 await failure.goto('http://127.0.0.1:18895/?fixture_email_publication=1&fixture_steps=3&fixture_run=failure-'+Date.now());
 const fr=failure.locator('[class*="st-key-flow-row-"]');await fr.nth(2).waitFor();await fr.nth(1).getByRole('button',{name:/Edit Email/}).click();
 const subject=failure.getByRole('textbox',{name:'Subject',exact:true});await subject.fill('Fixture worker rejection');await subject.press('Tab');
 await fr.first().waitFor({state:'hidden'});await failure.locator('.st-key-toolbar-publish button:visible').click();await failure.getByRole('dialog').getByRole('button',{name:'Publish All',exact:true}).click();
 await failure.getByText(/Publishing failed · Email tracking validation failed/).waitFor();
 assert.equal(await subject.inputValue(),'Fixture worker rejection');assert.equal(await failure.getByRole('tab',{name:'Settings',exact:true}).count(),1);
 assert.equal(await failure.getByText('Flow published successfully.',{exact:true}).count(),0);
 await failure.reload();await subject.waitFor();assert.equal(await subject.inputValue(),'Fixture worker rejection');
 results.push({failure_preserves_editor:true,failure_preserves_draft_after_reload:true,false_success:false});await failure.close();
 fs.writeFileSync('docs/email-full-flow-publication-validation-20261014.json',JSON.stringify({fixture:'Loopback synthetic data only; external requests blocked',results},null,2));console.log(JSON.stringify(results));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
