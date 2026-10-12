const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/ui/pair.js','utf8');
function fixture({bootstrap=false,enrolled=true}={}){
 const handlers={},nodes={},sent=[],timers=[],calls=[],storage={};let revoked=false,serial=0;
 const node=id=>nodes[id] ||= {textContent:'',value:'',disabled:false,hidden:true,replaceChildren(){},append(){}};
 const opener={postMessage:(d,o)=>sent.push({d,o})};
 const context={document:{getElementById:node,createElement:()=>({})},location:{hash:bootstrap?'#bootstrap='+'a'.repeat(43):'#'+'b'.repeat(48),pathname:'/pair',origin:'http://127.0.0.1:18001'},history:{replaceState(){}},window:{opener,confirm:()=>true,addEventListener:(n,f)=>handlers[n]=f},localStorage:{setItem:(k,v)=>storage[k]=v},URL,URLSearchParams,setTimeout:(f,ms)=>{timers.push({f,ms});return timers.length;},clearTimeout(){},fetch:async(url,opt={})=>{const q=opt.body?JSON.parse(opt.body):{};calls.push({url,q});if(url==='/api/device'){if(q.operation==='trust')enrolled=true;if(q.operation==='renew'&&!enrolled)return {ok:false,status:403,json:async()=>({error:'No saved trust'})};if(q.operation==='revoke')revoked=true;if(revoked)return {ok:q.operation==='revoke',status:403,json:async()=>({error:'Revoked'})};return {ok:true,json:async()=>({token:'secret-'+(++serial),expires_in:300})};}return {ok:true,json:async()=>({rows:[],categories:['CORE']})};}};
 vm.runInNewContext(source,context);
 const emit=d=>handlers.message({source:opener,origin:'https://os.example',data:{studio:1,nonce:'b'.repeat(48),...d}});
 return {node,sent,timers,calls,emit,storage,handlers,enroll:()=>enrolled=true};
}
(async()=>{
 const first=fixture({enrolled:false});await first.emit({type:'request'});
 first.node('trust').checked=true;await first.node('approve').onclick();
 assert.match(first.node('status').textContent,/Run Companion.ps1 Open/);
 assert.ok(!first.node('status').textContent.includes('Invalid URL'));
 assert.ok(!first.calls.some(x=>x.q.operation==='trust'||x.q.action==='catalog'));
 assert.equal(first.node('trusted-origin').value,'https://os.example');assert.equal(first.node('trusted-origin').disabled,true);
 first.enroll();await first.node('approve').onclick();assert.equal(first.sent.at(-1).d.trusted,true);
 const initial=fixture({bootstrap:true,enrolled:false});
 initial.node('trusted-origin').value='https://os.example/path';await initial.node('approve').onclick();
 assert.equal(initial.calls.length,0);assert.match(initial.node('status').textContent,/exact HTTPS OS origin/);
 initial.node('trusted-origin').value='http://127.0.0.1:18861';await initial.node('approve').onclick();
 assert.equal(initial.calls[0].q.operation,'trust');assert.equal(initial.calls[0].q.origin,'http://127.0.0.1:18861');
 assert.equal(initial.node('session').value,'');assert.match(initial.node('status').textContent,/Computer trusted/);
 assert.equal(initial.timers.at(-1).ms,240000);
 const f=fixture();await f.emit({type:'request'});
 assert.equal(f.sent.at(-1).d.type,'catalog');assert.equal(f.sent.at(-1).d.trusted,true);
 assert.equal(f.storage['studio-approved-origin'],'https://os.example');
 assert.equal(f.node('approve').disabled,true);
 assert.equal(f.timers.at(-1).ms,240000);
 await f.timers.at(-1).f();assert.equal(f.calls.filter(x=>x.q.operation==='renew').length,2);
 assert.ok(!JSON.stringify(f.sent).includes('secret-'));
 await f.emit({type:'ping'});assert.equal(f.sent.at(-1).d.type,'pong');assert.equal(f.calls.at(-1).url,'/api/ping');
 await f.node('forget').onclick();assert.equal(f.sent.at(-1).d.type,'disconnected');
 const before=f.calls.length;await f.emit({type:'handoff',draft_id:'other',intent:'edit'});assert.equal(f.calls.length,before);
 const reopened=fixture();await reopened.emit({type:'request'});assert.equal(reopened.sent.at(-1).d.trusted,true);
 console.log('Trusted pairing: resume, renewal, local-only credentials, health, revocation and reopen passed');
})().catch(e=>{console.error(e);process.exitCode=1});
