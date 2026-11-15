const {chromium}=require('playwright'),fs=require('fs'),crypto=require('crypto'),assert=require('node:assert/strict');
const out=process.env.EMAIL_BROWSER_EVIDENCE||'docs/email-inbox-outlook-v2a-evidence';
const port=process.env.EMAIL_BROWSER_PORT||'8553';
(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true}),checks=[];
 try{for(const width of [1440,390]){
  const context=await browser.newContext({viewport:{width,height:900}}),actor=crypto.randomUUID(),errors=[];
  await context.route('**/*',r=>new URL(r.request().url()).hostname==='127.0.0.1'?r.continue():r.abort());
  await context.addInitScript(()=>{window.__v2a={};window.addEventListener('message',e=>{
   if(e.data?.type==='streamlit:setComponentValue'){try{e.source.__v2a.pending=e.data.value.id;e.source.__v2a.action=e.data.value.action;}catch(_){}}
   if(e.data?.type==='streamlit:render')window.__v2a.model=e.data.args.model;
  });});
  async function open(){const p=await context.newPage();p.on('dialog',d=>d.accept());p.on('pageerror',e=>errors.push(e.message));await p.goto(`http://127.0.0.1:${port}/?actor=${actor}`);await p.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation-wrap').first().waitFor();return p;}
  const frame=p=>p.frames().find(f=>f.url().includes('/component/'));
  async function click(f,selector){await f.waitForFunction(s=>{const b=document.querySelector(s);return b&&!b.disabled;},selector);const prior=await f.evaluate(()=>window.__v2a.pending),action=await f.locator(selector).first().getAttribute('data-action');await f.locator(selector).first().evaluate(b=>b.click());if(action==='back')return;const expected=['recover_local_edits','recover_current_copy'].includes(action)?'recover_draft_copy':action;await f.waitForFunction(({prior,expected})=>window.__v2a.pending!==prior&&window.__v2a.action===expected&&window.__v2a.model?.ack===window.__v2a.pending,{prior,expected});}
  const first=await open();let f=frame(first);
  assert.equal(await f.evaluate(()=>window.__v2a.model.selected),null);
  await click(f,'[data-action="compose"][data-mode="new"]');
  const original=await f.evaluate(()=>window.__v2a.model.draft.id);
  await f.locator('#draft-to').fill('synthetic@example.test');await f.locator('#draft-subject').fill('Draft recovery fixture');
  await f.locator('#editor').fill('Latest text immediately before reload');
  await first.reload();await first.frameLocator('iframe[title="support_email_page.support_email_desktop"]').locator('.conversation-wrap').first().waitFor();f=frame(first);
  assert.equal(await f.evaluate(()=>window.__v2a.model.view),'mail');
  assert.equal(await f.locator('#editor').count(),0);
  assert.ok(await f.locator('[data-action="export_draft_text"]').count());
  await click(f,'[data-action="recover_local_edits"]');
  assert.match(await f.locator('#editor').innerText(),/Latest text immediately before reload/);
  const recovered=await f.evaluate(()=>window.__v2a.model.draft.id);assert.notEqual(recovered,original);
  await f.waitForFunction(()=>document.querySelector('#draft-save-status')?.textContent==='Saved');
  const second=await open(),g=frame(second);
  await click(g,`[data-action="open_local_draft"][data-draft="${recovered}"]`);
  await f.locator('#editor').fill('First tab newer durable text');await f.waitForFunction(()=>document.querySelector('#draft-save-status')?.textContent==='Saved');
  await g.locator('#editor').fill('Second tab conflicting text');
  await g.waitForFunction(()=>document.querySelector('#draft-save-status')?.textContent.startsWith('Conflict'));
  assert.match(await g.locator('#editor').innerText(),/Second tab conflicting text/);
  await click(g,'[data-action="recover_current_copy"]');
  assert.match(await g.locator('#editor').innerText(),/Second tab conflicting text/);
  assert.notEqual(await g.evaluate(()=>window.__v2a.model.draft.id),recovered);
  // Normal reconciliation must retain the actual editor node and selection/caret.
  await g.locator('#editor').fill('Caret remains during background sync');
  await g.evaluate(()=>{const editor=document.querySelector('#editor');window.savedEditor=editor;editor.focus();const range=document.createRange();range.selectNodeContents(editor);range.collapse(false);const s=getSelection();s.removeAllRanges();s.addRange(range);window.caret=s.anchorOffset;});
  await second.evaluate(()=>document.querySelector('iframe[title="support_email_page.support_email_desktop"]').contentWindow.postMessage({type:'sc:email-change',version:'synthetic-background'},location.origin));
  await g.waitForFunction(()=>window.__v2a.model?.ack===window.__v2a.pending);
  assert.equal(await g.evaluate(()=>window.savedEditor===document.querySelector('#editor')),true);
  assert.equal(await g.evaluate(()=>getSelection().anchorOffset===window.caret),true);
  await g.locator('#draft-subject').fill('SIMULATED SAVE FAILURE');
  await g.waitForFunction(()=>document.querySelector('#draft-save-status')?.textContent.startsWith('Failed'));
  assert.match(await g.locator('#editor').innerText(),/Caret remains/);
  assert.ok(await g.locator('[data-action="export_draft_text"]').count());
  await second.screenshot({path:`${out}/recovery-failure-${width}.png`});
  await g.locator('#draft-subject').fill('Storage recovered');await g.waitForFunction(()=>document.querySelector('#draft-save-status')?.textContent==='Saved');
  await click(g,'[data-action="close_composer"]');
  if(width===390){await click(g,'[data-action="back"]');assert.equal(await g.locator('.listpane').isVisible(),true);}
  checks.push({width,reload_recovered:true,explicit_recovery:true,cross_tab_conflict:true,conflict_fork:true,caret_preserved:true,failed_save_retained:true,narrow_back:true,errors});
  fs.writeFileSync(`${out}/browser-recovery.json`,JSON.stringify(checks,null,2));await context.close();console.log('Recovery verified',width);
 }}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
