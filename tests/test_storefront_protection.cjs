const {chromium}=require('playwright');
const fs=require('fs'),assert=require('assert');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 const source=fs.readFileSync('shopify_theme/assets/sports-cave-image-protection.js','utf8');
 let checks=0;
 assert(!source.includes('notify('));assert(!source.includes('sc-protection-notice'));
 assert(fs.readFileSync('shopify_theme/assets/sports-cave-image-protection.css','utf8').includes('-webkit-touch-callout:none'));
 const html=`<html><head><style>${fs.readFileSync("shopify_theme/assets/sports-cave-image-protection.css","utf8")}</style></head><body>
 <div class="product__media"><img id="art" alt="Artwork" src="data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"></div>
 <p id="text">Ordinary product description</p><input aria-label="email"><button id="cart">Add to Cart</button>
 <select aria-label="Size"><option>S</option><option>M</option></select><button id="next">Next image</button>
 <a href="#details">Details</a><div class="sc-wall-v1"><div class="product__media"><img id="wall" alt="Wall preview"></div><button>PLACE</button></div>
 <script>window.shopping={cart:0,next:0,swipe:0};document.getElementById('cart').onclick=()=>shopping.cart++;document.getElementById('next').onclick=()=>shopping.next++;document.getElementById('art').addEventListener('touchmove',e=>{if(!e.defaultPrevented)shopping.swipe++;});</script>
 <script src="https://sports-cave-image-factory.onrender.com/storefront-protection.js" defer></script></body></html>`;
 async function fixture(width,url='https://www.sportscaveshop.com/products/edition',flags={enabled:true,showCopyrightMessage:true}){
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
  await page.waitForFunction(()=>window.__scProtectionReady);
  const values=await page.evaluate(()=>{
   const art=document.querySelector('#art'),input=document.querySelector('input'),wall=document.querySelector('#wall');
   art.addEventListener('contextmenu',e=>e.stopPropagation());
   const cancelled=(target,type)=>!target.dispatchEvent(new Event(type,{bubbles:true,cancelable:true}));
   const save=target=>!target.dispatchEvent(new KeyboardEvent('keydown',{key:'s',ctrlKey:true,bubbles:true,cancelable:true}));
   art.dispatchEvent(new Event('touchmove',{bubbles:true,cancelable:true}));
   return {rightClick:cancelled(art,'contextmenu'),textAllowed:!cancelled(document.querySelector('#text'),'contextmenu'),inputAllowed:!cancelled(input,'contextmenu'),drag:cancelled(art,'dragstart'),copy:cancelled(art,'copy'),inputCopy:!cancelled(input,'copy'),wallAllowed:!cancelled(wall,'contextmenu'),wallUnmarked:!wall.hasAttribute('data-sc-protected'),marker:art.hasAttribute('data-sc-protected'),draggable:art.draggable,saveArt:save(art),saveInput:save(input),saveText:save(document.querySelector('#text')),swipe:shopping.swipe,overflow:document.documentElement.scrollWidth>innerWidth,watermark:!!document.querySelector('.sc-artwork-watermark')};
  });
  assert.deepStrictEqual(values,{rightClick:true,textAllowed:true,inputAllowed:true,drag:true,copy:true,inputCopy:true,wallAllowed:false,wallUnmarked:true,marker:false,draggable:true,saveArt:true,saveInput:false,saveText:false,swipe:1,overflow:false,watermark:false});checks+=16;
  const silent=await page.evaluate(()=>{
   const art=document.querySelector('#art'),text=document.querySelector('#text');
   let messages=0;window.alert=window.confirm=window.prompt=()=>messages++;
   const before=document.body.innerHTML;
   for(const type of ['contextmenu','dragstart','copy','selectstart'])assertSilent(type);
   function assertSilent(type){art.dispatchEvent(new Event(type,{bubbles:true,cancelable:true}));}
   art.dispatchEvent(new KeyboardEvent('keydown',{key:'PrintScreen',bubbles:true,cancelable:true}));
   art.dispatchEvent(new KeyboardEvent('keydown',{key:'s',metaKey:true,bubbles:true,cancelable:true}));
   return {unchanged:before===document.body.innerHTML,messages,selection:!art.dispatchEvent(new Event('selectstart',{bubbles:true,cancelable:true})),textSelection:text.dispatchEvent(new Event('selectstart',{bubbles:true,cancelable:true})),css:getComputedStyle(art).userSelect};
  });
  assert.deepStrictEqual(silent,{unchanged:true,messages:0,selection:true,textSelection:true,css:'none'});checks+=5;
  await page.emulateMedia({media:'print'});assert.equal(await page.locator('#art').evaluate(el=>getComputedStyle(el).visibility),'hidden');checks++;
  await page.emulateMedia({media:'screen'});
  await page.getByRole('button',{name:'Add to Cart'}).click();await page.getByRole('button',{name:'Next image'}).click();
  await page.getByRole('combobox',{name:'Size'}).selectOption('M');
  assert.deepStrictEqual(await page.evaluate(()=>shopping),{cart:1,next:1,swipe:1});checks++;
  await page.getByRole('textbox',{name:'email'}).fill('test@example.test');assert.equal(await page.getByRole('textbox',{name:'email'}).inputValue(),'test@example.test');checks++;
  await page.evaluate(()=>{const img=document.createElement('img');img.className='sc-protected-artwork';document.body.appendChild(img);});
  assert.equal(await page.locator('.sc-protected-artwork').evaluate(e=>{e.addEventListener('contextmenu',ev=>ev.stopPropagation());return e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}));}),false);checks++;
  await page.locator('#art').evaluate(e=>{e.onclick=()=>window.artOpened=true;});await page.locator('#art').click();assert.equal(await page.evaluate(()=>window.artOpened),true);checks++;
  await page.getByRole('link',{name:'Details'}).click();assert(page.url().endsWith('#details'));checks++;
  assert.deepStrictEqual(errors,[]);assert.equal(reads(),1);checks+=2;await page.close();
 }
 for(const url of ['https://sports-cave-image-factory.onrender.com/','https://www.sportscaveshop.com/account/login','https://www.sportscaveshop.com/checkouts/test']){
  const {page,reads}=await fixture(390,url);assert.equal(await page.evaluate(()=>!!window.__scProtectionInstalled),false);assert.equal(reads(),0);checks+=2;await page.close();
 }
 for(const flags of [{enabled:false},{enabled:true,visibleWatermark:true}]){
  const {page}=await fixture(390,undefined,flags);await page.waitForTimeout(150);
  if(flags.enabled===false){assert.equal(await page.locator('#art').evaluate(e=>e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),true);assert.equal(await page.locator('#art').evaluate(e=>e.draggable),true);}
  else {assert.equal(await page.locator('.sc-artwork-watermark').count(),1);assert.equal(await page.locator('.sc-artwork-watermark').evaluate(e=>getComputedStyle(e).pointerEvents),'none');}
  checks+=2;await page.close();
 }
 for(const [url,key] of [['https://www.sportscaveshop.com/','protectHomepage'],['https://www.sportscaveshop.com/collections/all','protectCollections'],['https://www.sportscaveshop.com/products/edition','protectProductImages']]){
  const f=await fixture(390,url,{enabled:true,[key]:false});await f.page.waitForFunction(()=>window.__scProtectionReady);
  assert.equal(await f.page.locator('#art').evaluate(e=>e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),true);checks++;await f.page.close();
 }
 const wallOff=await fixture(390,undefined,{enabled:true,protectWallPreview:false});await wallOff.page.waitForFunction(()=>window.__scProtectionReady);assert.equal(await wallOff.page.locator('#wall').evaluate(e=>e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),true);checks++;await wallOff.page.close();
 const perf=await fixture(1366);await perf.page.waitForFunction(()=>window.__scProtectionReady);
 await perf.page.addScriptTag({content:source});assert.equal(perf.reads(),1);checks++;
 const milliseconds=await perf.page.evaluate(()=>{const e=document.querySelector('#art'),t=performance.now();for(let i=0;i<1000;i++)e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}));return performance.now()-t;});
 console.log(JSON.stringify({delegatedEvents:1000,milliseconds,scriptBytes:Buffer.byteLength(source),polling:0,extraConfigRequestsAfterReinstall:perf.reads()-1}));await perf.page.close();
 const real=await fixture(1366);await real.page.waitForFunction(()=>window.__scProtectionReady);
 for(const className of ['sc-product-media','gallery-viewer','sc-square-mobile-zoom','sc-featured-collection-banner__frame']){
  assert.equal(await real.page.evaluate(c=>{const host=document.createElement('div');host.className=c;const img=document.createElement('img');host.append(img);document.body.append(host);return img.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}));},className),false);checks++;
 }await real.page.close();
 const outage=await fixture(390,undefined,null); await outage.page.waitForTimeout(150); assert.equal(await outage.page.locator('#art').evaluate(e=>e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))),true);assert.deepStrictEqual(outage.errors,[]);checks+=2;await outage.page.close();
 // Real WebKit CSS support is checked in WebKit, not inferred from Chromium.
 console.log(JSON.stringify({checks,widths:[1920,1366,750,390,320],errors:0}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
