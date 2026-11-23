'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const html=fs.readFileSync(require('node:path').join(__dirname,'../components/orders_prodigi_grid/index.html'),'utf8');
const patch=html.slice(html.indexOf('function patchOrderRows('),html.indexOf('function render(){'));
test('a status update replaces only its own row and preserves table and other row objects',()=>{
 const replaced=[],rows=[{id:'allocation:1',review:{}},{id:'allocation:2',review:{}}];
 const old=rows.map(r=>({dataset:{unitId:r.id},replaceWith(next){replaced.push(next.id)}}));
 const scope=vm.createContext({args:{rows},filter:'all',opened:'',orderRow:r=>r,
  core:{filtered:r=>r},render:()=>assert.fail('No table rebuild for one status change'),
  document:{activeElement:{id:''},querySelector:s=>s==='.layout'?{}:null,
   querySelectorAll:s=>s==='tr[data-unit-id]'?old:[]}});
 vm.runInContext(patch,scope);scope.changed=new Set(['allocation:2']);
 vm.runInContext('patchOrderRows(changed)',scope);
 assert.deepEqual(replaced,['allocation:2']);assert.equal(old[0].dataset.unitId,'allocation:1');
});
test('filtered membership changes use a full render so rows cannot remain in the wrong filter',()=>{
 let renders=0;const scope=vm.createContext({args:{rows:[]},filter:'attention',document:{querySelector:()=>({})},render:()=>renders++});
 vm.runInContext(patch,scope);vm.runInContext('patchOrderRows(new Set())',scope);assert.equal(renders,1);
});
