const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),{webcrypto}=require('node:crypto');
async function run(error=''){
 const status={},calls=[],messages=[],listeners=new Set();let close,sequence=0,cleared=false;
 const bridge={addEventListener:(n,f)=>listeners.add(f),removeEventListener:(n,f)=>listeners.delete(f),postMessage:m=>{
 messages.push(m);queueMicrotask(()=>{for(const f of [...listeners])f({data:{type:'sports-cave-desktop',request_id:m.request_id,action:m.action,ok:!(error&&m.action==='copyPreparedWebpPackage'),productUploadPreparedWebp:true,count:8,copy_ms:35,message:error}});});}};
 const ctx={document:{getElementById:()=>status},location:{hash:'#'+'a'.repeat(43),pathname:'/product-upload-native'},history:{replaceState:()=>cleared=true},crypto:webcrypto,
 setInterval:()=>1,clearInterval(){},setTimeout:(f,n)=>n===150?setTimeout(f,0):setTimeout(f,n),clearTimeout,addEventListener:(event,fn)=>{close=fn;},
 fetch:async(url,options)=>{const body=JSON.parse(options.body);calls.push(body);let result={command:'wait'};
 if(url.endsWith('claim'))result={secret:'secret',transfer:{ticket:'ticket'}};
 if(body.event==='poll')result={command:'copy',sequence:++sequence};
 if(body.event==='complete'&&sequence===3)close();
 return {ok:true,json:async()=>result};}};ctx.window={chrome:{webview:bridge}};
 await vm.runInNewContext(fs.readFileSync('components/product_uploads/native_clipboard.js','utf8'),ctx);
 return {status,calls,messages,listeners,cleared};
}
(async()=>{
 const r=await run();assert.equal(r.messages.filter(x=>x.action==='prepareWebpPackage').length,1);
 assert.equal(r.messages.filter(x=>x.action==='copyPreparedWebpPackage').length,3);
 assert.equal(r.calls.filter(x=>x.event==='complete').length,3);assert.equal(r.listeners.size,0);assert.ok(r.cleared);
 assert.ok(r.calls.findIndex(x=>x.event==='ready')<r.calls.findIndex(x=>x.event==='complete'));
 const failed=await run('Clipboard is busy');assert.match(failed.status.textContent,/busy/);assert.equal(failed.calls.at(-1).event,'failed');assert.equal(failed.listeners.size,0);
 console.log('Native page: one preparation, three explicit copy commands, verified acknowledgements, errors and cleanup passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
