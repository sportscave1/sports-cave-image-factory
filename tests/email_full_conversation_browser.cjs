// Real Chromium layout, synthetic mail only; no application server or credentials.
const {chromium}=require('playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
const docs=JSON.parse(fs.readFileSync('tmp/conversation-documents.json','utf8'));
const current=fs.readFileSync('components/support_email/mail.js','utf8');
const baseline=fs.readFileSync('tmp/conversation-before/mail.js','utf8');
const row=(key,document)=>({key,subject:'Synthetic conversation',sender:{name:'Customer',email:'customer@example.test'},to:[],cc:[],time:'Today',folder:'INBOX',attachments:[],expanded:true,reader_document:document,reader_identity:key,html:'<p>Plain body</p>',quote:'<p>Quoted plain reply</p>'});
const model=(document,n=12)=>({reader_scope:'test',selected:'thread',view:'mail',active_message:'0',roles:{},messages:Array.from({length:n},(_,i)=>row(String(i),i%2?null:document))});
const stats=a=>({n:a.length,p50_ms:+a.sort((a,b)=>a-b)[Math.floor(a.length/2)].toFixed(2),max_ms:+Math.max(...a).toFixed(2)});
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true});
 const result={method:'Loopback-free synthetic DOM fixture, same 12 loaded messages before/after; 7 paints, 30 animation-frame scrolls. No production latency claims.'};
 try{
  for(const label of ['before','after']){
   const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[],requests=[];
   page.on('pageerror',e=>errors.push(e.message));
   await page.route('**/*',route=>{requests.push(route.request().url());route.abort();});
   await page.setContent('<div id="mail"><section class="reading"></section></div>');
   await page.addStyleTag({content:fs.readFileSync('components/support_email/style.css','utf8')+'#mail{display:block;height:900px}.reading{height:900px;display:flex!important}'});
   const source=label==='before'?baseline:current;
   await page.addScriptTag({content:source.replace(/\}\)\(\);\s*$/,`window.readerTest={paint(m,reset=false){model=m;paintReading(false,reset)},render};})();`)});
   const m=model(docs[label]);
   const paints=[];
   for(let i=0;i<7;i++){
    m.selected='thread-'+i;
    const t=await page.evaluate(m=>{const t=performance.now();readerTest.paint(m,true);return performance.now()-t;},m);paints.push(t);
    await page.waitForFunction(()=>[...document.querySelectorAll('.email-document')].every(f=>f.style.height));
   }
   const geometry=await page.evaluate(()=>{
    const f=document.querySelector('.email-document'),doc=f.contentDocument,ps=[...doc.querySelectorAll('p')],last=ps.at(-1).getBoundingClientRect(); const glyphs=ps.map(p=>{const r=doc.createRange();r.selectNodeContents(p);return r.getBoundingClientRect();});
    return {frameHeight:f.getBoundingClientRect().height,bodyScroll:doc.body.scrollHeight,
     overlappingLines:glyphs.slice(1).filter((p,i)=>p.top<glyphs[i].bottom).length,
     contentBottom:last.bottom,quotesVisible:document.querySelectorAll('.quote').length,
     bodyControls:[...document.querySelectorAll('button,summary')].filter(b=>/expand|collapse message|show quoted/i.test(b.textContent)).length};
   });
   const scrolls=await page.evaluate(async()=>{const s=document.querySelector('.reading-scroll'),times=[];for(let i=0;i<30;i++){const t=performance.now();s.scrollTop=i*(s.scrollHeight-s.clientHeight)/29;await new Promise(requestAnimationFrame);times.push(performance.now()-t);}return times;});
   result[label]={paint:stats(paints),scrollFrame:stats(scrolls),geometry,requests,errors};
   if(label==='after'){
    assert.equal(geometry.overlappingLines,0);assert.equal(geometry.bodyControls,0);assert.equal(geometry.quotesVisible,6);assert.equal(requests.length,0);
    assert.equal(await page.evaluate(()=>[...document.querySelectorAll('.email-document')].every(f=>f.contentDocument.documentElement.scrollWidth<=f.clientWidth&&f.contentDocument.body.scrollHeight<=f.clientHeight)),true,'Email has internal overflow');
    const oldHeight=geometry.frameHeight;
    await page.setViewportSize({width:700,height:900});
    await page.waitForFunction(h=>document.querySelector('.email-document').getBoundingClientRect().height>h,oldHeight);
    // Populate a previously missing body while preserving another live iframe.
    m.messages[0].expanded=false;await page.evaluate(m=>readerTest.paint(m),m);
    await page.evaluate(()=>{window.savedFrame=document.querySelectorAll('.email-document')[0];window.savedDoc=savedFrame.contentDocument;});
    m.messages[0].expanded=true;await page.evaluate(m=>readerTest.paint(m),m);
    assert.equal(await page.evaluate(()=>savedFrame.isConnected&&savedFrame.contentDocument===savedDoc),true);
    // Late intrinsic image growth and subsequent shrink both resize the frame.
    await page.waitForFunction(()=>document.querySelector('.email-document').style.height);
    const image=await page.evaluate(()=>{
      const f=document.querySelector('.email-document');window.imageFrame=f;
      window.lateImage=f.contentDocument.createElement('img');lateImage.style.width='100%';
      f.contentDocument.querySelector('.sc-email-content').append(lateImage);
      return f.getBoundingClientRect().height;
    });
    await page.evaluate(()=>{lateImage.src='data:image/svg+xml,'+encodeURIComponent('<svg xmlns="http://www.w3.org/2000/svg" width="300" height="600"></svg>');});
    await page.waitForFunction(h=>imageFrame.getBoundingClientRect().height>h+100,image);
    await page.evaluate(()=>lateImage.remove());
    await page.waitForFunction(h=>Math.abs(imageFrame.getBoundingClientRect().height-h)<3,image);
    // A body arriving above the viewport retains the visible message's offset.
    m.messages[0].expanded=false;await page.evaluate(m=>readerTest.paint(m,true),m);
    const offset=await page.evaluate(()=>{const a=document.querySelector('[data-message-key="6"]'),s=document.querySelector('.reading-scroll');s.scrollTop=a.offsetTop;return a.getBoundingClientRect().top;});
    m.messages[0].expanded=true;await page.evaluate(m=>readerTest.paint(m),m);
    await page.waitForTimeout(150);
    const drift=await page.evaluate(old=>Math.abs(document.querySelector('[data-message-key="6"]').getBoundingClientRect().top-old),offset);
    result.after.scroll_anchor_drift_px=drift;
    assert.ok(drift<3,'Body growth moved the visible message by '+drift+'px');
    for(let i=0;i<10;i++){const switched=model(docs.after,i%2?2:12);switched.selected='switch-'+i;await page.evaluate(m=>readerTest.paint(m,true),switched);}
    await page.waitForFunction(()=>[...document.querySelectorAll('.email-document')].every(f=>f.style.height));
    result.after.rapid_switches=10;result.after.live_frame_preserved=true;result.after.late_image_grows_and_shrinks=true;
    await page.screenshot({path:'tmp/email-full-conversation.png'});
   }
   assert.deepEqual(errors,[]);await page.close();
  }
  const page=await browser.newPage({viewport:{width:1440,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://127.0.0.1/**',route=>route.fulfill({contentType:'text/html',body:'<div id="mail"></div>'}));
  await page.goto('http://127.0.0.1/synthetic-email-test');
  await page.addStyleTag({content:fs.readFileSync('components/support_email/style.css','utf8')});
  await page.addScriptTag({content:current.replace(/\}\)\(\);\s*$/,`window.readerTest={render};})();`)});
  const full={...JSON.parse(fs.readFileSync('tmp/conversation-model.json','utf8')),...model(null,100)};
  full.messages.forEach((m,i)=>m.expanded=i===0);
  await page.evaluate(m=>{
    window.hydration=m;window.bodyRequests=[];
    window.addEventListener('message',e=>{
      if(e.data.type!=='streamlit:setComponentValue')return;
      const event=e.data.value;if(event.action!=='load_conversation_body')return;
      bodyRequests.push(event.message_key);
      const next=structuredClone(hydration);next.ack=event.id;
      next.messages.find(row=>row.key===event.message_key).expanded=true;
      hydration=next;readerTest.render(next);
    });
    readerTest.render(m);
  },full);
  try{await page.waitForFunction(()=>bodyRequests.length===99&&document.querySelectorAll('.message-body').length===100,{},{timeout:10000});}
  catch(error){console.log({errors,state:await page.evaluate(()=>({requests:bodyRequests.length,bodies:document.querySelectorAll('.message-body').length,expanded:hydration.messages.filter(m=>m.expanded).length,pending:hydration.body_pending,html:document.body.textContent.slice(-500)}))});throw error;}
  assert.equal(await page.evaluate(()=>new Set(bodyRequests).size),99);
  assert.equal(await page.locator('summary,[data-action="collapse_message"],[data-tool="expand-all"]').count(),0);
  assert.deepEqual(errors,[]);
  result.automatic_hydration={messages:100,body_requests:99,duplicate_requests:0,expand_clicks:0};
  await page.close();
 }finally{fs.writeFileSync('tmp/email-full-conversation-browser.json',JSON.stringify(result,null,2));await browser.close();}
 console.log(JSON.stringify(result,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
