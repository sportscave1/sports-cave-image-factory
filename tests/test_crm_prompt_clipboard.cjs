const {execFileSync}=require('node:child_process');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=JSON.parse(execFileSync('.venv/Scripts/python',['-c',
 `import json; from unittest.mock import patch; from crm_prompt_ui import copy_result
with patch('streamlit.html') as out:
 copy_result('fixture </script> prompt'); print(json.dumps(out.call_args.args[0]))`],{encoding:'utf8'}));
const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
async function check(clipboard){
 const status={textContent:'Copying…'},fallback={hidden:true,value:''};
 vm.runInNewContext(source,{navigator:{clipboard},document:{getElementById:id=>id.includes('fallback')?fallback:status}});
 await new Promise(resolve=>setImmediate(resolve));return {status,fallback};
}
(async()=>{
 let text;let r=await check({writeText:async value=>{text=value;}});
 assert.equal(text,'fixture </script> prompt');assert.equal(r.status.textContent,'Copied');assert.equal(r.fallback.hidden,true);
 for(const clipboard of [undefined,{writeText:async()=>{throw Error('denied');}}]){
  r=await check(clipboard);assert.notEqual(r.status.textContent,'Copied');assert.equal(r.fallback.hidden,false);assert.equal(r.fallback.value,'fixture </script> prompt');
 }
 console.log('Actual clipboard script: success, unsupported, denial and escaped payload passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
