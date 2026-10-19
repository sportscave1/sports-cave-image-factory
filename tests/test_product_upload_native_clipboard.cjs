const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
const script=fs.readFileSync('components/product_uploads/native_clipboard.js','utf8');
async function run(count=8,error=''){
 const status={},calls=[],messages=[],listeners=new Set();let cleared=false;
 const bridge={addEventListener:(n,f)=>listeners.add(f),removeEventListener:(n,f)=>listeners.delete(f),postMessage:m=>{
  messages.push(m);if(m.action==='cancel')return;
  queueMicrotask(()=>{for(const f of [...listeners])f({data:{type:'sports-cave-desktop',request_id:m.request_id,action:m.action,ok:m.action==='hello'||!error,productUploadWebp:true,count,message:error}});});
 }};
 const ctx={document:{getElementById:()=>status},location:{hash:'#'+'a'.repeat(43),pathname:'/product-upload-native'},
  history:{replaceState:()=>cleared=true},crypto:webcrypto,setTimeout,clearTimeout,addEventListener(){},
  fetch:async(url,options)=>{calls.push({url,body:JSON.parse(options.body)});return{ok:true,json:async()=>url.endsWith('claim')?{secret:'completion',transfer:{ticket:'ticket',secret:'grant'}}:{ok:true}};}};
 ctx.window={chrome:{webview:bridge}};await vm.runInNewContext(script,ctx);
 return {status,calls,messages,listeners,cleared};
}
(async()=>{
 for(let i=0;i<3;i++){const r=await run();assert.match(r.status.textContent,/Copied all eight/);assert.equal(r.calls.at(-1).body.count,8);assert.equal(r.messages.filter(x=>x.action==='copyWebpPackage').length,1);assert.ok(r.cleared);assert.equal(r.listeners.size,0);}
 for(const [count,error] of [[7,''],[8,'office.webp: failed to hydrate'],[8,'Clipboard is busy']]){const r=await run(count,error);assert.doesNotMatch(r.status.textContent,/✓ Copied/);assert.equal(r.calls.at(-1).body.count,0);assert.ok(r.calls.at(-1).body.error);assert.equal(r.listeners.size,0);}
 console.log('Native handoff: three independent copies, exact count, missing-file/clipboard errors, fragment removal and listener cleanup passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
