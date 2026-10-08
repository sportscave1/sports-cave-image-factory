const {chromium}=require('playwright'),fs=require('fs'),assert=require('assert');
(async()=>{const b=await chromium.launch({channel:'chrome',headless:true});try{
fs.mkdirSync('artifacts/mockups-ui',{recursive:true});const results=[];
for(const [width,height] of [[1920,1080],[1440,900],[1280,800],[390,844]]){
const p=await b.newPage({viewport:{width,height}});
await p.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
await p.goto('http://127.0.0.1:8895');await p.getByRole('heading',{name:'Product Page Lifestyle Mockups',exact:true}).waitFor({timeout:30000});
await p.getByRole('button',{name:'Load Full Resolution',exact:true}).first().waitFor();
const metrics=await p.evaluate(()=>({height:document.querySelector('[data-testid="stMainBlockContainer"]').getBoundingClientRect().height,headingY:[...document.querySelectorAll('h1')].find(e=>e.textContent==='Mockups').getBoundingClientRect().y,overflow:document.documentElement.scrollWidth>innerWidth,images:[...document.querySelectorAll('[data-testid="stImage"] img')].map(i=>({x:i.getBoundingClientRect().x,y:i.getBoundingClientRect().y,height:i.getBoundingClientRect().height}))}));
results.push({width,...metrics});
await p.screenshot({path:`artifacts/mockups-ui/${process.env.MOCKUPS_PHASE}-${width}.png`,fullPage:true});
if(process.env.MOCKUPS_PHASE==='after'){
assert.equal(await p.getByRole('button',{name:'Load Full Resolution',exact:true}).count(),5);assert.equal(await p.getByTestId('stFileUploader').count(),4);assert(!metrics.overflow);assert.equal(metrics.images.length,5);assert(metrics.images.every(i=>i.height<=261));
if(width===1440){await p.getByRole('button',{name:'Load Full Resolution',exact:true}).first().click();await p.getByRole('button',{name:'Hide Full Resolution',exact:true}).waitFor();await p.getByRole('button',{name:'Hide Full Resolution',exact:true}).click();await p.getByRole('button',{name:'Load Full Resolution',exact:true}).first().waitFor();}
}
await p.close();}
fs.writeFileSync(`artifacts/mockups-ui/${process.env.MOCKUPS_PHASE}.json`,JSON.stringify(results,null,2));console.log(JSON.stringify(results));
}finally{await b.close();}})().catch(e=>{console.error(e);process.exitCode=1});
