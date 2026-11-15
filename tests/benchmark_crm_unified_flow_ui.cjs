// Paired five-sample, 50-row cold/warm panel benchmark. Synthetic 20ms reads.
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true}),results=[];
try{for(const kind of ['abandoned','welcome','post_purchase','win_back','fulfilled']){
 const samples={before:[],after:[]};
 for(let i=0;i<5;i++)for(const [label,port] of [['before',18750],['after',18749]]){
  if(kind==='fulfilled'&&label==='before')continue;
  const p=await b.newPage({viewport:{width:1440,height:1000}});
  await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await p.goto(`http://127.0.0.1:${port}/?flow=${kind}`);
  const summary=p.locator('summary').first();await summary.waitFor();
  await p.locator('[data-testid=stApp][data-test-script-state=notRunning]').waitFor();
  const f=p.frameLocator('iframe').first(),iframe=p.locator('iframe').first();
  const start=Date.now();await summary.click();await iframe.waitFor({state:'visible'});await f.locator('tbody tr').nth(49).waitFor();
  const coldMs=Date.now()-start;
  await p.waitForTimeout(250);await summary.click();await iframe.waitFor({state:'hidden'});await p.waitForTimeout(300);
  const warm=Date.now();await summary.click();await iframe.waitFor({state:'visible'});await f.locator('tbody tr').nth(49).waitFor();
  samples[label].push({coldMs,warmMs:Date.now()-warm});
  assert.equal(await p.getByTestId('stException').count(),0);await p.close();
 }
 const median=(xs,k)=>xs.length?xs.map(x=>x[k]).sort((a,b)=>a-b)[Math.floor(xs.length/2)]:null;
 results.push({kind,samples,before:{coldMs:median(samples.before,'coldMs'),warmMs:median(samples.before,'warmMs')},
   after:{coldMs:median(samples.after,'coldMs'),warmMs:median(samples.after,'warmMs')}});
 fs.writeFileSync('.tmp-unified-flow/paired-ui.json',JSON.stringify(results,null,2));console.log(JSON.stringify(results.at(-1)));
}}finally{await b.close()}})().catch(e=>{console.error(e);process.exit(1)});
