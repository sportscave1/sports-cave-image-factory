// Controlled browser-only comparison, same inputs; excludes network/persistence.
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{const browser=await chromium.launch({channel:'chrome',headless:true});const rows=[];
try{for(const label of ['baseline','after'])for(const count of [3,30]){
 const base=label==='baseline'?'tmp/v6-baseline-source':'.';const page=await browser.newPage({viewport:{width:1440,height:1000}});
 await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.hostname!=='fixture.test')return route.abort();
  if(u.pathname==='/')return route.fulfill({contentType:'text/html',body:'<iframe id="controls" src="/index.html"></iframe><iframe id="preview"></iframe>'});
  const file=path.join(base,'components/crm_sections',path.basename(u.pathname));return route.fulfill({path:file});
 });
 const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto('https://fixture.test/');const controls=page.frames().find(f=>f.url().includes('index.html')),preview=page.frames().find(f=>f.url()==='about:blank');
 const fixture=JSON.parse(fs.readFileSync('tmp/local-editor-models.json','utf8'))[0],model=fixture.model;model.resolved={};model.errors={};model.shell='<div id="sc-local-sections"></div>';
 const sections=Array.from({length:count},(_,i)=>({id:'s'+i,type:'html',html_number:i+1,html:'<p>Section '+i+'</p>',visible:true}));
 await page.evaluate(({model,sections})=>{window.scEmailDrafts=new Map([['bench',{model,sections,revision:0,listeners:new Set()}]])},{model,sections});
 await preview.addScriptTag({content:fs.readFileSync(path.join(base,'components/crm_sections/preview.js'),'utf8')});await preview.evaluate(()=>SCPreview.mount({scope:'bench'}));
 await controls.waitForFunction(()=>typeof SCPreview!=='undefined');
 await controls.evaluate(sections=>dispatchEvent(new MessageEvent('message',{source:parent,data:{type:'streamlit:render',args:{sections,history_scope:'bench',preview_scope:'bench',draft_version:1,templates:[{id:'fixture-template',name:'Fixture template',version:1,html:'<!-- exact --><p>Inserted template</p>'}],discount:{},save_status:'Saved'}}})),sections);
 await controls.locator('.visibility').first().waitFor();
 const result=await controls.evaluate(async count=>{
  const samples={hide_processing_ms:[],hide_frame_ms:[],move_frame_ms:[],typing_preview_ms:[]};
  for(let i=0;i<12;i++){let started=performance.now();document.querySelector('.visibility').click();samples.hide_processing_ms.push(performance.now()-started);await new Promise(requestAnimationFrame);samples.hide_frame_ms.push(performance.now()-started);}
  for(let i=0;i<12;i++){let started=performance.now();document.querySelector('.handle').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',altKey:true,bubbles:true}));await new Promise(requestAnimationFrame);samples.move_frame_ms.push(performance.now()-started);}
  const area=document.querySelector('textarea');const preview=parent.document.getElementById('preview').contentDocument;
  for(let i=0;i<8;i++){
   const marker='Typing-'+count+'-'+i,started=performance.now();area.value='<h2>'+marker+'</h2>'+'<p style="color:#123456">Long creative</p>'.repeat(800);area.dispatchEvent(new Event('input',{bubbles:true}));
   while(!preview.body.textContent.includes(marker))await new Promise(requestAnimationFrame);samples.typing_preview_ms.push(performance.now()-started);
  }
  // Structural operations use actual component handlers. These measurements
  // deliberately exclude the 650 ms save debounce and database acknowledgement.
  const measure=async(name,action)=>{const start=performance.now();try{action()}catch(e){throw Error(name+': '+e.message+'; sections='+document.querySelectorAll('.section').length)}await new Promise(requestAnimationFrame);(samples[name]??=[]).push(performance.now()-start);};
  const remove=()=>{const card=document.querySelector('.section:last-child');card.querySelector('[aria-label="Delete section"]').click();card.querySelector('[aria-label="Confirm delete section"]').click();};
  for(let i=0;i<12;i++){
   await measure('add_frame_ms',()=>document.querySelector('[data-add="html"]').click());remove();
   await measure('duplicate_frame_ms',()=>document.querySelector('.section:last-child [aria-label="Duplicate section"]').click());
   await measure('delete_frame_ms',remove);
   await measure('undo_frame_ms',()=>document.querySelector('[aria-label="Undo delete section"]').click());remove();
   await measure('template_insert_frame_ms',()=>document.querySelector('[aria-label="Insert Fixture template"]').click());remove();
   await measure('section_panel_frame_ms',()=>document.querySelector('.section .title').click());
  }
  return samples;
 },count);
 assert.equal(await preview.locator('[data-section-id]').count(),count);assert.deepEqual(errors,[]);rows.push({label,count,...result});await page.close();
}fs.writeFileSync('tmp/email-v6-local-comparison.json',JSON.stringify(rows,null,2));console.log('Current baseline / V6 local interaction comparison completed');
}finally{await browser.close()}})().catch(e=>{console.error(e);process.exit(1)});
