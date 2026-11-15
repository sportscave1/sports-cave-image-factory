// Runs generated Shopify custom-pixel code in a synthetic sandbox; never network.
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const {webcrypto}=require('node:crypto');
const template=fs.readFileSync('crm_customer_pixel.js','utf8');
async function sandbox(enabled=true,initial=false){
 const handlers={}, memory=new Map(), sent=[];let consent;
 const context={URL,crypto:webcrypto,init:{customerPrivacy:{analyticsProcessingAllowed:initial,marketingAllowed:initial}},
  api:{customerPrivacy:{subscribe:(name,fn)=>{consent=fn;}}},
  analytics:{subscribe:(name,fn)=>{handlers[name]=fn;}},
  browser:{sessionStorage:{getItem:async k=>memory.get(k),setItem:async(k,v)=>memory.set(k,v),removeItem:async k=>memory.delete(k)}},
  fetch:async(url,options)=>{sent.push({url,...options});return {ok:true};}};
 vm.runInNewContext(template.replace('__SC_CONFIG__',JSON.stringify({enabled,endpoint:'https://hooks.example.test/crm/tracking/events',pixel_id:'public_fixture_12345',test_context:true})),context);
 return {handlers,memory,sent,consent,context};
}
(async()=>{
 const off=await sandbox(false);assert.equal(Object.keys(off.handlers).length,0);assert.equal(off.sent.length,0);
 const s=await sandbox();const key='sc_'+'a'.repeat(32);
 const event={id:'fixture-event',timestamp:new Date().toISOString(),context:{document:{location:{href:'https://shop.example.test/products/art?utm_source=sports_cave&utm_medium=email&utm_campaign='+key+'&sc_test=1&email=private@example.test'}}},data:{productVariant:{product:{id:'gid://shopify/Product/1'}},checkout:{email:'private@example.test',payment:'private'}}};
 for(const fn of Object.values(s.handlers))await fn(event);assert.equal(s.sent.length,0);assert.equal(s.memory.size,0);
 s.consent({customerPrivacy:{analyticsProcessingAllowed:true,marketingAllowed:true}});
 for(const fn of Object.values(s.handlers))await fn(event);
 assert.equal(s.sent.length,5);assert(!JSON.stringify(s.sent).includes('private'));assert(!JSON.stringify(s.sent).includes('payment'));
 for(const message of s.sent){assert.equal(message.mode,'cors');assert.equal(message.credentials,'omit');const p=JSON.parse(message.body);assert.equal(p.campaign_key,key);assert.equal(p.test_context,true);}
 s.consent({customerPrivacy:{analyticsProcessingAllowed:true,marketingAllowed:false}});
 for(const fn of Object.values(s.handlers))await fn(event);assert.equal(s.sent.length,5);assert.equal(s.memory.size,0);
 // Withdrawal while asynchronous sandbox storage is pending must cancel the event.
 const race=await sandbox(true,true);let release;
 race.context.browser.sessionStorage.setItem=()=>new Promise(resolve=>{release=resolve;});
 const pending=race.handlers.page_viewed(event);race.consent({customerPrivacy:{analyticsProcessingAllowed:false,marketingAllowed:false}});release();await pending;
 assert.equal(race.sent.length,0);
 console.log('Pixel sandbox: disabled, denied, granted, five events, withdrawal, async race, PII minimization and fetch options passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
