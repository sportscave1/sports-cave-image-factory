// Offline shared table with actual Welcome projection; no customer data/network.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const data=JSON.parse(execFileSync(process.env.CRM_TEST_PYTHON||'python',['-B','-c',`
import json
from tests.test_crm_welcome_stages import fixture,projected,AT
row,record=fixture(5)
columns,rows=projected(row,record)
print(json.dumps(dict(columns=columns,rows=rows,server_now=AT.isoformat(),read_at=AT.isoformat(),refresh_seconds=15,table_label='Marketing subscribers',date_label='Subscribed',state_key='welcome-fixture'),default=str))
`],{encoding:'utf8'}));
const html=fs.readFileSync('components/crm_checkout_table/index.html','utf8');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage();await page.route('**/*',r=>r.abort());
 await page.setContent('<iframe title="shared flow table" style="width:100%;height:650px;border:0"></iframe>');
 await page.evaluate(html=>{window.events=[];window.addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')window.events.push(e.data.value)});document.querySelector('iframe').srcdoc=html},html);
 const frame=page.frameLocator('iframe');await frame.locator('#root').waitFor({state:'attached'});
 await page.waitForFunction(()=>document.querySelector('iframe').contentDocument?.readyState==='complete');
 async function update(payload){await page.evaluate(args=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args},'*'),payload);}
 await update(data);await frame.getByRole('button',{name:'Details Stage fixture',exact:true}).waitFor();
 assert.equal(await frame.locator('th').count(),10);
 assert.match(await frame.locator('th').nth(7).innerText(),/7 days after confirmed subscription/);
 const scheduled=frame.locator('tbody td').nth(5);
 assert.match(await scheduled.innerText(),/Scheduled · 1h 0m\nScheduled 17 Oct 2026 12:00 AEDT/);
 await frame.locator('body').evaluate(()=>{window.originalRow=document.querySelector('tbody tr');clockAnchor-=2000;tick(false)});
 assert.match(await scheduled.innerText(),/Scheduled · 59m 58s/);
 await frame.getByRole('checkbox',{name:'Select Stage fixture',exact:true}).check();
 const accepted=structuredClone(data);accepted.selected=['customer'];accepted.rows[0].cells[5]={label:'Sent ✓',tone:'green',detail:'Sent 17 Oct 2026 11:00 AEDT',reason:'Provider accepted receipt'};
 await update(accepted);await frame.getByText('Sent ✓',{exact:true}).waitFor();
 assert.equal(await frame.locator('body').evaluate(()=>window.originalRow===document.querySelector('tbody tr')),true);
 assert.equal(await frame.getByRole('checkbox',{name:'Select Stage fixture',exact:true}).isChecked(),true);
 assert.equal(await scheduled.getAttribute('title'),'Provider accepted receipt');
 for(const width of [1440,390,320]){
  await page.setViewportSize({width,height:850});
  assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth),false);
  if(width<600)assert.equal(await frame.locator('.wrap').evaluate(e=>e.scrollWidth>e.clientWidth),true);
  await frame.locator('.wrap').evaluate(e=>e.scrollLeft=e.scrollWidth);
  assert.ok(await frame.locator('tbody td').nth(1).evaluate(e=>e.getBoundingClientRect().left)<35);
  if(process.env.CRM_STAGE_EVIDENCE)await page.screenshot({path:process.env.CRM_STAGE_EVIDENCE+'/welcome-'+width+'.png'});
 }
 await frame.locator('body').evaluate(()=>{lastPoll=performance.now()-16000;tick();tick()});
 assert.equal(await page.evaluate(()=>window.events.filter(e=>e.refresh).length),1);
 console.log('PASS shared Welcome stage headers, timestamps/countdown, receipt refresh, retained nodes/selection, bounded poll, sticky scrolling at 1440/390/320');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
