// Hosted default-screen and restoration protocol; no network or production writes.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/../../components/developer_studio/panel.js','utf8');
function fixture(saved='a') {
 const nodes={},handlers={},messages=[],classes=new Set(),storage={'studio-v6-last-draft:http://127.0.0.1:18762':saved};let url;
 const element=()=>({children:[],value:'',dataset:{},textContent:'',disabled:false,hidden:false,append(...c){this.children.push(...c);},replaceChildren(...c){this.children=c;},setAttribute(k,v){this[k]=v;}});
 const node=id=>nodes[id]||=(element());
 const popup={closed:false,postMessage:(d,o)=>messages.push({d,o}),focus(){}};
 const ctx={document:{getElementById:node,createElement:element,querySelectorAll:()=>[],body:{classList:{toggle:(k,v)=>v?classes.add(k):classes.delete(k)}}},window:{open:u=>(url=u,popup),addEventListener:(n,f)=>handlers[n]=f},crypto:require('node:crypto').webcrypto,URL,localStorage:{getItem:k=>storage[k]||null,setItem:(k,v)=>storage[k]=v},setTimeout:()=>1,clearTimeout(){}};
 vm.runInNewContext(source,ctx);
 function connect(){node('origin').value='http://127.0.0.1:18762';node('connect').onclick();}
 const emit=data=>handlers.message({source:popup,origin:'http://127.0.0.1:18762',data:{studio:1,nonce:new URL(url).hash.slice(1),...data}});
 connect();return {node,emit,messages,classes,connect};
}
const rows=[{kind:'application',id:'a',name:'Owned A',category:'CORE',owner:'me/a',actionable:true,test:{evidence:'Evidence A'}},{kind:'application',id:'b',name:'Other B',category:'ADS',owner:'me/b',actionable:false,action_reason:'Different assigned owner',test:{evidence:'Evidence B'}}];
const catalog={type:'catalog',rows,categories:['CORE','ADS'],trusted:true,workspace_v6:true,application_drafts:true,default_draft_id:'a'};
(async()=>{
 const f=fixture();assert.ok(f.classes.has('editing'));assert.equal(f.node('workspace-v6').hidden,false);
 f.emit(catalog);assert.equal(f.messages.at(-1).d.type,'workspace-begin');assert.equal(f.messages.at(-1).d.draft_id,'a');
 assert.match(f.node('tests-selected').textContent,/Owned A/);assert.equal(f.node('evidence').children.length,1);
 const calls=f.messages.length;f.emit(catalog);assert.equal(f.messages.length,calls,'Refresh must not repeat confirmation');
 f.emit({type:'workspace-approved',draft_id:'b'});assert.equal(f.messages.length,calls,'Locked or unsolicited approval must not load a workspace');
 f.emit({type:'disconnected'});assert.equal(f.node('selected-preview').disabled,true);assert.equal(f.node('workspace-v6').hidden,false);
 f.connect();f.emit(catalog);assert.equal(f.messages.at(-1).d.type,'workspace-begin');assert.equal(f.messages.at(-1).d.draft_id,'a');
 for(const stored of ['b','deleted','']){const locked=fixture(stored);locked.emit(catalog);assert.equal(locked.messages.at(-1).d.draft_id,'a');assert.equal(locked.node('resume-editor').disabled,false);assert.equal(locked.node('workspace-v6').hidden,false);}
 const noDefault=fixture('');noDefault.emit({...catalog,default_draft_id:null});assert.equal(noDefault.messages.some(m=>m.d.type==='workspace-begin'),false,'Never pick an arbitrary application');
 const registrySaved=fixture('a');registrySaved.emit({...catalog,rows:[...rows,{...rows[0],id:'c',name:'Saved C'}],default_draft_id:'c'});assert.equal(registrySaved.messages.at(-1).d.draft_id,'c');
 const legacy=fixture();legacy.emit({...catalog,workspace_v6:false});assert.equal(legacy.messages.some(m=>m.d.type==='handoff'),false);assert.match(legacy.node('message').textContent,/V6 workspace update/);
 assert.equal(f.messages.some(m=>m.d.type==='handoff'),false,'V6 editing stays embedded');
 await new Promise(r=>setImmediate(r));
 console.log('Default Editor, authorised restoration, locked/missing drafts, approval correlation, refresh and reconnect passed');
})().catch(e=>{console.error(e);process.exitCode=1});
