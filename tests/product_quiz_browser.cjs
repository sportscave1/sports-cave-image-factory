/* Fully mocked storefront and static fixture. No OS server or provider credentials. */
const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'..');
const out=process.env.PRODUCT_QUIZ_PREVIEW_DIR || path.join(root,'tmp/product-quiz-preview');
const config={
  questions:['sport','subject','preference'].map(id=>({id,label:'Which story speaks to you?',enabled:true,answers:[]})),
  appearance:{title:'Legacy saved title',intro:'Legacy intro',accent:'#c6a76b',background:'#0b0b0c',text:'#f5f0e6'},
  rules:{max_results:3,allow_broader:true},aliases:{},collections:{basketball:'Basketball'}
};
const products=[
  {id:'gid://shopify/Product/1',handle:'jordan',title:'Jordan Legacy',sports:['Basketball'],subjects:['Michael Jordan'],keywords:['Chicago Bulls'],preferences:['Legacy'],featured:0,next_number:23,edition_total:100},
  {id:'gid://shopify/Product/2',handle:'rivals',title:'Rivals',sports:['Basketball'],subjects:['Michael Jordan','Kobe Bryant'],keywords:['Chicago Bulls','Los Angeles Lakers'],preferences:['Rivalry'],featured:1,next_number:16,edition_total:100},
  {id:'gid://shopify/Product/3',handle:'kobe',title:'Kobe Legacy',sports:['Basketball'],subjects:['Kobe Bryant'],keywords:['Los Angeles Lakers'],preferences:['Legacy'],featured:3,next_number:7,edition_total:100},
  {id:'gid://shopify/Product/4',handle:'warne',title:'Warne',sports:['Cricket'],subjects:['Shane Warne'],preferences:[],featured:0,next_number:2,edition_total:100}
];
const sportPrompt='What sports do you support?';
const resultHeading='We have found your edition';
const launchLabel='Find your next edition';
const click=(scope,name)=>scope.getByRole('button',{name,exact:true}).click();
const heading=(scope,name)=>scope.getByRole('heading',{name,exact:true}).waitFor();
async function sport(scope, term, option) {
  const input=scope.getByRole('combobox',{name:sportPrompt});
  await input.fill(term);
  if (option) await scope.getByRole('option',{name:option,exact:true}).click();
  else await input.press('Enter');
}
(async()=>{
  const browser=await chromium.launch({headless:true,channel:process.env.PRODUCT_QUIZ_BROWSER_CHANNEL || 'chrome'});
  try {
    const page=await browser.newPage({viewport:{width:1440,height:1080}});
    const errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(pathToFileURL(path.join(out,'index.html')).href);
    const inline=page.locator('#inline');
    await sport(inline,'nba','Basketball (NBA)');
    await heading(inline,'Any other favourite sports?');
    await click(inline,'Yes');
    await sport(inline,'formlua one','Formula One');
    await click(inline,'No');
    await heading(inline,'Which team do you support?');
    await click(inline,'No favourite');
    await heading(inline,'Which driver or team do you support?');
    await inline.getByRole('combobox').fill('Lewis Hamilton');
    await inline.getByRole('combobox').press('Enter');
    await click(inline,'Defining moment');
    await heading(inline,resultHeading);
    assert.equal(await inline.locator('article').count(),1);
    assert.match(await inline.locator('article').innerText(),/Lights Out/);

    const modal=page.locator('#button');
    const launch=modal.getByRole('button',{name:'Find your edition ↗'});
    await launch.click();
    await heading(modal,launchLabel);
    assert.equal(await modal.getByRole('listbox').count(),0);
    await modal.getByRole('combobox').fill('soccer');
    await modal.getByRole('option',{name:'Football',exact:true}).waitFor();
    assert.ok((await modal.locator('dialog').boundingBox()).width<=430);
    await page.screenshot({path:path.join(out,'desktop.png')});
    await page.keyboard.press('Escape');
    assert.equal(await modal.locator('dialog').evaluate(dialog=>dialog.open),true);
    await page.keyboard.press('Escape');
    assert.equal(await modal.locator('dialog').evaluate(dialog=>dialog.open),false);
    assert.equal(await modal.evaluate(host=>host.shadowRoot.activeElement?.textContent),'Find your edition ↗');
    await page.setViewportSize({width:390,height:844});
    await launch.click();
    await sport(modal,'synchronised swimming');
    await heading(modal,'Any other favourite sports?');
    assert.match(await modal.locator('dialog').innerText(),/don’t have an edition/);
    await click(modal,'Yes');
    const sportInput=modal.getByRole('combobox',{name:sportPrompt});
    await sportInput.fill('f1');
    await sportInput.press('ArrowDown');
    await page.screenshot({path:path.join(out,'mobile.png')});
    await sportInput.press('Enter');
    await click(modal,'No');
    await heading(modal,'Which driver or team do you support?');
    assert.ok((await modal.locator('dialog').boundingBox()).width<=390);
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
    await page.keyboard.press('Escape');

    const requests=[],events=[];
    const unavailable=new Set();
    let failAssets=false, updatedNumber=false;
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      requests.push(url.pathname);
      const json=data=>route.fulfill({contentType:'application/json',body:JSON.stringify(data),headers:{'Access-Control-Allow-Origin':'*'}});
      if(url.pathname==='/')return route.fulfill({contentType:'text/html',body:'<html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><body><div id="a" data-sports-cave-quiz="button"></div><div id="b" data-sports-cave-quiz="button"></div><script>window.Shopify={routes:{root:"/en-au/"},customerPrivacy:{analyticsProcessingAllowed:()=>window.allowed}};window.allowed=true;</script><script src="https://assets.example.test/product-quiz/loader.js" defer></script></body></html>'});
      if(url.pathname.endsWith('/loader.js'))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'static/product-quiz/loader.js'),'utf8')});
      if(failAssets&&url.hostname==='assets.example.test')return route.fulfill({status:503});
      if(url.pathname.endsWith('/manifest.json'))return json({version:'a'.repeat(24),config:'config/'+ 'a'.repeat(24)+'.json',runtime:'runtime/'+'b'.repeat(24)+'.js',analytics_endpoint:'https://quiz.test/events'});
      if(url.pathname.includes('/runtime/'))return route.fulfill({contentType:'text/javascript',body:fs.readFileSync(path.join(root,'static/product-quiz/runtime.js'),'utf8')});
      if(url.pathname.includes('/config/'))return json(config);
      const shard=letter=>'catalogue/'+letter.repeat(24)+'.json';
      if(url.pathname.endsWith('/catalogue.json'))return json({
        generated_at:new Date().toISOString(),
        sports:{Basketball:shard('c'),Cricket:shard('d')},
        extra_pages:{Basketball:[shard(updatedNumber ? 'f' : 'e')]},
        sport_options:{Basketball:['NBA'],Cricket:['BBL'],Football:['soccer']}
      });
      if(url.pathname.endsWith(shard('c')))return json({products:[products[0],products[1]]});
      if(url.pathname.endsWith(shard('d')))return json({products:[products[3]]});
      if(url.pathname.endsWith(shard('e')))return json({products:[products[2]]});
      if(url.pathname.endsWith(shard('f')))return json({products:[{...products[2],next_number:8}]});
      if(url.pathname==='/en-au/cart.js')return json({currency:'AUD'});
      if(url.pathname.startsWith('/en-au/products/')){
        const product=products.find(p=>url.pathname.endsWith('/'+p.handle+'.js'));
        const available=!unavailable.has(product.handle);
        return json({id:product.id.split('/').pop(),available,variants:[{available:false,price:9900},{available,price:21900}]});
      }
      if(url.pathname==='/events'){events.push(JSON.parse(route.request().postData()));return json({ok:true});}
      return route.fulfill({status:404});
    });
    await page.goto('https://quiz.test/');
    const a=page.locator('#a');
    await a.getByRole('button',{name:launchLabel,exact:true}).waitFor();
    assert.equal(requests.filter(p=>p.endsWith('manifest.json')).length,0);
    await page.addScriptTag({url:'https://assets.example.test/product-quiz/loader.js'});
    assert.equal(await a.getByRole('button').count(),1);
    await click(a,launchLabel);
    assert.doesNotMatch(await a.locator('dialog').innerText(),/Legacy intro|Question 1/);
    await sport(a,'nba');
    await click(a,'No');
    await a.getByRole('combobox',{name:'Which team do you support?'}).fill('Lakers');
    await a.getByRole('combobox').press('Enter');
    await heading(a,'Which story speaks to you?');
    updatedNumber=true;
    await click(a,'Legacy');
    await heading(a,resultHeading);
    assert.equal(await a.locator('article').count(),1);
    assert.match(await a.locator('article').innerText(),/Kobe Legacy[\s\S]*8\/100[\s\S]*From A?\$219\.00/);
    assert.equal(await a.getByRole('link',{name:'Collect now'}).getAttribute('href'),'/en-au/products/kobe');
    assert.ok(requests.some(url=>url.endsWith('/'+'e'.repeat(24)+'.json')));
    assert.ok(requests.some(url=>url.endsWith('/'+'f'.repeat(24)+'.json')));
    assert.ok(events.some(event=>event.step==='more'));
    assert.ok(!events.some(event=>JSON.stringify(event).includes('Lakers')));
    const starts=events.filter(event=>event.type==='started').length;
    await page.keyboard.press('Escape');
    await click(a,launchLabel);
    await heading(a,resultHeading);
    assert.equal(events.filter(event=>event.type==='started').length,starts);
    unavailable.add('kobe');
    await click(a,'← Back');
    await click(a,'Legacy');
    await heading(a,resultHeading);
    assert.match(await a.locator('article').innerText(),/Rivals/);
    await page.keyboard.press('Escape');

    await page.evaluate(()=>{
      window.allowed=false;
      const host=document.createElement('div');
      host.id='c';
      host.dataset.sportsCaveQuiz='button';
      document.body.append(host);
      document.dispatchEvent(new Event('shopify:section:load'));
    });
    unavailable.add('warne');
    const before=events.length,c=page.locator('#c');
    await click(c,launchLabel);
    await sport(c,'bbl');
    await click(c,'No');
    await click(c,'No favourite');
    await click(c,'Lowest edition number');
    await heading(c,'No edition available right now');
    assert.equal(events.length,before);
    await page.keyboard.press('Escape');

    await page.reload();
    failAssets=true;
    await click(a,launchLabel);
    await a.getByRole('link',{name:'Browse editions'}).waitFor();
    assert.deepEqual(errors,[]);
    console.log('PASS: compact desktop and mobile, aliases and typos, keyboard and focus, unsupported and multiple sports, sport-specific prompts, tag matching, catalogue pages, one numbered result, market fallback, consent and asset fallback.');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exit(1);});
