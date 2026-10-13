const {chromium,webkit}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const browser=await (process.env.PSD_BROWSER==='webkit'?webkit:chromium).launch(process.env.PSD_BROWSER==='webkit'?{headless:true}:{channel:'chrome',headless:true});try{
 const page=await browser.newPage();let saves=[],reloads=0,current='';
 const root=`<html><body><a id="file" href="/files-psd-picker?product_gid=gid%3A%2F%2Fshopify%2FProduct%2F1">Add</a><iframe src="/component" style="height:0"></iframe><script>window.addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue'){document.querySelector('#file').textContent='Open PSD';document.querySelector('#file').href='/api/files-psd-open?product_gid=1';window.componentSaved=e.data.value;}});</script></body></html>`;
 await page.route('**/*',async route=>{const url=new URL(route.request().url());
  if(url.hostname!=='psd.local.test')return route.abort();
  if(url.pathname==='/'){reloads++;return route.fulfill({contentType:'text/html',body:root});}
  if(url.pathname==='/component')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/psd_picker/index.html','utf8')});
  if(url.pathname==='/files-psd-picker')return route.fulfill({contentType:'text/html',body:fs.readFileSync('components/psd_picker/picker.html','utf8')});
  if(url.pathname==='/api/files-psd-options')return route.fulfill({json:{product_title:'Selected Artwork',current_file_id:current,files:[{id:'id:one',name:'Selected Artwork.psd',mismatch:false},{id:'id:two',name:'Different Artwork.psd',mismatch:true}]}});
  if(url.pathname==='/api/files-psd-attach'){const data=route.request().postDataJSON();saves.push(data);current=data.file_id;return route.fulfill({json:{ok:true}});}
  return route.fulfill({status:404,body:'unavailable'});
 });
 await page.goto('http://psd.local.test/');await page.waitForFunction(()=>!!window.SportsCavePsdPicker);
 await page.getByText('Add',{exact:true}).click();let picker=page.frameLocator('dialog iframe');await picker.getByText('Attach PSD to: Selected Artwork').waitFor();
 await picker.getByRole('textbox').fill('Different');assert.equal(await picker.locator('#files option').count(),1);
 await picker.locator('#files').selectOption('id:two');await picker.getByText('Save PSD',{exact:true}).click();assert.equal(saves.length,0);await picker.getByText('Confirm the filename mismatch first.').waitFor();
 await picker.locator('#mismatch').check();await picker.getByText('Save PSD',{exact:true}).click();await page.getByText('Open PSD',{exact:true}).waitFor();assert.equal(saves.length,1);assert.equal(saves[0].confirm_mismatch,true);assert.equal(reloads,1);assert.equal(await page.locator('dialog').count(),0);
 // Reopen through the same production launcher to verify replace confirmation and cancellation.
 await page.evaluate(()=>window.open('/files-psd-picker?product_gid=gid%3A%2F%2Fshopify%2FProduct%2F1'));
 picker=page.frameLocator('dialog iframe');await picker.getByText('Attach PSD to: Selected Artwork').waitFor();await picker.locator('#files').selectOption('id:one');await picker.getByText('Save PSD',{exact:true}).click();assert.equal(saves.length,1);await picker.getByText('Confirm replacement first.').waitFor();await picker.locator('#replace').check();await picker.getByText('Save PSD',{exact:true}).click();await page.waitForFunction(()=>!document.querySelector('dialog'));assert.equal(saves.length,2);assert.equal(saves[1].confirm_replace,true);assert.equal(saves[1].expected_file_id,'id:two');
 await page.evaluate(()=>window.open('/files-psd-picker?product_gid=1'));picker=page.frameLocator('dialog iframe');await picker.getByText('Cancel',{exact:true}).click();await page.waitForFunction(()=>!document.querySelector('dialog'));assert.equal(saves.length,2);assert.equal(reloads,1);
 await page.evaluate(()=>{window.open('Not linked');window.open('Unavailable');});assert.equal(browser.contexts()[0].pages().length,1);
 console.log('PSD browser workflow passed: Add → Search → Select → Confirm → Save → Open PSD; replace, cancel, missing, no full reload, no live network.');
 }finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});
