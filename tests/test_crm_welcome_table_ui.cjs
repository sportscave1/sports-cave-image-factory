// Offline production component with synthetic records; no application startup.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('components/crm_checkout_table/index.html','utf8');
const labels=['Email','Consent','Flow','Purchased','Source','Email 1','Email 2'];
const payload={table_label:'Marketing subscribers',date_label:'Subscribed',compact_columns:true,
 columns:labels.map(label=>({label,name:label,enabled:true,visible:['Flow','Purchased'].includes(label)})),
 refresh_seconds:0,selected:[],server_now:'2026-10-14T00:00:00Z',
 rows:[{key:'subscriber',customer:'VeryLongCustomerName'.repeat(12),created:'14 Oct 2026',
 created_full:'14 October 2026',cells:['hidden@example.test','SUBSCRIBED','Not enrolled','Yes','Shopify','Sent','Waiting'].map(label=>({label,tone:'muted'}))}]};
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 for(const width of [1440,768,390,320]){
  const page=await browser.newPage({viewport:{width,height:900}});await page.route('**/*',r=>r.abort());
  await page.setContent('<iframe style="width:100%;height:800px;border:0"></iframe>');
  await page.evaluate(source=>{window.events=[];window.addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')window.events.push(e.data.value)});document.querySelector('iframe').srcdoc=source},html);
  await page.waitForFunction(()=>document.querySelector('iframe').contentDocument?.readyState==='complete');
  const frame=page.frameLocator('iframe');
  const update=async args=>page.evaluate(args=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args},'*'),args);
  await update(payload);await frame.locator('tbody tr').waitFor();
  assert.deepEqual(await frame.locator('th').allTextContents(),['','Customer','Subscribed','Flow','Purchased']);
  assert.deepEqual((await frame.locator('tbody td').allTextContents()).slice(2),['14 Oct 2026','Not enrolled','Yes']);
  assert.equal(await frame.locator('.wrap').evaluate(e=>e.scrollWidth>e.clientWidth),false,`horizontal overflow at ${width}`);
  assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await frame.locator('tbody input').check();await frame.locator('.customer').click();
  await page.waitForFunction(()=>window.events.some(e=>e.detail==='subscriber'&&e.selected.includes('subscriber')));
  await update({...payload,rows:[{...payload.rows[0],cells:payload.rows[0].cells.map((c,i)=>i===2?{...c,label:'ACTIVE'}:c)}]});
  await frame.locator('tbody td').nth(3).getByText('ACTIVE',{exact:true}).waitFor();
  // A different audience retains its full columns and existing layout.
  await update({...payload,compact_columns:false,columns:payload.columns.map(({visible,...c})=>c)});
  await frame.getByRole('columnheader',{name:'Consent',exact:true}).waitFor();
  assert.equal(await frame.locator('th').count(),10);
  assert.equal(await frame.locator('.compact-columns').count(),0);
  await page.close();console.log(`Welcome table passed at ${width}px`);
 }
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
