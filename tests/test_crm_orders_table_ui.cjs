const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('components/crm_checkout_table/index.html','utf8');
const baseline=require('node:child_process').execFileSync('git',['show','HEAD:components/crm_checkout_table/index.html'],{encoding:'utf8'});
const cols=['Order','Fulfilment','Flow','Email 1','Email 2','Email 3'].map(label=>({label,name:label,enabled:true}));
const payload={presentation:'orders',selection_context:'page1',table_label:'Orders',date_label:'Order date',
 selected:['off-page'],refresh_seconds:15,server_now:new Date().toISOString(),read_at:new Date().toISOString(),phase:'READY',columns:cols,
 rows:Array.from({length:50},(_,i)=>({key:'order'+i,customer:'Fixture Purchaser '+i,created:'13 Oct 2026 09:45',cells:cols.map(c=>({label:c.label==='Order'?'#SC'+i:'Not enrolled',tone:'muted'}))}))};
async function mount(p,source,args){await p.setContent('<iframe style="width:100%;height:720px;border:0"></iframe>');
 await p.evaluate(source=>{window.events=[];window.addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')window.events.push(e.data.value)});document.querySelector('iframe').srcdoc=source},source);
 const f=p.frameLocator('iframe');await p.waitForFunction(()=>document.querySelector('iframe').contentDocument?.readyState==='complete');
 await p.evaluate(args=>document.querySelector('iframe').contentWindow.postMessage({type:'streamlit:render',args},'*'),args);
 await f.locator(args.rows.length?'tbody tr':'thead tr').first().waitFor();return f;}
async function measure(f){return f.locator('body').evaluate(()=>{
 const times=[];for(let i=0;i<41;i++){const start=performance.now();render();document.body.offsetHeight;if(i)times.push(performance.now()-start)}times.sort((a,b)=>a-b);
 return {medianMs:times[20],p95Ms:times[38],rowHeight:document.querySelector('tbody tr').getBoundingClientRect().height};});}
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});try{
 const p=await b.newPage({viewport:{width:1366,height:900}});await p.route('**/*',r=>r.abort());
 let f=await mount(p,html,payload);
 assert.equal(await f.locator('thead input').evaluate(e=>e.indeterminate),true);
 await f.locator('thead input').check();await f.locator('thead input').uncheck();
 await p.waitForFunction(()=>window.events.at(-1)?.clear_selection===true);
 const event=await p.evaluate(()=>window.events.at(-1));assert.equal(event.clear_selection,true);assert.deepEqual(event.selected,[]);assert.equal(event.context,'page1');
 const after=await measure(f);assert.equal(after.rowHeight,34);
 for(const width of [1366,1024,390]){await p.setViewportSize({width,height:900});assert.equal(await f.locator('body').evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}
 f=await mount(p,html,{...payload,rows:[],selected:['off-page']});await f.locator('thead input').click();await p.waitForFunction(()=>window.events.at(-1)?.clear_selection===true);assert.deepEqual(await p.evaluate(()=>window.events.at(-1).selected),[]);
 await p.setViewportSize({width:1366,height:900});
 const oldCols=['Order','Email','Payment','Fulfilment','Marketing consent','Flow','Email 1','Email 2','Email 3'].map(label=>({label,name:label,enabled:true}));
 f=await mount(p,baseline,{...payload,presentation:undefined,columns:oldCols,rows:payload.rows.map(r=>({...r,cells:oldCols.map(c=>({label:c.label,tone:'muted'}))}))});
 const before=await measure(f);console.log(JSON.stringify({synthetic:true,rows:50,before,after}));
}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
