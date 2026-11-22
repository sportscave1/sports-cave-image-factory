const test=require('node:test'),assert=require('node:assert/strict');
const {prodigiShippingQuotes,prodigiCheapestShipping}=require('../windows-upload-companion/prodigi-dashboard-qa.js');
const select=rows=>({options:rows.map(([value,label,disabled=false])=>({value,textContent:label,disabled}))});
test('quoted shipping prices use cents, including ties and Express intent',()=>{
 const quotes=prodigiShippingQuotes(select([['budget','Budget: $10.07'],['standard','Standard: $10.07'],['express','Express: $23.04']]));
 assert.deepEqual(quotes.map(q=>q.cents),[1007,1007,2304]);
 assert.equal(prodigiCheapestShipping(quotes,'standard','standard'),'standard');
 quotes[0].cents=900;assert.equal(prodigiCheapestShipping(quotes,'standard','standard'),'budget');
 assert.equal(prodigiCheapestShipping(quotes,'express','budget'),'express');
});
test('unpriced, ambiguous and missing Express quotes stop instead of guessing',()=>{
 assert.throws(()=>prodigiShippingQuotes(select([['standard','Standard: calculated later']])));
 assert.throws(()=>prodigiCheapestShipping([{service:'budget',cents:100,currency:'$'}],'express','budget'));
 assert.throws(()=>prodigiCheapestShipping([{service:'budget',cents:100,currency:'$'},{service:'budget',cents:200,currency:'$'}],'standard','budget'));
});

test('QA waits for late inserts controls and reads saved names without changing a set',async()=>{
 const vm=require('node:vm'),fs=require('node:fs');let listener,opened=false,lookups=0,edits=0,cancels=0;
 const visible=text=>({textContent:text,isConnected:true,getClientRects:()=>[{}],getAttribute:()=>null});
 const edit={...visible('View & edit'),click(){opened=true;edits++}},cancel={...visible('Cancel'),click(){opened=false;cancels++}};
 const quotes={...visible(''),value:'standard',options:[{textContent:'Standard: $10.07',value:'standard',disabled:false},{textContent:'Express: $23.04',value:'express',disabled:false}]};
 const modal={...visible(''),querySelectorAll(selector){if(selector==='h1,h2')return [visible('Inserts on this order')];if(selector==='button')return [cancel];if(selector.startsWith('[data-test'))return [visible('Current slip'),visible('Current sticker')];throw Error('Unexpected modal read '+selector)}};
 const main={...visible('REF-TEST'),querySelectorAll(selector){if(selector==='button')return ++lookups===1?[]:[edit];throw Error('Unexpected main read '+selector)}};
 const row={querySelector:()=>visible('Excellent')};
 const document={querySelector:()=>main,querySelectorAll(selector){if(selector==='main h1')return [visible('99')];if(selector==='table tbody tr')return [row];if(selector==='[role="dialog"]')return opened?[modal]:[];if(selector==='main select')return [quotes];throw Error('Unexpected document read '+selector)}};
 const context={document,URL,location:{href:'https://dashboard.prodigi.com/orders/99/detail'},prodigiExactRow:()=>true,setTimeout:fn=>queueMicrotask(fn),chrome:{runtime:{id:'paired',onMessage:{addListener:fn=>listener=fn},sendMessage:async()=>({permitted:true})}}};
 vm.runInNewContext(fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-dashboard-qa.js'),'utf8'),context);
 const result=await new Promise(resolve=>listener({type:'prodigi:qa',plan:{order_url:context.location.href,order_id:'99',reference:'REF-TEST',sku:'fixture',colour:'black',shipping_intent:'standard'}},{id:'paired'},resolve));
 assert.equal(result.error,undefined);assert.deepEqual(Array.from(result.evidence.inserts.saved,r=>r.name),['Current slip','Current sticker']);
 assert.equal(edits,1);assert.equal(cancels,1);assert.equal(opened,false);assert(lookups>=2);
});


test('US quotes include Overnight and Standard Plus without changing a cheapest Standard tie',()=>{
 const quotes=prodigiShippingQuotes(select([['budget','Budget: $27.30'],['standard','Standard: $27.30'],['express','Express: $38.10'],['overnight','Overnight: $54.30'],['standardplus','Standard Plus: $30.00']]));
 assert.deepEqual(quotes.map(q=>q.service),['budget','standard','express','overnight','standardplus']);
 assert.equal(prodigiCheapestShipping(quotes,'standard','standard'),'standard');
 assert.equal(prodigiCheapestShipping(quotes,'express','standard'),'express');
 quotes[4].cents=2000;assert.equal(prodigiCheapestShipping(quotes,'standard','standard'),'standardplus');
});

test('owner-authorised tax control is ticked once and an existing tick is never toggled off',async()=>{
 const vm=require('node:vm'),fs=require('node:fs');
 for(const initial of [false,true]){
  let listener,opened=false,checked=initial,clicks=0,permitted=false;
  const visible=text=>({textContent:text,isConnected:true,getClientRects:()=>[{}],getAttribute:()=>null});
  const edit={...visible('View & edit'),click(){opened=true}},cancel={...visible('Cancel'),click(){opened=false}};
  const quotes={...visible(''),value:'standard',options:[{textContent:'Standard: $10.07',value:'standard',disabled:false}]};
  const control={...visible(''),tagName:'BUTTON',disabled:false,parentElement:visible('I declare that this order has already had sales tax collected.'),getAttribute:key=>key==='role'?'checkbox':key==='aria-checked'?String(checked):null,click(){assert(permitted);checked=!checked;clicks++}};
  const modal={...visible(''),querySelectorAll(selector){if(selector==='h1,h2')return [visible('Inserts on this order')];if(selector==='button')return [cancel];if(selector.startsWith('[data-test'))return [visible('Slip'),visible('Sticker')];throw Error('Unexpected read '+selector)}};
  const main={...visible('REF-TEST'),querySelectorAll:()=>[edit]},row={querySelector:()=>visible('Excellent')};
  const document={querySelector:()=>main,querySelectorAll(selector){if(selector==='main h1')return [visible('99')];if(selector==='table tbody tr')return [row];if(selector==='[role="dialog"]')return opened?[modal]:[];if(selector==='main select')return [quotes];if(selector==='#taxCollectedCheckbox')return [control];throw Error('Unexpected read '+selector)}};
  const context={document,URL,location:{href:'https://dashboard.prodigi.com/orders/99/detail'},prodigiExactRow:()=>true,setTimeout:fn=>queueMicrotask(fn),chrome:{runtime:{id:'paired',onMessage:{addListener:fn=>listener=fn},sendMessage:async()=>{permitted=true;return {permitted:true,tax_declaration:true}}}}};
  vm.runInNewContext(fs.readFileSync(require.resolve('../windows-upload-companion/prodigi-dashboard-qa.js'),'utf8'),context);
  const result=await new Promise(resolve=>listener({type:'prodigi:qa',plan:{order_url:context.location.href,order_id:'99',reference:'REF-TEST',sku:'fixture',colour:'black',shipping_intent:'standard',tax_declaration:true,tax_required:true}},{id:'paired'},resolve));
  assert.equal(result.error,undefined);assert.equal(result.evidence.tax_collected,true);assert.equal(checked,true);assert.equal(clicks,initial?0:1);
 }
});
