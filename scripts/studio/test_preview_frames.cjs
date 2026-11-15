const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/ui/workspace.js','utf8');
const fn=source.match(/async function showFrame\(next\)\{[^\n]+\}/)[0];
const nodes={},pending=[];
const ctx={frame:{image:'old'},frameSequence:0,disposed:false,information:false,target:{querySelector:()=>({clientWidth:1280,clientHeight:900})},
 $:id=>nodes[id]||=(id==='ws-image'?{src:'old'}:{hidden:false,style:{}}),controls(){},
 Image:class{decode(){return new Promise((resolve,reject)=>pending.push({resolve,reject}));}},Error};
vm.createContext(ctx);vm.runInContext(fn,ctx);
(async()=>{
 const first=ctx.showFrame({image:'first'});assert.equal(nodes['ws-image'],undefined,'Old displayed frame must not be touched before decode');
 const second=ctx.showFrame({image:'second'});pending[1].resolve();await second;
 assert.equal(nodes['ws-image'].src,'data:image/jpeg;base64,second');
 pending[0].resolve();await first;assert.equal(nodes['ws-image'].src,'data:image/jpeg;base64,second','Late frame cannot overwrite newer frame');
 const bad=ctx.showFrame({image:'bad'});pending[2].reject(Error('bad image'));await assert.rejects(bad,/last valid frame is preserved/);
 assert.equal(nodes['ws-image'].src,'data:image/jpeg;base64,second');
 const oldDraft=ctx.showFrame({image:'old-draft'});ctx.disposed=true;ctx.frameSequence++;pending[3].resolve();await oldDraft;
 assert.equal(nodes['ws-image'].src,'data:image/jpeg;base64,second','Disposed draft cannot redraw a newly selected workspace');
 console.log('Decoded frame retention, latest response, bad image and disposed draft protection passed');
})().catch(e=>{console.error(e);process.exitCode=1});
