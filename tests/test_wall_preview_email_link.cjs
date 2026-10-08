const {chromium,webkit}=require('playwright');
const fs=require('fs'),assert=require('node:assert/strict');
const base='shopify/on-demand-wall-preview/';
const loader=fs.readFileSync(base+'assets/sports-cave-wall-preview-loader.js','utf8');
const engine=fs.readFileSync(base+'assets/sports-cave-wall-preview.js','utf8');
const helper=fs.readFileSync('tests/fixtures/wall_banner/sports-cave-wall-artwork.js','utf8');
const css=fs.readFileSync('tests/fixtures/wall_banner/sports-cave-wall-preview.css','utf8');
// Use the existing modal markup and engine, with synthetic public product data.
const snippet=fs.readFileSync(base+'snippets/sc-wall-visualizer-v1.liquid','utf8');
const overlay=snippet.slice(snippet.indexOf('<div class="sc-wall-v1__overlay"'),snippet.lastIndexOf('{% else %}'))
 .replace(/{{\s*value\s*\|\s*escape\s*}}/g,'XL - 62 x 87 cm')
 .replace(/{{[\s\S]*?}}/g,'').replace(/{%[\s\S]*?%}/g,'');
const shell='<div data-sc-wall-root data-product-id="123" data-sc-wall-js="/engine.js" data-sc-wall-css="/preview.css" data-sc-wall-artwork="/helper.js"></div>';
const trigger='<button data-sc-wall-preview-trigger>See it on your wall</button>';
const data={options:['Frame','Size'],variants:[{id:456,options:['White','XL - 62 x 87 cm'],option1:'White',option2:'XL - 62 x 87 cm',available:true,price:33900}],formatted:{456:{price:'339'}}};
const hydrated='<div class="sc-wall-v1" data-sc-wall-root data-product-id="123" data-product-handle="test" data-product-title="Test artwork" data-unit="cm"><script type="application/json" data-sc-wall-product-data>'+JSON.stringify(data)+'</script>'+overlay;
async function run(browser,label,viewport){
 const context=await browser.newContext({viewport});
 const page=await context.newPage(),errors=[],requests=[];
 let delayed=false,fail=false;
 await context.route('**/*',async r=>{
  const u=new URL(r.request().url());requests.push(u.pathname+u.search);
  if(u.searchParams.has('section_id'))return r.fulfill({status:fail?503:200,contentType:'text/html',body:hydrated});
  const files={'/engine.js':engine,'/helper.js':helper,'/preview.css':css};
  if(files[u.pathname])return r.fulfill({contentType:u.pathname.endsWith('css')?'text/css':'text/javascript',body:files[u.pathname]});
  if(u.pathname.startsWith('/products/'))return r.fulfill({contentType:'text/html',body:'<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font:16px Arial}button{font:inherit}main{min-height:2400px}</style><main class="section-main-product"><h1>Test product</h1><form action="/cart/add"><input name="id" value="456"></form><div id="mount" style="margin-top:1600px">'+(delayed?'':trigger+shell)+'</div></main><script>'+loader+'</script>'});
  return r.fulfill({status:204,body:''});
 });
 page.on('pageerror',e=>errors.push(e.message));
 await page.addInitScript(()=>{
  window.cameraRequests=0;
  if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>{window.cameraRequests++;throw new DOMException('Mock camera unavailable','NotAllowedError');};
 });
 const url='https://preview.test/products/test?variant=456&sc_wall_preview=1&utm_source=email&utm_campaign=recovery#product';
 await page.goto(url);
 await page.getByRole('heading',{name:'Take a photo of your wall'}).waitFor({state:'visible'});
 assert.equal(await page.locator('[data-sc-wall-overlay]').count(),1);
 assert.equal(await page.evaluate(()=>cameraRequests),0);
 assert.equal(await page.evaluate(()=>scrollY),0);
 assert.equal(await page.locator('input[name=id]').inputValue(),'456');
 const after=new URL(page.url());assert.equal(after.searchParams.get('variant'),'456');assert.equal(after.searchParams.get('utm_source'),'email');assert.equal(after.searchParams.get('utm_campaign'),'recovery');assert.equal(after.hash,'#product');
 for(const selector of ['[data-sc-wall-camera]','[data-sc-wall-upload]','[data-sc-wall-keep-browsing]']){
  const b=await page.locator(selector).boundingBox();assert(b&&b.x>=0&&b.y>=0&&b.x+b.width<=viewport.width+1&&b.y+b.height<=viewport.height+1,selector+' fits viewport');
 }
 await page.addScriptTag({content:loader});
 assert.equal(requests.filter(u=>u.includes('section_id=')).length,1);
 await page.locator('[data-sc-wall-camera]').click();
 assert.equal(await page.evaluate(()=>cameraRequests),1);
 const chooser=page.waitForEvent('filechooser');await page.locator('[data-sc-wall-upload]').click();await chooser;
 await page.locator('[data-sc-wall-keep-browsing]').click();
 assert.equal(await page.locator('[data-sc-wall-overlay]').isVisible(),false);
 await page.evaluate(()=>document.dispatchEvent(new CustomEvent('shopify:section:load')));
 assert.equal(await page.locator('[data-sc-wall-overlay]').isVisible(),false);
 await page.locator('[data-sc-wall-preview-trigger]').click();
 await page.getByRole('heading',{name:'Take a photo of your wall'}).waitFor({state:'visible'});
 assert.equal(requests.filter(u=>u.includes('section_id=')).length,1);
 await page.keyboard.press('Escape');
 assert.equal(await page.locator('[data-sc-wall-overlay]').isVisible(),false);
 // No-flag visits stay lazy and retain manual opening.
 requests.length=0;await page.goto('https://preview.test/products/test?variant=456');
 assert.equal(await page.locator('[data-sc-wall-overlay]').count(),0);assert.equal(requests.length,1);
 await page.locator('[data-sc-wall-preview-trigger]').click();
 await page.getByRole('heading',{name:'Take a photo of your wall'}).waitFor({state:'visible'});
 // Trigger and root may arrive independently after DOMContentLoaded.
 delayed=true;await page.goto(url);
 await page.evaluate(t=>document.querySelector('#mount').innerHTML=t,trigger);
 assert.equal(await page.locator('[data-sc-wall-loading-dialog]').count(),0);
 await page.evaluate(s=>document.querySelector('#mount').insertAdjacentHTML('beforeend',s),shell);
 await page.getByRole('heading',{name:'Take a photo of your wall'}).waitFor({state:'visible'});
 // Failed preparation uses the existing retry interface, without a second job.
 delayed=false;fail=true;await page.goto(url);
 await page.getByRole('button',{name:'Try again',exact:true}).waitFor({state:'visible'});
 fail=false;await page.getByRole('button',{name:'Try again',exact:true}).click();
 await page.getByRole('heading',{name:'Take a photo of your wall'}).waitFor({state:'visible'});
 // Late unsupported markup after the bounded watch must not unexpectedly open.
 delayed=true;await page.clock.install();await page.goto(url);await page.clock.fastForward(21000);
 await page.evaluate(t=>document.querySelector('#mount').innerHTML=t,trigger+shell);
 assert.equal(await page.locator('[data-sc-wall-loading-dialog]').count(),0);
 assert.deepEqual(errors,[]);
 console.log('PASS',label,viewport.width+'x'+viewport.height,'actual popup, variant/UTM, lazy/manual, camera opt-in, upload chooser, close, late markup, retry, timeout, deduplication');
 await context.close();
}
(async()=>{
 for(const channel of ['chrome','msedge']){
  const browser=await chromium.launch({channel,headless:true});
  try{for(const viewport of [{width:1440,height:900},{width:390,height:844}])await run(browser,channel,viewport);}finally{await browser.close();}
 }
 if(fs.existsSync(webkit.executablePath())){const b=await webkit.launch({headless:true});try{await run(b,'WebKit',{width:390,height:844});}finally{await b.close();}}
 else console.log('NOT RUN: WebKit/Safari engine unavailable; physical iPhone/Android not tested.');
})().catch(e=>{console.error(e);process.exitCode=1;});
