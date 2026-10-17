/* Fully mocked storefront and static fixture. No OS server or provider credentials. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),out=path.join(root,'tmp/product-quiz-preview');
const config={questions:[{id:'sport',label:'Which sport?',enabled:true,answers:[]},{id:'subject',label:'Who belongs on your wall?',enabled:true,answers:[]},{id:'preference',label:'Which story speaks to you?',enabled:true,answers:[]}],appearance:{title:'Find your edition',intro:'Your sport. Your icons. Your edition.',accent:'#c6a76b',background:'#0b0b0c',text:'#f5f0e6'},rules:{max_results:3,allow_broader:true},aliases:{},collections:{basketball:'Basketball'}};
const products=[
  {id:'gid://shopify/Product/1',handle:'jordan',title:'Jordan Legacy',image:'https://cdn.shopify.com/jordan.jpg',sports:['Basketball'],subjects:['Michael Jordan'],preferences:['Legacy'],featured:0},
  {id:'gid://shopify/Product/2',handle:'rivals',title:'Rivals',image:'https://cdn.shopify.com/rivals.jpg',sports:['Basketball'],subjects:['Michael Jordan','Kobe Bryant'],preferences:['Rivalry'],featured:1},
  {id:'gid://shopify/Product/3',handle:'kobe',title:'Kobe Legacy',image:'https://cdn.shopify.com/kobe.jpg',sports:['Basketball'],subjects:['Kobe Bryant'],preferences:['Legacy'],featured:3},
  {id:'gid://shopify/Product/4',handle:'warne',title:'Warne',image:'https://cdn.shopify.com/warne.jpg',sports:['Cricket'],subjects:['Shane Warne'],preferences:[],featured:0}];
(async()=>{
 const browser=await chromium.launch({headless:true,channel:process.env.PRODUCT_QUIZ_BROWSER_CHANNEL||'chrome'});const page=await browser.newPage({viewport:{width:1440,height:1080}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('file:///'+path.join(out,'index.html').replaceAll('\\','/'));
 const inline=page.locator('#inline');await inline.getByRole('button',{name:'Basketball',exact:true}).click();
 await inline.getByRole('button',{name:'Show me all',exact:true}).click();
 await inline.getByRole('heading',{name:'Your editions',exact:true}).waitFor();
 assert.equal(await inline.locator('article').count(),3);
 await page.screenshot({path:path.join(out,'desktop.png'),fullPage:true});
 const launch=page.locator('#button').getByRole('button',{name:'Find your edition ↗'});await launch.click();
 assert.equal(await page.locator('#button').locator('dialog').evaluate(e=>e.open),true);
 await page.keyboard.press('Escape');assert.equal(await page.locator('#button').locator('dialog').evaluate(e=>e.open),false);
 assert.equal(await page.locator('#button').evaluate(e=>e.shadowRoot.activeElement?.textContent),'Find your edition ↗');
 await launch.click();await page.locator('#button').getByRole('button',{name:'Cricket',exact:true}).click();
 await page.locator('#button').getByRole('heading',{name:'Your editions',exact:true}).waitFor();
 await page.keyboard.press('Escape');
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(out,'mobile.png'),fullPage:true});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 const ranked=await page.evaluate(p=>SportsCaveQuizRuntime.ranked(p,{sport:'Basketball',subject:'Michael Jordan',preference:'Absent'},{allow_broader:true}),products);
 assert.equal(ranked.length,2);assert(ranked.every(p=>p.broader));assert(!ranked.some(p=>p.handle==='kobe'));
 assert.deepEqual(await page.evaluate(p=>SportsCaveQuizRuntime.ranked(p,{sport:'Cricket',subject:'Michael Jordan'},{allow_broader:true}),products),[]);
 let requests=[],events=[],available=true,failAssets=false,consent=true;
 await page.route('**/*',async route=>{
  const url=new URL(route.request().url());requests.push(url.pathname);
  const json=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data),headers:{'Access-Control-Allow-Origin':'*'}});
  if(url.hostname==='cdn.shopify.com')return route.fulfill({status:404});
  if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body><div id="a" data-sports-cave-quiz="button"></div><div id="b" data-sports-cave-quiz="button"></div><script>window.Shopify={routes:{root:"/en-au/"},customerPrivacy:{analyticsProcessingAllowed:()=>window.allowed}};window.allowed=true;</script><script src="https://assets.example.test/product-quiz/loader.js" defer></script></body></html>'});
  if(url.pathname.endsWith('/loader.js'))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'static/product-quiz/loader.js'),'utf8')});
  if(failAssets&&url.hostname==='assets.example.test')return route.fulfill({status:503});
  if(url.pathname.endsWith('/manifest.json'))return json({version:'a'.repeat(24),config:'config/'+ 'a'.repeat(24)+'.json',runtime:'runtime/'+'b'.repeat(24)+'.js',analytics_endpoint:'https://quiz.test/events'});
  if(url.pathname.includes('/runtime/'))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'static/product-quiz/runtime.js'),'utf8')});
  if(url.pathname.includes('/config/'))return json(config);
  if(url.pathname.endsWith('/catalogue.json'))return json({generated_at:new Date().toISOString(),sports:{Basketball:'catalogue/'+'c'.repeat(24)+'.json',Cricket:'catalogue/'+'d'.repeat(24)+'.json'}});
  if(url.pathname.includes('/catalogue/'))return json({products:url.pathname.includes('cccc')?products.filter(p=>p.sports.includes('Basketball')):products.filter(p=>p.sports.includes('Cricket'))});
  if(url.pathname==='/en-au/cart.js')return json({currency:'AUD'});
  if(url.pathname.startsWith('/en-au/products/')){const p=products.find(p=>url.pathname.endsWith('/'+p.handle+'.js'));return json({id:p.id.split('/').pop(),available,price:9900,variants:[{available:false,price:9900},{available,price:21900}],featured_image:p.image});}
  if(url.pathname==='/events'){events.push(JSON.parse(route.request().postData()));return json({ok:true});}
  return route.fulfill({status:404});
 });
 await page.goto('https://quiz.test/');await page.locator('#a').getByRole('button',{name:'Find your edition',exact:true}).waitFor();
 assert.equal(requests.filter(p=>p.endsWith('manifest.json')).length,0,'button placement must be lazy');
 await page.addScriptTag({url:'https://assets.example.test/product-quiz/loader.js'});
 assert.equal(await page.locator('#a').getByRole('button').count(),1,'repeat loader must not duplicate');
 const a=page.locator('#a');await a.getByRole('button',{name:'Find your edition',exact:true}).click();
 await a.getByRole('button',{name:'Basketball',exact:true}).click();await a.getByRole('button',{name:'Michael Jordan',exact:true}).click();await a.getByRole('button',{name:'Show me all',exact:true}).click();
 await a.getByRole('heading',{name:'Your editions',exact:true}).waitFor();
 assert.equal(await a.locator('article').count(),2);assert.match((await a.locator('article').allTextContents()).join(' '),/From A?\$219\.00/);
 const starts=events.filter(e=>e.type==='started').length;await page.keyboard.press('Escape');await a.getByRole('button',{name:'Find your edition',exact:true}).click();await a.getByRole('heading',{name:'Your editions',exact:true}).waitFor();assert.equal(events.filter(e=>e.type==='started').length,starts);
 await page.keyboard.press('Escape');
 // New section mounts, consent denied, and all unavailable products.
 await page.evaluate(()=>{window.allowed=false;const host=document.createElement('div');host.id='c';host.dataset.sportsCaveQuiz='button';document.body.append(host);document.dispatchEvent(new Event('shopify:section:load'));});
 available=false;const before=events.length,c=page.locator('#c');await c.getByRole('button',{name:'Find your edition',exact:true}).click();await c.getByRole('button',{name:'Cricket',exact:true}).click();await c.getByRole('heading',{name:'No exact match right now',exact:true}).waitFor();assert.equal(events.length,before);await page.keyboard.press('Escape');
 // First-load asset error must expose a compact collection fallback.
 await page.reload();failAssets=true;await page.locator('#a').getByRole('button',{name:'Find your edition',exact:true}).click();await page.locator('#a').getByRole('link',{name:'Browse editions'}).waitFor();
 assert.deepEqual(errors,[]);console.log('PASS: static desktop/mobile preview; modal keyboard/focus; deterministic identity matching; lazy/repeated/multiple/section initialization; market price and availability; consent; deduplication; load fallback.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1);});
