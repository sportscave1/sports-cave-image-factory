const {chromium}=require('playwright'),fs=require('node:fs');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});const result={fixture:'Real Streamlit UI; synthetic Shopify responses with 40ms latency; no production timings',versions:{}};
 try{for(const [label,port]of [['before',18732],['after',18731]]){
  const page=await browser.newPage({viewport:{width:1100,height:950}});
  await page.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  const frame=()=>page.frameLocator('.st-key-crm-composer-preview iframe');
  const t=performance.now();await page.goto('http://127.0.0.1:'+port);await frame().getByText('Fixture Ada Motorsport artwork',{exact:true}).first().waitFor({timeout:20000});
  const data={cold_browser_ms:performance.now()-t};await page.waitForTimeout(400);
  const canvas=await page.locator('.st-key-crm-composer-preview').boundingBox(),iframe=await page.locator('.st-key-crm-composer-preview iframe').boundingBox();data.header_space_px=iframe.y-canvas.y;
  await page.getByRole('button',{name:'Close/open editor'}).click();const warm=performance.now();await page.getByRole('button',{name:'Close/open editor'}).click();await frame().getByText('Fixture Ada Motorsport artwork',{exact:true}).first().waitFor();data.warm_reopen_ms=performance.now()-warm;
  if(label==='after')await page.locator('[class*="st-key-crm-preview-toolbar-"]').getByRole('button',{name:/Previewing:/}).click();
  const choice=label==='after'?page.getByTestId('stPopoverBody').getByRole('combobox'):page.getByTestId('stSelectbox').filter({has:page.getByText('Example customer',{exact:true})}).getByRole('combobox');
  await choice.waitFor();await choice.click();const switched=performance.now();await page.getByRole('option',{name:/Fixture Grace/}).click();if(label==='after'){await page.keyboard.press('Escape');const toggle=page.locator('[class*="st-key-crm-preview-toolbar-"]').getByRole('button',{name:/Previewing:/});if(await toggle.getAttribute('aria-expanded')==='true')await toggle.click();}await frame().getByText('Fixture Grace Motorsport artwork',{exact:true}).first().waitFor();data.customer_switch_ms=performance.now()-switched;
  await page.waitForTimeout(500); // Compare warm editing after background verification completes.
  const area=page.getByRole('textbox',{name:'Fixture HTML'});const source=await area.inputValue();const edited=performance.now();await area.fill(source.replace('Your artwork, chosen by you','Benchmark edited heading'));await area.press('Tab');await frame().getByText('Benchmark edited heading',{exact:true}).waitFor();data.html_edit_ms=performance.now()-edited;
  await page.getByRole('button',{name:'Fixture counters'}).click();data.calls=JSON.parse(await page.locator('#fixture-metrics').innerText());result.versions[label]=data;await page.close();
 }}finally{await browser.close()}
 fs.writeFileSync('.tmp-preview-performance/browser-before-after.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exit(1)});
