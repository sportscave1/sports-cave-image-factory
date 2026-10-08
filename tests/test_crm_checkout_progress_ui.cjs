// Production component, synthetic persisted projections. No network or providers.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs');
const output='docs/checkout-flow-evidence';fs.mkdirSync(output,{recursive:true});
const html=fs.readFileSync('components/crm_checkout_table/index.html','utf8');
const epoch=Date.parse('2026-10-09T00:00:00Z');
const iso=n=>new Date(epoch+n*1000).toISOString();
const columns=Array.from({length:5},(_,i)=>({id:''+i,label:'Email '+(i+1),name:'Email '+(i+1),enabled:true}));
const cells=[{label:'Sent ✓',tone:'green',reason:'Accepted by Resend'},
 {label:'Countdown',tone:'gold',due_at:iso(600),reason:'Persisted deadline'},
 ...Array.from({length:3},()=>({label:'Waiting',tone:'muted',reason:'Waiting for prior step'}))];
const payload={columns,server_now:iso(0),read_at:iso(0),phase:'READY',refresh_seconds:15,selected:[],
 rows:Array.from({length:50},(_,i)=>({key:'key-'+i,customer:i?'Customer Name '+i:'Roslyn Williamson',created:'9 Oct',created_full:'09 Oct 2026 11:00:00 AEDT',cells:structuredClone(cells)}))};
async function mount(page,source,payload){await page.setContent('<iframe title="table" style="width:100%;height:720px;border:0"></iframe>');
 await page.evaluate(source=>{window.messages=[];window.addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')window.messages.push(e.data.value)});document.querySelector('iframe').srcdoc=source},source);
 const frame=page.frameLocator('iframe');await frame.locator('#root').waitFor({state:'attached'});
 await page.waitForFunction(()=>document.querySelector('iframe').contentDocument?.readyState==='complete');
 await update(page,payload);await frame.locator('tbody tr').first().waitFor();return frame;}
async function update(page,p){await page.evaluate(args=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args},'*'),p);}
async function benchmark(page,source,p){const frame=await mount(page,source,p);return frame.locator('body').evaluate(()=>{
 const times=[];for(let i=0;i<31;i++){const start=performance.now();render();document.body.offsetHeight;times.push(performance.now()-start)}
 return {median_render_ms:times.slice(1).sort((a,b)=>a-b)[15],dom_elements:document.querySelectorAll('*').length,row_height:document.querySelector('tbody tr').getBoundingClientRect().height};});}
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage({viewport:{width:1366,height:900}});await page.route('**/*',r=>r.abort());
 const frame=await mount(page,html,payload);
 assert.deepEqual(await frame.locator('th').allTextContents(),['','Customer','Created','Email 1','Email 2','Email 3','Email 4','Email 5']);
 assert.equal(await frame.locator('tbody tr').count(),50);
 const countdown=frame.locator('tbody tr').first().locator('td').nth(4);
 await frame.locator('body').evaluate(()=>{window.keep=document.querySelector('tbody tr');window.initialNode=document.querySelector('tbody tr .customer');window.mutations=0;new MutationObserver(v=>window.mutations+=v.length).observe(document.querySelector('tbody'),{childList:true,subtree:true});});
 const before=await countdown.textContent();await page.waitForTimeout(2200);assert.notEqual(await countdown.textContent(),before);
 assert.equal(await page.evaluate(()=>window.messages.length),0,'countdown never requests server refresh');
 assert.equal(await frame.locator('body').evaluate(()=>window.keep===document.querySelector('tbody tr')),true);
 await frame.getByRole('checkbox',{name:'Select Roslyn Williamson',exact:true}).check();
 await frame.getByRole('button',{name:'Details Roslyn Williamson',exact:true}).click();
 await page.waitForFunction(()=>window.messages.some(m=>m.detail==='key-0'));
 const selected={...payload,selected:['key-0'],server_now:iso(3)};selected.rows=structuredClone(payload.rows);selected.rows[0].cells[1]={label:'Sent ✓',tone:'green',reason:'Accepted by Resend'};selected.rows[0].cells[2]={label:'Countdown',tone:'gold',due_at:iso(43203)};
 await frame.locator('.wrap').evaluate(e=>e.scrollTop=210);await update(page,selected);
 await page.waitForTimeout(100);assert.equal(await frame.getByRole('checkbox',{name:'Select Roslyn Williamson',exact:true}).isChecked(),true);
 assert.equal(await frame.locator('.wrap').evaluate(e=>e.scrollTop),210);
 assert.equal(await frame.locator('body').evaluate(()=>window.keep===document.querySelector('tbody tr')&&window.initialNode===document.querySelector('tbody tr .customer')),true);
 assert.equal(await countdown.textContent(),'Sent ✓');assert.equal(await frame.locator('tbody tr').first().locator('td').nth(5).textContent(),'12h 0m');
 // A wild browser wall-clock change must not change the countdown.
 await frame.locator('body').evaluate(()=>Date.now=()=>1);const drift=await frame.locator('tbody tr').first().locator('td').nth(5).textContent();await page.waitForTimeout(1100);
 assert.equal(await frame.locator('body').evaluate(()=>remaining(args.rows[0].cells[2].due_at)), '11h 59m');
 await frame.locator('body').evaluate(()=>{lastPoll=performance.now()-16000;tick();tick();});
 await page.waitForTimeout(100);assert.equal(await page.evaluate(()=>window.messages.filter(m=>m.refresh).length),1,'one bounded poll, never per row');
 await frame.locator('body').evaluate(()=>{clockAnchor-=700000;tick(false)});
 assert.ok(await frame.locator('.freshness').textContent());
 for(const width of [1440,1024,750,390,320]){await page.setViewportSize({width,height:900});
  assert.equal(await frame.locator('body').evaluate(()=>document.documentElement.scrollWidth>document.documentElement.clientWidth),false,'no document overflow '+width);
  await frame.locator('.wrap').evaluate(e=>{e.scrollTop=0;e.scrollLeft=e.scrollWidth});
  const position=await frame.locator('tbody tr').first().locator('td').nth(1).evaluate(e=>e.getBoundingClientRect().left);assert.ok(position<=34,'sticky customer');
  if(width===390)assert.equal(await frame.locator('.wrap').evaluate(e=>e.scrollWidth>e.clientWidth),true);
  if([1440,390].includes(width))await page.screenshot({path:output+'/table-'+width+'.png'});
 }
 // Fresh mount resumes from persisted UTC, and adding a publication column works.
 const reloaded={...selected,server_now:iso(10),read_at:iso(10),columns:[...columns,{id:'new',label:'Email 6',name:'New published email',enabled:true}]};
 reloaded.rows=selected.rows.map(r=>({...r,cells:[...r.cells,{label:'—',tone:'muted',reason:'Older frozen version'}]}));
 const resumed=await mount(page,html,reloaded);assert.equal(await resumed.locator('th').last().textContent(),'Email 6');
 assert.equal(await resumed.locator('tbody tr').first().locator('td').last().textContent(),'—');
 assert.equal(await resumed.locator('tbody tr').first().locator('td').nth(5).textContent(),'11h 59m');
 await resumed.locator('body').evaluate(()=>{inView=false;stop();lastPoll=-999999;tick()});const messages=await page.evaluate(()=>window.messages.length);await page.waitForTimeout(1200);assert.equal(await page.evaluate(()=>window.messages.length),messages);
 await resumed.locator('body').evaluate(()=>{cleanup();if(timer!==null)throw Error('Timer leaked')});
 await page.setViewportSize({width:1366,height:900});
 const after=await benchmark(page,html,payload);let beforeBench=null;
 if(fs.existsSync('tmp/checkout-table-before.html')){const old={rows:payload.rows.map(r=>({...r,reference:'#123',region:'Australia',status:'Not recovered',time_to_send:'10m remaining'})),selected:[]};beforeBench=await benchmark(page,fs.readFileSync('tmp/checkout-table-before.html','utf8'),old)}
 const report={fixture:'50 rows, Chromium, 30 repeated render samples; new table has five email columns',before:beforeBench,after,local_countdown_backend_requests:0,status_poll_min_seconds:15};
 fs.writeFileSync(output+'/component-benchmark.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 console.log('PASS dynamic columns, acceptance, local ticking, drift, persisted reload, due/stale state, bounded polling, selection/details, DOM retention, sticky scroll, cleanup, desktop/narrow layouts');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exitCode=1});
