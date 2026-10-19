const {test}=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
const script=fs.readFileSync('components/product_uploads/focus_generation.js','utf8');
test('generation scrolls once per click, respects reduced motion and cleans up',()=>{
 const stored=new Map();let target=null,observer,stopped=0,cleared=0,unmount;
 const calls=[];
 const host={sessionStorage:{getItem:k=>stored.get(k),setItem:(k,v)=>stored.set(k,v)},document:{body:{},querySelector:()=>target},requestAnimationFrame:f=>f(),matchMedia:()=>({matches:true})};
 function run(token){vm.runInNewContext(script,{focusToken:token,window:{parent:host},MutationObserver:class{constructor(f){observer=f}observe(){}disconnect(){stopped++}},setTimeout:()=>1,clearTimeout:()=>cleared++,addEventListener:(type,f)=>{unmount=f}})}
 run('click1');assert.equal(calls.length,0);
 target={getBoundingClientRect:()=>({height:400}),scrollIntoView:options=>calls.push(options)};observer();
 assert.equal(calls.length,1);assert.equal(calls[0].behavior,'auto');assert.equal(stopped,1);
 run('click1');assert.equal(calls.length,1);
 host.matchMedia=()=>({matches:false});run('click2');assert.equal(calls.length,2);assert.equal(calls[1].behavior,'smooth');
 unmount();assert.ok(cleared>=3);
});
