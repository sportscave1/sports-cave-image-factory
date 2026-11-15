// Interleaved V2/V3 image-load measurements isolate viewer work from frame/popup polling.
const fs=require('node:fs'), assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process'), {chromium}=require('playwright');
(async()=>{
 const browser=await chromium.launch({channel:'chrome',headless:true});
 try {
  const baseline=process.env.FILES_BENCHMARK_BASELINE||'a1058ce0';
  const versions={before:execFileSync('git',['show',baseline+':components/files_image_viewer/index.html'],{encoding:'utf8'}),after:fs.readFileSync('components/files_image_viewer/index.html','utf8')};
  const pages={},samples={before:[],after:[]};let payload;
  for(const label of ['before','after']){
   const page=await browser.newPage();pages[label]=page;await page.setContent('<canvas id="c" width="1024" height="768"></canvas>');
   payload=Buffer.from(await page.evaluate(()=>{c.getContext('2d').fillRect(0,0,1024,768);return c.toDataURL().split(',')[1];}),'base64');
   await page.route('**/*',async route=>{
    const u=new URL(route.request().url());if(u.hostname!=='measure.synthetic.test')return route.abort();
    if(u.pathname==='/viewer')return route.fulfill({contentType:'text/html',body:versions[label]});
    if(u.pathname==='/api/files-image-preview'){assert.equal(u.searchParams.get('representation'),'screen');await new Promise(r=>setTimeout(r,40));return route.fulfill({contentType:'image/png',body:payload});}
    return route.fulfill({status:404,body:''});
   });
   await page.goto('http://measure.synthetic.test/viewer?embedded=1');
  }
  for(let i=0;i<20;i++)for(const label of i%2?['after','before']:['before','after']){
   samples[label].push(await pages[label].evaluate(i=>new Promise(resolve=>{
    const start=performance.now();elements.image.addEventListener('load',()=>resolve(performance.now()-start),{once:true});void loadImage('Fixture'+i+'.jpg',{name:'Fixture'+i+'.jpg'});
   }),i));
  }
  const report={baseline,environment:'Actual Chrome/viewer, 40 ms synthetic image response; interleaved order; actual image load event'};
  for(const label of ['before','after']){const sorted=[...samples[label]].sort((a,b)=>a-b);report[label]={p50:sorted[10],p95:sorted[18],samples:samples[label]};}
  fs.writeFileSync('test-results/files-preview-v3-interleaved.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
