const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const code=fs.readFileSync(__dirname+'/../edge-adapter/browser-identity.js','utf8');
const profile='56578ebe-3793-47ba-b81f-fbc2c2755cf9',origin='http://127.0.0.1:18963';
function run(change={},page='edition_ops'){
 const identity={profile,page:origin+'/?page=product_uploads',frame:'top',control:'id:map',...change.identity};
 const witness={identity,name:'Mapping',time:Date.now(),...change};witness.identity=identity;
 let stored=JSON.stringify(witness),removed=0;const elements={};
 const doc={body:{append(e){elements[e.id]=e}},addEventListener(){},querySelectorAll(){return []},getElementById:id=>elements[id],
 createElement(){return {attrs:{},style:{},setAttribute(k,v){this.attrs[k]=v},getAttribute(k){return this.attrs[k]??null}}}};
 const host={document:doc,location:new URL(origin+'/?page='+page),localStorage:{getItem:()=>profile},
 sessionStorage:{getItem:()=>stored,removeItem(){stored=null;removed++}},addEventListener(){}};
 vm.runInNewContext(code,{window:host,top:host,document:doc,URL,URLSearchParams,crypto:{randomUUID:()=>profile},
 MutationObserver:class{observe(){}},queueMicrotask:f=>f(),setInterval(){}});
 assert.equal(removed,1);assert.equal(stored,null);
 return elements['sc-recorder-button-gesture'];
}
assert.ok(run());
for(const change of [{time:Date.now()-3000},{time:Date.now()+1000},{identity:{profile:'other'}},{identity:{control:'id:save'}},{identity:{page:'https://example.com/'}},{name:'secret token'}, {download:{url:'x'}}])assert.equal(run(change),undefined);
assert.equal(run({},'product_uploads'),undefined);
console.log('PASS: fresh Mapping witness restored once; stale/future/wrong scope/extra data rejected (9 cases)');
