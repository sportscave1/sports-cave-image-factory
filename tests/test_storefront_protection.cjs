const {chromium}=require('playwright');
const fs=require('fs');
const assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const source=fs.readFileSync('storefront-protection.js','utf8');
 let checks=0;
 for(const width of [1920,1366,750,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://fixture.test/**',r=>r.fulfill({contentType:'text/html',body:'<html><head></head><body><div class="product__media"><img src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></div><input aria-label="email"><button id="cart">Add to Cart</button><script src="https://sports-cave-image-factory.onrender.com/storefront-protection.js" defer></script></body></html>'}));
  await page.route('https://sports-cave-image-factory.onrender.com/storefront-protection.js',r=>r.fulfill({contentType:'application/javascript',body:source}));
  await page.route('https://sports-cave-image-factory.onrender.com/api/storefront-protection/config',r=>r.abort());
  await page.goto('https://fixture.test/products/edition');
  await page.waitForFunction(()=>window.__scProtectionInstalled);
  const values=await page.evaluate(()=>{
   const image=document.querySelector('img'),input=document.querySelector('input');
   const cancelled=(target,type)=>!target.dispatchEvent(new Event(type,{bubbles:true,cancelable:true}));
   return {rightClick:cancelled(image,'contextmenu'),inputAllowed:!cancelled(input,'contextmenu'),drag:cancelled(image,'dragstart'),inputCopy:!cancelled(input,'copy'),marker:image.hasAttribute('data-sc-protected'),draggable:image.draggable,overflow:document.documentElement.scrollWidth>innerWidth};
  });
  assert.deepStrictEqual(values,{rightClick:true,inputAllowed:true,drag:true,inputCopy:true,marker:true,draggable:false,overflow:false});checks+=7;
  await page.emulateMedia({media:'print'});
  assert.equal(await page.locator('img').evaluate(el=>getComputedStyle(el).visibility),'hidden');checks++;
  await page.emulateMedia({media:'screen'});await page.getByRole('button',{name:'Add to Cart'}).click();checks++;
  await page.getByRole('textbox',{name:'email'}).fill('test@example.test');assert.equal(await page.getByRole('textbox',{name:'email'}).inputValue(),'test@example.test');checks++;
  await page.evaluate(()=>{const image=document.createElement('img');image.className='sc-protected-artwork';document.body.appendChild(image);});
  await page.waitForFunction(()=>document.querySelector('.sc-protected-artwork').draggable===false);checks++;
  assert.deepStrictEqual(errors,[]);checks++;
  await page.close();
 }
 await browser.close();console.log(JSON.stringify({checks,widths:[1920,1366,750,390,320],errors:0}));
})().catch(error=>{console.error(error);process.exit(1);});
