const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(){const context={parent:{}};vm.createContext(context);vm.runInContext(fs.readFileSync('components/crm_sections/preview.js','utf8'),context);return context.SCPreview;}
test('selection is scoped and does not publish or mutate content',()=>{
 const api=fixture(),a=api.channel('a'),b=api.channel('b');let selected=[],renders=0;
 a.sections=[{id:'same-id',visible:true,html:'<p>Unpublished edit</p>'}];b.sections=structuredClone(a.sections);a.revision=7;a.listeners.add(()=>renders++);a.selectionListeners=new Set([id=>selected.push(id)]);
 const before=JSON.stringify(a.sections);assert(api.select('a','same-id'));assert.equal(a.selected,'same-id');assert.equal(b.selected,undefined);assert.deepEqual(selected,['same-id']);assert.equal(a.revision,7);assert.equal(renders,0);assert.equal(JSON.stringify(a.sections),before);
});
test('duplicates and reordered sections are selected by identity; removed, hidden and loading targets are ignored',()=>{
 const api=fixture(),state=api.channel('email');state.sections=[{id:'original',visible:true,html:'same'},{id:'duplicate',visible:true,html:'same'},{id:'hidden',visible:false}];
 state.sections.reverse();assert(api.select('email','duplicate'));assert.equal(state.selected,'duplicate');assert(!api.select('email','hidden'));state.sections=state.sections.filter(s=>s.id!=='duplicate');assert(!api.select('email','duplicate'));assert(!api.select('email','missing'));assert(api.select('email','original'));state.model={loading:true};assert(!api.select('email','original'));
});
