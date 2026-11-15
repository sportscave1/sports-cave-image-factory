// Real storefront QA. Theme override optional; no customer data or OS policy writes.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const base='https://www.sportscaveshop.com',theme=process.env.SC_THEME_ID||'',out=process.env.SC_PROTECTION_OUTPUT||'.tmp-protection/evidence';
const modes=process.env.SC_PROTECTION_QUICK?[['chrome',1440,900]]:[['chrome',1920,1080],['msedge',1440,900],['chrome',390,844],['chrome',430,932]];
const paths=['/products/shohei-ohtani-wall-art','/products/legends-never-die-kobe-bryant-michael-jordan-wall-art','/collections/all','/'];
(async()=>{fs.mkdirSync(out,{recursive:true});const results=[];
 for(const [channel,width,height] of modes.filter(m=>!process.env.SC_PROTECTION_MOBILE||m[1]<500)){const browser=await chromium.launch({channel,headless:true});try{
 const context=await browser.newContext({viewport:{width,height},isMobile:width<500,hasTouch:width<500,...(width===390?{userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'}:width===430?{userAgent:'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/130.0.0.0 Mobile Safari/537.36'}:{})});
 for(const route of paths){const page=await context.newPage(),errors=[],failures=[];page.on('pageerror',e=>errors.push(e.stack||e.message));page.on('requestfailed',r=>{if(/image-protection|storefront-protection/.test(r.url()))failures.push(r.failure()?.errorText)});
 try{
 await page.addLocatorHandler(page.locator('#sc-collector-pop .sc-collector-close'),async locator=>{await locator.click();});
 await page.goto(base+route+(theme?'?preview_theme_id='+theme:''),{waitUntil:'commit',timeout:60000});
 await page.waitForFunction(()=>window.SportsCaveImageProtection?.enabled,{timeout:25000});
 await page.waitForFunction(()=>document.body&&document.images.length>2);
 const reject=page.getByRole('button',{name:/reject all|decline/i}).first();if(await reject.isVisible())await reject.click();
 const hide=page.frameLocator('#PBarNextFrame').getByRole('button',{name:/hide/i}).first();try{if(await hide.isVisible())await hide.click();}catch{}
 await page.waitForTimeout(700);await page.waitForFunction(()=>document.readyState!=='loading'&&document.body&&document.images.length>2&&window.SportsCaveImageProtection?.enabled);
 const record={channel,width,height,path:route,theme:await page.evaluate(()=>Shopify.theme.id)};
 record.coverage=await page.evaluate(()=>{
  const cancel=(el,type)=>!el.dispatchEvent(new Event(type,{bubbles:true,cancelable:true,composed:true}));
  const imgs=[...document.images],dynamic=document.createElement('img');document.body.append(dynamic);
  const result={version:SportsCaveImageProtection.version,images:imgs.length,allImagesContext:imgs.every(e=>cancel(e,'contextmenu')),allImagesDrag:imgs.every(e=>cancel(e,'dragstart')),backgroundContext:cancel(document.body,'contextmenu'),dynamic:cancel(dynamic,'contextmenu')&&cancel(dynamic,'dragstart'),legacy:!!window.__sportsCaveImageProtectLoaded,toast:!!document.querySelector('#sc-image-protect-toast,.sc-protection-notice'),dragCSS:getComputedStyle(dynamic).webkitUserDrag};dynamic.remove();return result;
 });
 assert.equal(record.coverage.version,'2026-10-07.1');assert(record.coverage.allImagesContext&&record.coverage.allImagesDrag&&record.coverage.dynamic&&record.coverage.backgroundContext);assert(!record.coverage.legacy&&!record.coverage.toast);assert.equal(record.coverage.dragCSS,'none');
 if(route.startsWith('/products/')){
  const img=page.locator(width<500?'.sc-square-mobile-slide.is-active .sc-square-mobile-zoom':'.media-gallery .main-image .slider__item.is-active a.show-gallery').first();
  if(width<500)await img.tap({timeout:12000});else await img.click({timeout:12000});
  const close=page.locator(width<500?'[data-sc-viewer-close]':'.gallery-viewer__close').first();await close.waitFor({state:'visible',timeout:10000});
  const enlarged=page.locator(width<500?'[data-sc-viewer-image]':'.gallery-viewer img').first();
  record.zoom=await enlarged.evaluate(e=>!e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}))&&!e.dispatchEvent(new Event('dragstart',{bubbles:true,cancelable:true})));assert(record.zoom);if(width<500)await close.tap();else await close.click();await close.waitFor({state:'hidden',timeout:8000});
  const groups=page.locator('variant-picker.sc-vp fieldset.option-selector');
  record.variants=[];
  for(const group of await groups.all()){
   const values=await group.locator('input[type=radio]').evaluateAll(es=>es.filter(e=>!e.disabled).map(e=>({id:e.id,value:e.value})));
   for(const value of values){await page.locator(`label[for="${value.id}"]`).click();assert(await page.locator(`[id="${value.id}"]`).isChecked());record.variants.push(value.value);}
  }
  await page.locator('[data-sc-wall-banner-open]').click();await page.locator('[data-sc-wall-overlay]').waitFor({state:'visible'});await page.keyboard.press('Escape');await page.locator('[data-sc-wall-overlay]').waitFor({state:'hidden'});record.wallPreview=true;
  record.purchaseEnabled=await page.locator('[data-sc-secure-edition-button]').isEnabled();assert(record.purchaseEnabled);
  if(process.env.SC_PROTECTION_CART==='1'&&route.includes('shohei')){
   const initial=await (await page.request.get(base+'/cart.js')).json();assert.equal(initial.item_count,0,'Only an empty isolated test cart may be used');let added;
   try{await page.locator('[data-sc-secure-edition-button]').click();await page.waitForFunction(()=>document.querySelector('cart-drawer')?.getAttribute('aria-hidden')==='false');
    const cart=await (await page.request.get(base+'/cart.js')).json();assert.equal(cart.item_count,1);added=cart.items[0];assert.equal(added.handle,'shohei-ohtani-wall-art');
    assert(await page.locator('cart-drawer [name=checkout],cart-drawer a[href*=checkout]').count());record.cart={added:true,drawer:true,checkoutControl:true};
    const image=page.locator('cart-drawer img').first();record.cart.imageProtected=await image.evaluate(e=>!e.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true})));assert(record.cart.imageProtected);
    await page.locator('cart-drawer [data-sc-close-cart]').first().click();
   }finally{const cart=await (await page.request.get(base+'/cart.js')).json();for(const item of cart.items){if(item.handle==='shohei-ohtani-wall-art')await page.request.post(base+'/cart/change.js',{data:{id:item.key,quantity:0}});}assert.equal((await (await page.request.get(base+'/cart.js')).json()).item_count,0);}
  }
 }
 record.reversible=await page.evaluate(()=>{const api=SportsCaveImageProtection,el=document.images[0];const event=()=>el.dispatchEvent(new Event('contextmenu',{bubbles:true,cancelable:true}));api.update({enabled:false});let stack='';const prevent=Event.prototype.preventDefault;Event.prototype.preventDefault=function(){if(this.type==='contextmenu')stack=new Error().stack;return prevent.call(this);};const off=event(),styleOff=!document.documentElement.hasAttribute('data-sc-protection-drag');Event.prototype.preventDefault=prevent;api.update({enabled:true});return {off,styleOff,restored:!event(),stack};});assert(record.reversible.off&&record.reversible.styleOff&&record.reversible.restored);
 record.errors=errors;record.protectionFailures=failures;results.push(record);console.log(JSON.stringify(record));
 }catch(e){results.push({channel,width,path:route,error:e.message,errors,failures});throw e;}finally{await page.close();fs.writeFileSync(`${out}/storefront-${theme||'live'}${process.env.SC_PROTECTION_MOBILE?'-mobile':''}.json`,JSON.stringify(results,null,2));}
 }
 }finally{await browser.close();}}
})().catch(e=>{console.error(e);process.exitCode=1});
