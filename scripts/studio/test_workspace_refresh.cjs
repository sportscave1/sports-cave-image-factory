const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(__dirname+'/ui/workspace-local.js','utf8').replace("import {mount} from '/workspace.js';",'');
async function load({hash='',session=new Map(),valid='session-one',origin='',renewed='',blocked=false}={}){
 const output={mounted:false,status:'',calls:[],stripped:false},buffers=new Map([['studio-buffer:test','preserve unsaved HTML and CSS']]);
 const context={URLSearchParams,URL,location:{hash,pathname:'/workspace',origin:'http://127.0.0.1:57605'},history:{replaceState(){output.stripped=true;}},
  sessionStorage:{getItem(k){if(blocked)throw Error('blocked');return session.get(k);},setItem(k,v){if(blocked)throw Error('blocked');session.set(k,v);},removeItem(k){session.delete(k);}},
  localStorage:{getItem:k=>k==='studio-approved-origin'?origin:buffers.get(k)},navigator:{},
  document:{getElementById:id=>id==='local-status'?{set textContent(v){output.status=v;}}:{}},
  mount:async()=>{output.mounted=true;return {refreshCatalog(){},intent:async()=>{}};},
  fetch:async(path,options)=>{const body=JSON.parse(options.body);output.calls.push({path,body,token:options.headers['X-Studio-Token']});
   if(path==='/api/device')return {ok:!!renewed,status:renewed?200:403,json:async()=>({token:renewed})};
   const ok=options.headers['X-Studio-Token']===valid;return {ok,status:ok?200:401,json:async()=>ok?{draft:{id:'draft'},rows:[]}:{error:'Reopen the launcher URL to authenticate.'}};}};
 await vm.runInNewContext('(async()=>{'+source+'})()',context);
 assert.equal(buffers.get('studio-buffer:test'),'preserve unsaved HTML and CSS');return output;
}
(async()=>{
 const session=new Map();let result=await load({hash:'#token=session-one',session});assert(result.mounted&&result.stripped);assert.equal(session.get('studio-workspace-token'),'session-one');
 result=await load({session});assert(result.mounted);assert(result.calls.every(c=>c.path!=='/api/device'));
 result=await load({session,valid:'rotated'});assert(!result.mounted);assert(!session.has('studio-workspace-token'));
 result=await load({session,hash:'#token=rotated',valid:'rotated'});assert(result.mounted);assert.equal(session.get('studio-workspace-token'),'rotated');
 result=await load({session,valid:'renewed',origin:'https://os.example',renewed:'renewed'});assert(result.mounted);assert.equal(session.get('studio-workspace-token'),'renewed');
 result=await load({session,valid:'expired',origin:'https://os.example'});assert(!result.mounted);assert(!session.has('studio-workspace-token'));
 result=await load({hash:'#token=session-one',blocked:true});assert(result.mounted);
 result=await load({session:new Map()});assert(!result.mounted);
 console.log(JSON.stringify({passed:true,cases:8,checks:['launcher','plain reload','revocation','replacement launcher','trusted renewal','expired renewal','storage unavailable','tab isolation'],unsaved_buffers_untouched:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
