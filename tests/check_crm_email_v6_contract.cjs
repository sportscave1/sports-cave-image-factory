// Real component, intercepted local files only: source/version and template contracts.
const {chromium}=require('playwright'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{for(const channel of ['chrome','msedge']){
 const browser=await chromium.launch({channel,headless:true});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',r=>{
   const u=new URL(r.request().url());if(u.hostname!=='fixture.test')return r.abort();
   if(u.pathname==='/')return r.fulfill({contentType:'text/html',body:'<iframe id="controls" src="/index.html"></iframe><iframe id="preview"></iframe>'});
   return r.fulfill({path:path.join('components/crm_sections',path.basename(u.pathname))});
  });
  await page.goto('https://fixture.test/');const controls=page.frames().find(f=>f.url().includes('index.html')),preview=page.frames().find(f=>f.url()==='about:blank');
  const model=JSON.parse(fs.readFileSync('tmp/local-editor-models.json','utf8'))[0].model;model.resolved={};model.errors={};model.offer=null;model.shell='<div id="sc-local-sections"></div>';
  const sections=[{id:'original',type:'html',html_number:1,visible:true,html:'<p>Saved source</p>'}];
  const source='<style>.title{padding:23px}</style><!-- exact source --><h2 class="title">Hidden creative</h2>';
  const template={id:'structured',name:'Structured source',version:1,html:'<p>Fallback must not be used</p>',sections:[
   {id:'old-1',type:'html',html_number:1,visible:false,html:source},
   {id:'old-2',type:'discount',visible:true,offer:null,html:'<p>Personal creative</p>'}]};
  await page.evaluate(({model,sections})=>{window.events=[];addEventListener('message',e=>{if(e.data.type==='streamlit:setComponentValue')events.push(e.data.value)});window.scEmailDrafts=new Map([['test',{model,sections,revision:0,listeners:new Set()}]])},{model,sections});
  await preview.addScriptTag({content:fs.readFileSync('components/crm_sections/preview.js','utf8')});await preview.evaluate(()=>SCPreview.mount({scope:'test'}));
  await controls.waitForFunction(()=>typeof SCPreview!=='undefined');
  await controls.evaluate(({sections,template})=>dispatchEvent(new MessageEvent('message',{source:parent,data:{type:'streamlit:render',args:{sections,history_scope:'test',preview_scope:'test',draft_version:1,templates:[template],discount:{},save_status:'Saved'}}})),{sections,template});
  await controls.locator('textarea').first().waitFor();
  await controls.locator('textarea').first().evaluate(area=>{area.value='<p>Temporary</p>';area.dispatchEvent(new Event('input',{bubbles:true}));area.value='<p>Saved source</p>';area.dispatchEvent(new Event('input',{bubbles:true}));});
  await controls.getByText('Saved · Draft',{exact:true}).waitFor();
  assert.equal(await preview.getByText('Saved source',{exact:true}).count(),1);
  assert.equal(await page.evaluate(()=>scEmailDrafts.get('test').dirty),false);
  assert.deepEqual(await page.evaluate(()=>events),[],'Rapid revert sends no redundant persistence operation');
  await controls.locator('#add summary').click();await controls.getByRole('button',{name:'Insert Structured source',exact:true}).click();
  const inserted=await page.evaluate(()=>scEmailDrafts.get('test').sections);
  assert.equal(inserted.length,3);assert.equal(inserted[0].id,'original');assert.equal(inserted[1].html,source);assert.equal(inserted[1].visible,false);
  assert.equal(inserted[2].type,'discount');assert.equal(inserted[2].offer,null);assert.notEqual(inserted[1].id,'old-1');
  assert.equal(await preview.getByText('Hidden creative',{exact:true}).count(),0);assert.equal(await preview.getByText('Personal creative',{exact:true}).count(),1);
  await page.waitForFunction(()=>events.length>0);const action=(await page.evaluate(()=>events))[0].events[0];
  assert.deepEqual(action.new_ids,inserted.slice(1).map(s=>s.id));assert.deepEqual(errors,[]);
  console.log(channel+': rapid revert, zero redundant save, structured template source/visibility/identity passed');
 }finally{await browser.close()}
}})().catch(e=>{console.error(e);process.exit(1)});
