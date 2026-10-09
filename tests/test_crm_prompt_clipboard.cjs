const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('ui_components/prompt_copy/clipboard.js','utf8');
async function check(api,legacy){
 let selected='',removed=false,calls=0,reads=0;
 const active={focus(){}};
 const area={style:{},setAttribute(){},focus(){},select(){selected=this.value;},setSelectionRange(){},remove(){removed=true;}};
 const context={isSecureContext:true,navigator:{clipboard:{writeText:api,readText(){reads++;}}},document:{activeElement:active,body:{appendChild(){}},createElement:()=>area,execCommand(){calls++;return legacy;}}};
 vm.runInNewContext(source,context);const ok=await context.scCopyText('fixture </script> λ');
 assert.equal(reads,0);return {ok,calls,selected,removed};
}
(async()=>{
 let actual;let r=await check(async s=>{actual=s;},false);assert.equal(r.ok,true);assert.equal(r.calls,0);assert.equal(actual,'fixture </script> λ');
 for(const api of [undefined,async()=>{throw Error('denied');}]){
  r=await check(api,true);assert.equal(r.ok,true);assert.equal(r.calls,1);assert.equal(r.selected,'fixture </script> λ');assert.equal(r.removed,true);
  r=await check(api,false);assert.equal(r.ok,false);assert.equal(r.calls,1);
 }
 const html=fs.readFileSync('ui_components/prompt_copy/index.html','utf8');
 const js=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
 const button={style:{},setAttribute(){},addEventListener(t,f){this[t]=f;}},status={};let listener;const messages=[];
 const parent={postMessage:m=>messages.push(m)};
 const copiedTexts=[];let copySucceeds=true;
 const ctx={window:{parent,addEventListener(t,f){listener=f;},setTimeout(){},scCopyText:async text=>{copiedTexts.push(text);return copySucceeds;}},document:{body:{scrollHeight:58},getElementById:id=>id==='copy-button'?button:status},crypto:{randomUUID:()=> 'nonce'}};
 vm.runInNewContext(js,ctx);
 const render=args=>listener({source:parent,data:{type:'streamlit:render',args}});
 render({validation_mode:true,compact:true,label:'Copy email prompt',prompt_text:''});button.click({preventDefault(){}});
 assert.equal(messages.at(-1).value.type,'prepare');
 render({validation_mode:true,compact:true,label:'Copy email prompt',prompt_text:'verified',response_id:'nonce'});
 await new Promise(r=>setImmediate(r));assert.equal(messages.find(m=>m.value?.type==='copied').value.event,'nonce');
 const count=messages.filter(m=>m.value?.type==='copied').length;render({validation_mode:true,compact:true,prompt_text:'verified',response_id:'nonce'});
 await new Promise(r=>setImmediate(r));assert.equal(messages.filter(m=>m.value?.type==='copied').length,count);
 const fullPrompt='Artwork {ROOM} </script> λ\n'+('Exact source, reflections and shadows\n'.repeat(8000))+'END OF COMPLETE PROMPT';
 render({prompt_text:fullPrompt,label:'Copy Prompt'});button.click({preventDefault(){}});await new Promise(r=>setImmediate(r));assert.equal(messages.at(-2).value,true);
 assert.equal(copiedTexts.at(-1),fullPrompt,'No truncation, escaping changes or missing tail');
 copySucceeds=false;const countBeforeFailure=messages.filter(m=>m.type==='streamlit:setComponentValue').length;
 button.click({preventDefault(){}});await new Promise(r=>setImmediate(r));
 assert.equal(messages.filter(m=>m.type==='streamlit:setComponentValue').length,countBeforeFailure,'Failure never reports success');
 assert.equal(button.textContent,'Copy failed');
 console.log('Clipboard API, rejection fallback, unsupported fallback, both-failed, no reads, safe literal payload, CRM preflight/ack/no loop and Ads boolean contract passed.');
})().catch(e=>{console.error(e);process.exitCode=1;});
