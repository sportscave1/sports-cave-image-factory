const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});try{
 const page=await browser.newPage();await page.route('**/*',r=>r.abort());await page.setContent('<iframe id="preview"></iframe>');
 const frame=page.frames()[1],source=fs.readFileSync('components/crm_sections/preview.js','utf8');await frame.addScriptTag({content:source});
 const fixture=JSON.parse(fs.readFileSync('tmp/local-editor-models.json','utf8'))[0];
 const sections=Array.from({length:100},(_,i)=>({...fixture.section,id:'large-'+i,settings:{...fixture.section.settings,text:'Section '+i}}));
 await page.evaluate(({model,sections})=>{window.scEmailDrafts=new Map([['stress',{model,sections,revision:0,listeners:new Set()}]]);},{model:fixture.model,sections});
 await frame.evaluate(()=>SCPreview.mount({scope:'stress'}));
 assert.equal(await frame.locator('[data-section-id]').count(),100);
 const result=await frame.evaluate(()=>{
  const state=SCPreview.channel('stress'),sections=structuredClone(state.sections),unchanged=document.querySelector('[data-section-id="large-20"]').firstChild;
  const times=[];for(let i=0;i<20;i++){sections[40].visible=!sections[40].visible;const start=performance.now();SCPreview.publish('stress',sections,true);times.push(performance.now()-start);}
  return {maxMs:Math.max(...times),meanMs:times.reduce((a,b)=>a+b)/times.length,retained:document.querySelector('[data-section-id="large-20"]').firstChild===unchanged};
 });
 assert.equal(result.retained,true);assert.ok(result.maxMs<200);console.log(result);fs.writeFileSync('tmp/local-editor-large.json',JSON.stringify(result));
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exit(1)});
