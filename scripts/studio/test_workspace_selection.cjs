// Focused hosted selection regression; no network, real browser or production writes.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function element(tag='div') {return {tag,children:[],value:'',dataset:{},textContent:'',disabled:false,hidden:false,append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},setAttribute(k,v){this[k]=v;}};}
const nodes={},handlers={},messages=[],tabs=['live','drafts','editor','preview','tests','releases','history'].map(tab=>Object.assign(element('button'),{dataset:{tab}}));
const node=id=>nodes[id]||=(element());
const popup={closed:false,postMessage:(d,o)=>messages.push({d,o}),focus(){}};
const ctx={document:{getElementById:node,createElement:element,querySelectorAll:q=>q==='[data-tab]'?tabs:[]},window:{open:()=>popup,addEventListener:(n,f)=>handlers[n]=f},crypto:require('node:crypto').webcrypto,URL,Option:function(text,value){return {textContent:text,value};},localStorage:{getItem:()=>null,setItem(){}},setTimeout:()=>1,clearTimeout(){}};
vm.runInNewContext(fs.readFileSync(__dirname+'/../../components/developer_studio/panel.js','utf8'),ctx);
node('origin').value='http://127.0.0.1:18762';node('connect').onclick();
// Ready includes the nonce generated for the popup URL; recover it from a captured open argument.
// Reinitialize the fixture with the open URL captured, preserving no state from the first context.
let url;ctx.window.open=u=>(url=u,popup);node('connect').onclick();const nonce=new URL(url).hash.slice(1);
const emit=data=>handlers.message({source:popup,origin:'http://127.0.0.1:18762',data:{studio:1,nonce,...data}});
emit({type:'ready'});
const rows=[{id:'a',name:'Owned A',category:'CORE',owner:'me/a',actionable:true,test:{evidence:'Evidence A'}},{id:'b',name:'Other B',category:'ADS',owner:'me/b',actionable:false,action_reason:'Different assigned owner',test:{evidence:'Evidence B'}}];
emit({type:'catalog',rows,categories:['CORE','ADS'],trusted:true});
assert.equal(node('selected-edit').disabled,true);
node('list').children[0].children.find(n=>n.tag==='button'&&n.textContent==='Edit').onclick();
assert.equal(messages.at(-1).d.draft_id,'a');assert.equal(messages.at(-1).d.intent,'edit');
assert.match(node('preview-selected').textContent,/Owned A/);assert.match(node('tests-selected').textContent,/Owned A/);
assert.equal(node('evidence').children.length,1);assert.equal(node('selected-preview').disabled,false);
node('selected-preview').onclick();assert.equal(messages.at(-1).d.intent,'preview');assert.equal(node('preview').hidden,false);
emit({type:'catalog',rows,categories:['CORE','ADS'],trusted:true});assert.match(node('selected').textContent,/Owned A/);
assert.equal(node('list').children[1].children.filter(n=>n.tag==='button').every(n=>n.disabled),true);
emit({type:'workspace-opened',draft_id:'a',intent:'preview'});assert.match(node('handoff-status').textContent,/Selected local workspace opened/);
emit({type:'disconnected'});assert.equal(node('selected-edit').disabled,true);assert.equal(node('evidence').children.length,0);
console.log('Hosted draft selection: action routing, owner locks, selected test evidence, refresh and disconnect passed');
