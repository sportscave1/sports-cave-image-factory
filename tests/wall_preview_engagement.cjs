const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const source=fs.readFileSync('shopify_theme/assets/sports-cave-wall-preview.js','utf8');
const transport=source.slice(source.indexOf('function analyticsDevice(){'),source.indexOf('function firstAnalyticsClick('));
const fn=source.slice(source.indexOf('function createEngagementTracker(){'),source.indexOf('var engagement=createEngagementTracker();'));
let time=1,interval,requests=[],beacons=[],listeners=new Map();
const document={visibilityState:'visible',referrer:'https://search.test/?private=x'},window={},overlay={hidden:false};
const fire=(target,name)=>{for(const f of listeners.get(target)?.[name]||[])f();};
const state={clientPreviewId:crypto.randomUUID(),isMobileCamera:false};
const ctx={document,window,overlay,state,sessionId:crypto.randomUUID(),sessionStorage:{getItem:()=>null,setItem:()=>{}},
 performance:{now:()=>time},screen:{width:1366,height:768},location:{href:'https://shop.test/products/a?utm_source=qa&email=private'},URL,Blob,
 root:{getAttribute:k=>k==='data-wall-inbox-url'?'https://backend.test/api/wall-previews':k==='data-product-id'?'123':'art'},
 frameName:()=> 'Black',makeId:()=>crypto.randomUUID(),currentVariant:()=>({id:456}),
 listen:(target,name,f)=>{if(!listeners.has(target))listeners.set(target,{});(listeners.get(target)[name]??=[]).push(f);},
 navigator:{sendBeacon:(url,body)=>{beacons.push(body);return true;}},
 fetch:async(url,opt)=>{requests.push(JSON.parse(opt.body));return {ok:true,status:200};}
};
window.setInterval=f=>{interval=f;return 1;};window.clearInterval=()=>{interval=null;};window.setTimeout=()=>{};
vm.createContext(ctx);vm.runInContext(transport+fn+'var tracker=createEngagementTracker();',ctx);const t=ctx.tracker;
(async()=>{
 t.click();assert.equal(requests.length,1);assert.equal(requests[0].event,'wall_preview_cta_click');
 t.open();t.open();assert.equal(requests.filter(p=>p.event==='wall_preview_open').length,1);
 time+=15000;interval();assert.equal(requests.at(-1).active_seconds,15);
 time+=5000;document.visibilityState='hidden';fire(document,'visibilitychange');
 time+=90000;interval();document.visibilityState='visible';fire(document,'visibilitychange');
 time+=10000;t.source('upload');t.event('wall_preview_photo_loaded');assert.equal(requests.at(-1).active_seconds,30);
 state.clientPreviewId=crypto.randomUUID();t.event('wall_preview_placement_confirmed');
 assert.equal(new Set(requests.map(p=>p.wall_preview_session_id)).size,1);
 fire(window,'blur');time+=90000;fire(window,'focus');time+=5000;interval();assert.equal(requests.at(-1).active_seconds,35);
 time+=120000;interval();assert.equal(requests.at(-1).active_seconds,90,'idle cap counts 60s since focus, not all elapsed');
 fire(overlay,'pointerdown');time+=5000;t.close();assert.equal(interval,null);t.close();
 const closes=await Promise.all(beacons.map(async b=>JSON.parse(await b.text())));assert.equal(closes.filter(p=>p.event==='wall_preview_close').length,1);
 assert.equal(closes.at(-1).active_seconds,95);assert(!JSON.stringify(requests).includes('email='));
 const previous=requests[0].wall_preview_session_id;t.click();t.open();assert.notEqual(requests.at(-1).wall_preview_session_id,previous);
 assert.equal(new Set(requests.map(p=>p.event_id)).size,requests.length);
 ctx.fetch=()=>Promise.reject(new Error('offline'));t.event('wall_preview_add_to_cart');await Promise.resolve();t.close();
 await new Promise(r=>setImmediate(r));
 // Retry guidance retains the exact event ID and body.
 const retryBodies=[],timers=[];window.setTimeout=(f,delay)=>timers.push({f,delay});
 ctx.fetch=async(url,opt)=>{retryBodies.push(opt.body);return {status:retryBodies.length===1?429:200,headers:{get:()=> '600'}};};
 t.click();await new Promise(r=>setImmediate(r));assert.equal(timers[0].delay,600000);timers[0].f();await new Promise(r=>setImmediate(r));assert.equal(retryBodies[0],retryBodies[1]);
 console.log('PASS: CTA vs open, stable visit across captures, hidden/blur/idle exclusion, resume, final beacon, reopen, privacy, outage isolation');
})().catch(e=>{console.error(e);process.exitCode=1;});
