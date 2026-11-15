// Real Streamlit/browser; synthetic Shopify 40ms calls. No production claims.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const label=process.env.CRM_BENCH_LABEL||'before',port=label==='before'?18732:18731;
const flows=['abandoned','welcome','post_purchase','win_back','fulfilled'];
const stats=xs=>{xs=[...xs].sort((a,b)=>a-b);return {median:xs[Math.floor(xs.length/2)],p95:xs[Math.ceil(xs.length*.95)-1],samples:xs.length}};
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true}),result={fixture:'Actual Streamlit and Chrome; synthetic Shopify calls 40ms each and synthetic SQL responses; no production timings',flows:{}};
 try{for(const flow of flows){
  const page=await browser.newPage({viewport:{width:1100,height:950}});let frames=0;
  page.on('frameattached',()=>frames++);
  await page.route('**/*',r=>{const u=new URL(r.request().url());if(u.hostname==='127.0.0.1')return r.continue();if(u.hostname==='cdn.shopify.com')return r.fulfill({contentType:'image/png',body:fs.readFileSync('tests/fixtures/checkout_product_generated.png')});return r.abort()});
  const bar=()=>page.locator('[class*="st-key-crm-preview-toolbar-"]'),frame=()=>page.frameLocator('.st-key-crm-composer-preview iframe');
  const text=flow==='welcome'?'Fixture Welcome subscriber content':flow==='abandoned'?'A collector edition <safe> 0':'Fixture Ada Motorsport artwork';
  const ready=async t=>{await frame().getByText(t,{exact:true}).first().waitFor({timeout:20000});assert.equal(await page.getByTestId('stException').count(),0)};
  const start=performance.now();await page.goto('http://127.0.0.1:'+port+'/?flow='+flow);await bar().waitFor();const toolbar=performance.now()-start;
  await page.locator('.st-key-crm-composer-preview iframe').waitFor();const visible=performance.now()-start;await ready(text);const personalized=performance.now()-start;
  await page.waitForTimeout(600);
  const d={cold_toolbar_ms:toolbar,cold_first_iframe_ms:visible,cold_personalized_ms:personalized,operations:{}};
  for(const operation of ['reopen','html','device','save']){
   const samples=[];
   for(let i=0;i<20;i++){
    if(operation==='reopen'){
     await page.getByRole('button',{name:'Close/open editor',exact:true}).click();await page.getByText('Editor closed',{exact:true}).waitFor();
     await page.waitForTimeout(80); // Let the previous root widget trigger settle; outside timing.
     const t=performance.now();await page.getByRole('button',{name:'Close/open editor',exact:true}).dispatchEvent('click');await ready(operation==='html'?'Ultimate edited 19':text);samples.push(performance.now()-t);
     await page.waitForTimeout(80);
    }else if(operation==='html'){
     const area=page.getByRole('textbox',{name:'Fixture HTML'}),source=await area.inputValue();
     // Add plain text without changing dynamic bindings or the selected order.
     const edited=source.replace(/<p>Ultimate edited \d+<\/p>/g,'')+'<p>Ultimate edited '+i+'</p>';
     const t=performance.now();await area.fill(edited);await area.press('Tab');await ready('Ultimate edited '+i);samples.push(performance.now()-t);
    }else if(operation==='device'){
     const name=i%2?'Desktop':'Mobile',width=i%2?600:390,t=performance.now();await bar().locator('[class*="device_'+name+'"] button:visible').dispatchEvent('click');
     await page.waitForFunction(w=>Math.round(document.querySelector('.st-key-crm-composer-preview iframe')?.getBoundingClientRect().width||0)===w,width);samples.push(performance.now()-t);
    }else{
     const previous=await page.locator('#fixture-save-version').innerText();
     const t=performance.now();await page.getByRole('button',{name:'Save draft fixture',exact:true}).dispatchEvent('click');
     await page.waitForFunction(v=>document.querySelector('#fixture-save-version')?.textContent!==v,previous);await ready('Ultimate edited 19');samples.push(performance.now()-t);
    }
   }
   d.operations[operation]=stats(samples);
  }
  if(flow!=='abandoned'){
   const samples=[];
   for(let i=0;i<12;i++){
    const toggle=bar().getByRole('button',{name:/Previewing:/});if(await toggle.getAttribute('aria-expanded')!=='true')await toggle.click();const choice=page.getByTestId('stPopoverBody').getByRole('combobox');await choice.click();
    const t=performance.now();await page.getByRole('option',{name:i%2?/Fixture Ada/:/Fixture Grace/}).click();await page.keyboard.press('Escape');
    const expected=flow==='welcome'?'Fixture Welcome subscriber content':i%2?'Fixture Ada Motorsport artwork':'Fixture Grace Motorsport artwork';await ready(expected);
    await page.waitForFunction(n=>[...document.querySelectorAll('[class*="st-key-preview-customer-"] button')].some(b=>b.textContent.includes(n)),i%2?'Fixture Ada':'Fixture Grace');
    const elapsed=performance.now()-t;
    if(await toggle.getAttribute('aria-expanded')==='true')await toggle.click();
    samples.push(elapsed);if(i===0)d.uncached_switch_ms=samples[0];await page.waitForTimeout(200);
   }
   d.operations.cached_switch=stats(samples.slice(1));
  }
  const client=[];
  for(let i=0;i<20;i++){
   client.push(await frame().locator('body').evaluate((_,i)=>{
    const scope=[...parent.scEmailDrafts.keys()][0],state=parent.scEmailDrafts.get(scope),sections=SCPreview.clone(state.sections);
    sections[0].html=sections[0].html.replace(/<p>Client edited \d+<\/p>/g,'')+'<p>Client edited '+i+'</p>';
    const t=performance.now();SCPreview.publish(scope,sections,true);return performance.now()-t;
   },i));await ready('Client edited '+i);
  }
  d.operations.client_html_processing=stats(client);
  const ack=await page.locator('#fixture-counter-version').innerText();
  await page.getByRole('button',{name:'Fixture counters',exact:true}).click();
  await page.waitForFunction(v=>document.querySelector('#fixture-counter-version')?.textContent!==v,ack);
  d.calls=JSON.parse(await page.locator('#fixture-metrics').innerText());d.frames_attached=frames;
  if(flow!=='abandoned')assert.equal(d.calls.verified_examples.length,2,'Both switched customers must complete verification');
  d.browser_last_render_ms=await page.evaluate(()=>[...window.scEmailDrafts.values()].find(s=>s.model)?.lastRenderMs);
  assert.equal(Math.round((await bar().boundingBox()).height),40);result.flows[flow]=d;console.log(label+' '+flow+' '+JSON.stringify(d));await page.close();
 }}finally{await browser.close()}
 fs.writeFileSync('.tmp-preview-ultimate/'+label+'-browser.json',JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
