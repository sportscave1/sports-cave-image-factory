const {chromium}=require('playwright');
const fs=require('fs'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const source=fs.readFileSync('storefront-protection.js','utf8');
 let checks=0;
 const html=`<html><head></head><body>
 <div class="product__media"><img id="art" alt="Artwork" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></div>
 <p id="text">Ordinary product description</p><input aria-label="email"><button id="cart">Add to Cart</button>
 <select aria-label="Size"><option>S</option><option>M</option></select><button id="next">Next image</button>
 <a href="#details">Details</a><div class="sc-wall-v1"><div class="product__media"><img id="wall" alt="Wall preview"></div><button>PLACE</button></div>
 <script>window.shopping={cart:0,next:0,swipe:0};document.getElementById('cart').onclick=()=>shopping.cart++;document.getElementById('next').onclick=()=>shopping.next++;document.getElementById('art').addEventListener('touchmove',e=>{if(!e.defaultPrevented)shopping.swipe++;});</script>
 <script src="https://sports-cave-image-factory.onrender.com/storefront-protection.js" defer></script></body></html>`;
 async function fixture(width,url='https://www.sportscaveshop.com/products/edition',flags=null){
  const page=await browser.newPage({viewport:{width,height:900}});let reads=0,errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{
   const u=r.request().url();
   if(u.endsWith('/storefront-protection.js'))return r.fulfill({contentType:'application/javascript',body:source});
   if(u.endsWith('/api/storefront-protection/config')){reads++;return flags===null?r.abort():r.fulfill({contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*'},body:JSON.stringify(flags)});}
   if(u===url)return r.fulfill({contentType:'text/html',body:html});
   return r.abort();
  });
  await page.goto(url);await page.waitForLoadState('load');return {page,errors,reads:()=>reads};
 }
 try{
 for(const width of [1920,1366,750,390,320]){
  const {page,errors,reads}=await fixture(width);
  await page.waitForFunction(()=>window.__scProtectionInstalled);
  const values=await page.evaluate(()=>{
   const art=document.querySelector('#art'),input=document.querySelector('input'),wall=document.querySelector('#wall');
   const cancelled=(target,type)=>!target.dispatchEvent(new Event(type,{bubbles:true,cancelable:true}));
   const save=target=>!target.dispatchEvent(new KeyboardEvent('keydown',{key:'s',ctrlKey:true,bubbles:true,cancelable:true}));
   art.dispatchEvent(new Event('touchmove',{bubbles:true,cancelable:true}));
   return {rightClick:cancelled(art,'contextmenu'),textAllowed:!cancelled(document.querySelector('#text'),'contextmenu'),inputAllowed:!cancelled(input,'contextmenu'),drag:cancelled(art,'dragstart'),copy:cancelled(art,'copy'),inputCopy:!cancelled(input,'copy'),wallAllowed:!cancelled(wall,'contextmenu'),wallUnmarked:!wall.hasAttribute('data-sc-protected'),marker:art.hasAttribute('data-sc-protected'),draggable:art.draggable,saveArt:save(art),saveInput:save(input),saveText:save(document.querySelector('#text')),swipe:shopping.swipe,overflow:document.documentElement.scrollWidth>innerWidth,watermark:!!document.querySelector('.sc-artwork-watermark')};
  });
  assert.deepStrictEqual(values,{rightClick:true,textAllowed:true,inputAllowed:true,drag:true,copy:true,inputCopy:true,wallAllowed:true,wallUnmarked:true,marker:true,draggable:false,saveArt:true,saveInput:false,saveText:false,swipe:1,overflow:false,watermark:false});checks+=16;
  await page.emulateMedia({media:'print'});assert.equal(await page.locator('#art').evaluate(el=>getComputedStyle(el).visibility),'hidden');checks++;
  await page.emulateMedia({media:'screen'});
  await page.getByRole('button',{name:'Add to Cart'}).click();await page.getByRole('button',{name:'Next image'}).click();
  await page.getByRole('combobox',{name:'Size'}).selectOption('M');
  assert.deepStrictEqual(await page.evaluate(()=>shopping),{cart:1,next:1,swipe:1});checks++;
  await page.getByRole('textbox',{name:'email'}).fill('test@example.test');assert.equal(await page.getByRole('textbox',{name:'email'}).inputValue(),'test@example.test');checks++;
  await page.evaluate(()=>{const img=document.createElement('img');img.className='sc-protected-artwork';document.body.appendChild(img);});
  await page.waitForFunction(()=>document.querySelector('.sc-protected-artwork').draggable===false);checks++;
  assert.deepStrictEqual(errors,[]);assert.equal(reads(),1);checks+=2;await page.close();
 }
 for(const url of ['https://sports-cave-image-factory.onrender.com/','https://www.sportscaveshop.com/account/login','https://www.sportscaveshop.com/checkouts/test']){
  const {page,reads}=await fixture(390,url);assert.equal(await page.evaluate(()=>!!window.__scProtectionInstalled),false);assert.equal(reads(),0);checks+=2;await page.close();
 }
 for(const flags of [{enabled:false},{visibleWatermark:true}]){
  const {page}=await fixture(390,undefined,flags);await page.waitForTimeout(150);
  if(flags.enabled===false){assert.equal(await page.locator('#art').evaluate(e=>e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),true);assert.equal(await page.locator('#art').evaluate(e=>e.draggable),true);}
  else {assert.equal(await page.locator('.sc-artwork-watermark').count(),1);assert.equal(await page.locator('.sc-artwork-watermark').evaluate(e=>getComputedStyle(e).pointerEvents),'none');}
  checks+=2;await page.close();
 }
 // Real WebKit CSS support is checked in WebKit, not inferred from Chromium.
 console.log(JSON.stringify({checks,widths:[1920,1366,750,390,320],errors:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
