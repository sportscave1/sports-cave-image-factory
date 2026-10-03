const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('section navigation dismisses popover, selects Editor and targets only the requested ID',()=>{
 const calls=[],handlers={},action={dataset:{crmSection:'section-2'}};
 const trigger={textContent:'Send test',closest:()=>null,click:()=>calls.push('close')};
 const editor={textContent:'Editor',click:()=>calls.push('editor')};
 const context={console,window:{scCampaignGoToSection:id=>{calls.push(id);return true;}},Date,setTimeout,
  document:{addEventListener:(name,fn)=>handlers[name]=fn,querySelectorAll:selector=>selector==='button'?[trigger]:[editor]}};
 vm.runInNewContext(fs.readFileSync('components/campaign_recovery/test_sections.js','utf8'),context);
 handlers.click({target:{closest:()=>action},preventDefault(){},stopPropagation(){}});
 assert.deepEqual(calls,['close','editor','section-2']);
});
test('expanding a section uses existing render without emitting a save or changing drafts',()=>{
 const source=fs.readFileSync('components/crm_sections/composer.js','utf8');
 const part=source.slice(source.indexOf('const goToSection='),source.indexOf('withParent(p=>p.scCampaignGoToSection='));
 const calls=[],context={args:{sections:[{id:'wanted'}]},opened:{},render:()=>calls.push('render'),
  requestAnimationFrame:fn=>fn(),root:{children:[{dataset:{id:'wanted'},scrollIntoView:()=>calls.push('scroll'),querySelector:()=>({focus:()=>calls.push('focus')})}]}};
 vm.runInNewContext(part+';globalThis.go=goToSection;',context);
 assert.equal(context.go('missing'),false);assert.deepEqual(calls,[]);
 assert.equal(context.go('wanted'),true);assert.equal(context.opened.wanted,true);
 assert.deepEqual(calls,['render','scroll','focus']);
});
