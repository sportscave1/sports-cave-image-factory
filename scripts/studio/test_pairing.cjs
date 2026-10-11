// Protocol unit checks in a disposable DOM fixture; no browser/network access.
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const listeners={},sent=[],nodes={},nonce='a'.repeat(48),opener={postMessage:(d,o)=>sent.push({d,o})};
const node=id=>nodes[id] ||= {textContent:'',value:'',disabled:false,hidden:true,replaceChildren(){},append(){}};
const context={document:{getElementById:node,createElement:()=>({})},location:{hash:'#'+nonce,pathname:'/pair',origin:'http://127.0.0.1:12345'},history:{replaceState(){}},window:{opener,addEventListener:(n,f)=>listeners[n]=f},URL,URLSearchParams,setTimeout:()=>1,clearTimeout(){},fetch:async()=>({ok:true,json:async()=>({rows:[{id:'draft',actionable:true}],categories:['CORE']})})};
vm.runInNewContext(fs.readFileSync(__dirname+'/ui/pair.js','utf8'),context);
const emit=(source,origin,data)=>listeners.message({source,origin,data:{studio:1,nonce,...data}});
(async()=>{
 assert.equal(sent[0].d.type,'ready');assert.equal(Object.keys(sent[0].d).join(','),'studio,type,nonce');
 await emit({},'https://os.example',{type:'request'});assert.equal(node('requester').textContent,'');
 await emit(opener,'null',{type:'request'});assert.equal(node('requester').textContent,'');
 await emit(opener,'http://evil.example',{type:'request'});assert.equal(node('requester').textContent,'');
 await emit(opener,'https://os.example',{type:'request',nonce:'b'.repeat(48)});assert.equal(node('requester').textContent,'');
 await emit(opener,'https://os.example',{type:'request'});assert.match(node('requester').textContent,/https:\/\/os.example/);
 await emit(opener,'https://os.example',{type:'handoff',draft_id:'draft',intent:'edit'});assert.equal(node('handoff').hidden,true);
 node('session').value='http://127.0.0.1:12345/#'+'t'.repeat(43);await node('approve').onclick();assert.equal(node('session').value,'');
 assert.equal(sent.at(-1).d.type,'catalog');assert.ok(!JSON.stringify(sent).includes('t'.repeat(43)));
 await emit({},'https://os.example',{type:'handoff',draft_id:'draft',intent:'edit'});assert.equal(node('handoff').hidden,true);
 await emit(opener,'https://evil.example',{type:'handoff',draft_id:'draft',intent:'edit'});assert.equal(node('handoff').hidden,true);
 await emit(opener,'https://os.example',{type:'handoff',draft_id:'draft',intent:'publish'});assert.equal(node('handoff').hidden,true);
 await emit(opener,'https://os.example',{type:'handoff',draft_id:'draft',intent:'edit'});assert.equal(node('handoff').hidden,false);
 await emit(opener,'https://os.example',{type:'disconnect'});assert.equal(node('handoff').hidden,true);
 await emit(opener,'https://os.example',{type:'handoff',draft_id:'draft',intent:'edit'});assert.equal(node('handoff').hidden,true);
 console.log('Pairing protocol: source/origin/nonce/approval/action/revocation/token checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
