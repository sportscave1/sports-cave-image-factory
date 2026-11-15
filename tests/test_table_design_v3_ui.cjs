// Synthetic data only; all non-loopback requests are denied.
const {chromium} = require('playwright');
const fs = require('node:fs'), assert = require('node:assert/strict');
const out = 'docs/table-v3-evidence';
fs.mkdirSync(out, {recursive:true});
const results = {browsers:[], native:[], checkout:[], checks:[]};
const phases=(process.env.TABLE_V3_PHASES||'before,after').split(',');
const median = values => [...values].sort((a,b)=>a-b)[Math.floor(values.length/2)];
const source = (component,phase) => fs.readFileSync(`${phase==='before'?'tmp/table-v3-baseline/':''}components/${component}/index.html`,'utf8');
const epoch = new Date().toISOString();
const payload = n => ({columns:[1,2,3].map(i=>({id:''+i,label:'Email '+i,name:'Follow-up '+i,enabled:true})),
  server_now:epoch,read_at:epoch,phase:'READY',refresh_seconds:15,selected:[],
  rows:Array.from({length:n},(_,i)=>({key:'key-'+i,customer:'Collector '+i,created:'10 Oct',created_full:'10 October 2026',
    cells:[{label:'Sent ✓',tone:'green',reason:'Synthetic accepted receipt'},
      {label:'Waiting',tone:'gold',reason:'Synthetic pending state'},{label:'—',tone:'muted'}]}))});
async function mount(page,html,args) {
  await page.setContent('<iframe title="checkout" style="width:100%;height:730px;border:0"></iframe>');
  await page.evaluate(html=>{window.events=[];window.addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')window.events.push(e.data.value)});document.querySelector('iframe').srcdoc=html},html);
  const frame=page.frameLocator('iframe'); await frame.locator('#root').waitFor({state:'attached'});
  await page.waitForFunction(()=>document.querySelector('iframe').contentDocument?.readyState==='complete');
  await page.evaluate(args=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args},'*'),args);
  await frame.locator('tbody tr').first().waitFor();return frame;
}
async function native(page, phase, channel) {
  const started=performance.now();
  await page.goto(process.env['TABLE_V3_'+phase.toUpperCase()+'_URL']);
  await page.locator('#table-v3-state').waitFor({state:'attached'});
  assert.equal(await page.getByTestId('stException').count(),0);
  const initial=performance.now()-started;
  for (const count of [50,250,500,1000]) {
    await page.getByTestId('stSelectbox').filter({hasText:'Records'}).getByRole('combobox').click();
    await page.getByRole('option',{name:String(count),exact:true}).click();
    await page.locator(`#table-v3-state[data-count="${count}"]`).waitFor({state:'attached'});
    const grid=page.getByTestId('stDataFrame').first();
    const box=await grid.boundingBox();
    const sort=[];
    for(let i=0;i<5;i++) { const t=performance.now();await page.mouse.click(box.x+100,box.y+18);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));sort.push(performance.now()-t); }
    const t=performance.now();await page.getByRole('textbox',{name:'Search fixture records'}).fill('KEY-0001');
    await page.getByRole('textbox',{name:'Search fixture records'}).press('Enter');
    await page.locator('#table-v3-state[data-count="1"]').waitFor({state:'attached'});
    const filter=performance.now()-t;
    await page.getByRole('textbox',{name:'Search fixture records'}).fill('');
    await page.getByRole('textbox',{name:'Search fixture records'}).press('Enter');
    await page.locator(`#table-v3-state[data-count="${count}"]`).waitFor({state:'attached'});
    const render=Number(await page.locator('#table-v3-state').getAttribute('data-render-ms'));
    const scrollStart=performance.now();await grid.hover();await page.mouse.wheel(0,600);await page.evaluate(()=>new Promise(r=>requestAnimationFrame(r)));
    results.native.push({phase,channel,count,initial_ms:initial,python_render_ms:render,sort_roundtrip_median_ms:median(sort),filter_roundtrip_ms:filter,scroll_roundtrip_ms:performance.now()-scrollStart});
  }
  for(const width of [1440,390]){
    await page.setViewportSize({width,height:1000});
    await page.screenshot({path:`${out}/${channel}-${phase}-native-${width}.png`,fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('.sc-activity-table-wrap').screenshot({path:`${out}/${channel}-${phase}-activity.png`});
  await page.locator('.prodigi-reference-scroll').screenshot({path:`${out}/${channel}-${phase}-fulfilment.png`});
  if(phase==='after') {
    assert.equal(await page.locator('.prodigi-reference-scroll th').first().evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(243, 242, 236)');
    assert.equal(await page.getByTestId('stTable').locator('th').first().evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(243, 242, 236)');
  }
  // Search down to one known record, then select/open it. This verifies identity after filtering.
  await page.getByRole('textbox',{name:'Search fixture records'}).fill('KEY-0001');
  await page.getByRole('textbox',{name:'Search fixture records'}).press('Enter');
  await page.locator('#table-v3-state[data-count="1"]').waitFor({state:'attached'});
  const grid=page.getByTestId('stDataFrame').first(), box=await grid.boundingBox();
  let t=performance.now();await page.mouse.click(box.x+16,box.y+52);
  await page.getByText('Selected: KEY-0001',{exact:true}).waitFor();const selection=performance.now()-t;
  t=performance.now();await page.getByRole('button',{name:'Open selected record'}).click();
  await page.getByRole('dialog').getByTestId('stDataFrame').waitFor();const popup=performance.now()-t;
  await page.getByRole('dialog').getByRole('button',{name:'Close'}).click();
  await page.getByRole('dialog').waitFor({state:'hidden'});
  // Start a fresh fixture session for the independent editor check. The popup
  // timings above exclude this reload and remain separate from editing timings.
  await page.reload();await page.locator('#table-v3-state').waitFor({state:'attached'});
  const editor=page.getByTestId('stDataFrame').nth(1);
  await editor.scrollIntoViewIfNeeded();
  await editor.locator('canvas').first().focus();
  t=performance.now();await page.keyboard.press('Control+Home');
  await page.keyboard.press('ArrowRight');await page.keyboard.press('ArrowRight');await page.keyboard.press('Enter');
  const input=page.locator('.gdg-input');await input.fill('987.5');await input.press('Tab');
  await page.getByText('Edited amount: 987.5',{exact:true}).waitFor();
  await page.getByText('Local saves: 1',{exact:true}).waitFor();
  const edit=performance.now()-t;
  results.checks.push({channel,phase,selection_ms:selection,popup_ms:popup,edit_and_save_ms:edit,identity:'KEY-0001'});
  assert.equal(await page.getByTestId('stException').count(),0);
}
async function orders(page,channel) {
  await page.goto(process.env.TABLE_V3_ORDERS_URL);
  const grid=page.getByTestId('stDataFrame').first();await grid.waitFor();
  const box=await grid.boundingBox();await page.mouse.click(box.x+16,box.y+51);
  await page.getByText('1 selected',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Preview Certificate',exact:true}).click();
  await page.getByText('Fixture action on 1 selected units').waitFor();
  const input=page.getByRole('textbox',{name:'Search orders',exact:true});
  await input.fill('#SC3049');await input.press('Enter');
  await page.locator('#orders-fixture-state[data-query="#SC3049"][data-count="1"]').waitFor({state:'attached'});
  for(const width of [1440,390]) {
    await page.setViewportSize({width,height:1000});
    await page.screenshot({path:`${out}/${channel}-after-orders-${width}.png`,fullPage:true});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
  }
  assert.equal(await page.getByTestId('stException').count(),0);
  results.checks.push({channel,orders:'selection, mocked certificate action, search, desktop/narrow passed'});
  await page.setViewportSize({width:1440,height:1000});
}
async function customSkins(page,channel) {
  const markups={
    daily_planner:'<div class="table-wrap"><table><thead><tr><th>Task</th><th>Owner</th><th>Status</th></tr></thead><tbody><tr><td>Review artwork</td><td>Operator</td><td>Completed</td></tr><tr><td>Prepare product</td><td>Designer</td><td>Pending</td></tr></tbody></table></div><div class="task-header"><span></span><span>Task</span><span>Details / outcome required</span><span>Allocated</span><span>Status</span><span>Timer</span></div><div class="task-row"><span>1</span><input value="Prepare product"><textarea>Retain multiline notes</textarea><input value="30m"><span>Pending</span><button>Save</button></div>',
    files_window:'<div class="details-header visible"><span>Name</span><span>Size</span><span>Type</span><span>Modified</span><span>Status</span></div><div class="items view-details"><div class="file-item"><span class="details-name">Artwork.png</span><span class="detail-cell">2 MB</span><span class="detail-cell">PNG image</span><span class="detail-modified">10 Oct 2026</span><span>Ready</span></div><div class="file-item selected"><span class="details-name">Selected artwork.png</span><span>1 MB</span><span>PNG image</span><span>10 Oct 2026</span><span>Ready</span></div></div>',
    files_chunk_uploader:'<div class="uploads"><div class="upload-row"><span class="cell">Artwork.png</span><span class="cell">2 MB</span><span class="cell">Product assets</span><span class="cell status">Uploading 50%</span><span class="cell">50%</span><span class="cell"><button class="mini">Cancel</button></span></div></div>'
  };
  for(const [component,markup] of Object.entries(markups)) for(const phase of phases){
    const raw=source(component,phase),styles=[...raw.matchAll(/<style\b[^>]*>[\s\S]*?<\/style>/g)].map(m=>m[0]).join('');
    const htmlTag=raw.match(/<html[^>]*>/)[0];
    // CSS regression harness only; no network or component backend is executed.
    await page.setContent(`${htmlTag}<head>${styles}</head><body><main style="padding:16px;max-width:100%;overflow:auto">${markup}<button id="unrelated">Unrelated control</button></main></body></html>`);
    for(const width of [1440,390]){
      await page.setViewportSize({width,height:500});
      await page.screenshot({path:`${out}/${channel}-${phase}-${component}-${width}.png`,fullPage:true});
      assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
    }
    if(component==='files_window'&&phase==='after')assert.equal(await page.locator('.file-item.selected').evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(238, 231, 215)');
    results.checks.push({channel,component,phase,css_fixture:'desktop and narrow overflow passed'});
  }
  await page.setViewportSize({width:1440,height:1000});
}
async function checkout(page,channel) {
  for(const phase of phases) for(const count of [50,250,500,1000]) {
    const frame=await mount(page,source('crm_checkout_table',phase),payload(count));
    const metrics=await frame.locator('body').evaluate(()=>{
      const times=[];for(let i=0;i<41;i++){const t=performance.now();render();document.body.offsetHeight;times.push(performance.now()-t)}
      return {median_render_ms:times.slice(1).sort((a,b)=>a-b)[20],elements:document.querySelectorAll('*').length,row_height:document.querySelector('tbody tr').getBoundingClientRect().height};
    });
    assert.equal(await frame.locator('tbody tr').count(),50);
    assert.equal(metrics.row_height,34);
    await frame.getByRole('checkbox',{name:'Select Collector 0',exact:true}).check();
    await frame.getByRole('button',{name:'Details Collector 0',exact:true}).click();
    await page.waitForFunction(()=>window.events.some(e=>e.detail==='key-0'&&e.selected.includes('key-0')));
    if(count>50){await frame.getByRole('button',{name:'Next',exact:true}).click();await frame.getByRole('button',{name:'Details Collector 50',exact:true}).waitFor();}
    if(count===50) for(const width of [1440,390]){
      await page.setViewportSize({width,height:900});
      await page.screenshot({path:`${out}/${channel}-${phase}-checkout-${width}.png`,fullPage:true});
      assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth),true);
      if(phase==='after') assert.equal(await frame.locator('tbody tr').first().locator('td').first().evaluate(e=>getComputedStyle(e).backgroundColor),'rgb(238, 231, 215)');
    }
    await page.setViewportSize({width:1440,height:1000});
    results.checkout.push({channel,phase,count,...metrics});
  }
}
(async()=>{
 for(const channel of (process.env.TABLE_V3_BROWSERS||'chrome,msedge').split(',')){
  const browser=await chromium.launch({channel,headless:true,timeout:25000});
  try {
   results.browsers.push({channel,version:browser.version()});
   const context=await browser.newContext({viewport:{width:1440,height:1000}});
   await context.route('**/*',r=>['127.0.0.1','localhost'].includes(new URL(r.request().url()).hostname)?r.continue():r.abort());
   const page=await context.newPage();page.setDefaultTimeout(25000);
   try {
    if(!process.env.TABLE_V3_CSS_ONLY){for(const phase of phases) await native(page,phase,channel);await checkout(page,channel);await orders(page,channel);}
    await customSkins(page,channel);
   }
   catch(error){await page.screenshot({path:`tmp/table-v3-${channel}-failure.png`,fullPage:true});fs.writeFileSync(`tmp/table-v3-${channel}-failure.txt`,await page.locator('body').innerText());fs.writeFileSync(`tmp/table-v3-${channel}-failure.html`,await page.content());throw error;}
   await context.close();
  } finally {await browser.close();fs.writeFileSync(`${out}/${process.env.TABLE_V3_CSS_ONLY?'css-results':'browser-results'}.json`,JSON.stringify(results,null,2));}
 }
 console.log('Table V3 browser checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
