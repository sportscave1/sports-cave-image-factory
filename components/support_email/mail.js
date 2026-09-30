(function () {
  'use strict';
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const size = n => Number(n) >= 1048576 ? (Number(n)/1048576).toFixed(1)+' MB' : Math.max(1, Math.round(Number(n)/1024))+' KB';
  const safeLink = value => {try {const u=new URL(value); return ['https:','http:','mailto:'].includes(u.protocol) && !u.username && !u.password ? u.href : '';} catch (_) {return '';}};
  const locked = m => Boolean((m.draft && ['accepted','unknown','in_progress'].includes((m.send_result || {}).status)) || m.draft_pending);
  const mailboxCount = m => m.error ? 'Mailbox unavailable' : (m.query ? 'Search · ' : '') + (m.threads || []).length + ' conversations';
  function messageMenuItems(target,roles,activeFolder){
    const items=[['Open','open'],['Reply','reply'],['Reply all','reply_all'],['Forward','forward'],
      [target.unread?'Mark as read':'Mark as unread',target.unread?'mark_read':'mark_unread'],
      [target.starred?'Unflag':'Flag',target.starred?'unstar':'star'],
      ['Archive','archive',!roles.archive],['Move to…','move'],['Copy to…','copy'],
      ['Junk','junk',!roles.junk],['Trash','trash',!roles.trash]];
    if(target.thread_key&&roles.trash&&activeFolder===roles.trash&&target.folder===roles.trash)
      items.push(['Delete forever','request_delete_forever']);
    return items;
  }
  function trashDeleteTarget(m,e,isBusy=false){
    if(e.key!=='Delete'||e.repeat||e.ctrlKey||e.metaKey||e.altKey||e.shiftKey||isBusy||m.delete_confirmation||
        m.view!=='mail'||!m.roles?.trash||m.folder!==m.roles.trash||!m.selected||m.error)return null;
    const typing=(e.composedPath?.()||[e.target]).some(node=>node?.isContentEditable||
      node?.closest?.('input,textarea,select,[contenteditable],[role="textbox"],[role="combobox"],[role="dialog"],[data-email-composer],.email-composer')||
      (node?.closest?.('button')&&!node.closest('.conversation')));
    return typing?null:(m.threads||[]).find(t=>t.key===m.selected)?.key||null;
  }
  function sendStatus(m) {
    const status=m.send_result?.status;
    if(m.send_stage==='SAVING_SENT_COPY') return '<div class="send-success">✓ Sent</div><div>Saving Sent copy…</div>';
    if(status==='accepted') return '<div class="send-success">✓ Sent</div>';
    if(status==='unknown') return '<div class="send-uncertain">⚠ Send status uncertain</div><small>Do not resend yet.</small>';
    if(status==='rejected') return '<div class="send-failed">✕ Not sent</div><small>Could not send this email.</small>';
    if(status==='in_progress') return `<div>${m.send_stage==='SENDING'?'Sending email…':'Validating email…'}</div>`;
    return '';
  }
  function sentReceipt(m){
    const sent=m.last_sent;
    if(!sent?.operation_id)return '';
    const copy=sent.copy||{}, saved=['present','appended'].includes(copy.status);
    return `<div class="sent-receipt" role="status"><span class="send-success">✓ Sent</span> <span>${esc(sent.subject)}</span>${saved?'':`<span class="send-pending">Email sent successfully, but ${copy.status==='pending'?'the Sent-folder copy is not visible yet.':'the Sent-folder copy could not be saved or verified.'} ${esc(copy.notice||'')}</span><button type="button" data-action="${copy.retryable?'retry_sent_copy':'check_sent'}" data-operation="${esc(sent.operation_id)}">${copy.retryable?'Retry saving Sent copy':'Check Sent copy'}</button>`}${sent.draft_warning?`<span>${esc(sent.draft_warning)}</span>`:''}</div>`;
  }
  function createViewCache(limit=20,byteLimit=8*1024*1024){
    const entries=new Map();let bytes=0;
    const remove=key=>{const old=entries.get(key);if(old){bytes-=old.size;entries.delete(key);}};
    return {get(key){const e=entries.get(key);if(!e)return null;entries.delete(key);entries.set(key,e);return e.value;},
      put(key,value){const size=new TextEncoder().encode(JSON.stringify(value)).length;remove(key);if(size>byteLimit)return;
        entries.set(key,{value,size});bytes+=size;while(entries.size>limit||bytes>byteLimit)remove(entries.keys().next().value);},
      clear(){entries.clear();bytes=0;},get size(){return entries.size;},get bytes(){return bytes;}};
  }
  function threadView(messages,folder){
    // Match the controller's initial selection, even after viewing an older thread member.
    const active=[...messages].reverse().find(m=>m.folder===folder)||messages[messages.length-1];
    if(!active?.expanded)return null;
    return {active_message:active.key,messages:messages.map(m=>({...m,expanded:m.key===active.key&&m.expanded}))};
  }
  function recoveryFeedback(m,active=false){
    const recovery=m.recovery||{};
    if(active)return '<span class="reconnect-spinner" aria-hidden="true"></span><span role="status">Reconnecting mailbox…</span>';
    if(!recovery.state)return '';
    return `<span role="status">${esc(recovery.message)}</span>${recovery.state==='stopped'?'<button type="button" data-action="retry_connection" class="connection-retry">Retry</button>':''}`;
  }
  function receivedBody(message) {
    return message.reader_document ? `<iframe class="email-document" title="Email content" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(message.reader_document)}"></iframe>` : `<div class="message-body">${message.html||''}</div>`;
  }
  function replyPromptControls(mode) {
    if(mode!=='reply')return '';
    return `<div class="reply-tools"><button type="button" data-action="reply_prompts" aria-haspopup="menu" aria-expanded="false" aria-controls="reply-prompts-popup">Prompts ▾</button><button type="button" class="reply-prompt-help" data-action="reply_prompt_help" aria-label="How prompts work" aria-expanded="false" aria-controls="reply-prompts-popup">?</button><div id="reply-prompts-popup" class="reply-prompt-popup" hidden></div><div id="reply-prompt-feedback" class="reply-prompt-feedback" role="status" aria-live="polite" hidden></div></div>`;
  }
  async function copyReplyPrompt(prompt,clipboard) {
    if(!prompt?.text || prompt.error)return {ok:false,message:prompt?.error||'5-star rating could not be confirmed for this email.'};
    try {
      if(!clipboard?.writeText)throw new Error('Clipboard unavailable');
      await clipboard.writeText(prompt.text);
      return {ok:true,message:'✓ Prompt copied — paste into ChatGPT'};
    } catch (_) {return {ok:false,message:'Could not copy the prompt. Allow clipboard access and try again.'};}
  }
  if (typeof module !== 'undefined') {module.exports={receivedBody,replyPromptControls,copyReplyPrompt,esc,size,safeLink,locked,mailboxCount,messageMenuItems,trashDeleteTarget,sendStatus,sentReceipt,createViewCache,threadView,recoveryFeedback}; return;}
  const root=document.getElementById('mail');
  let model={}, busy=false, pending='', collapsed=false, mobileReading=false, localDraft=null, downloaded='', selection=null;
  let pendingAction='', queued=null, historyTimer=null, lastHeight=0, readingStamp='', listStamp='', folderStamp='', toolbarStamp='';
  let selectionControlsDisabled=false;
  let replyPromptFeedbackTimer=null;
  const views=createViewCache();
  const submitted=new Set();
  let lastLiveCheck=Date.now(), menu=null, menuTarget=null, focusSearch=false;
  let pendingSignal='', seenSignal='';
  let signalAttempts=0, signalRetryTimer=null;
  function signalTick(version){
    if(model.recovery?.state)return;
    if(typeof version!=='string'||!version||version.length>128||version===seenSignal)return;
    pendingSignal=version;
    if(busy||menu||model.delete_confirmation||document.hidden||!model.configured)return;
    seenSignal=version;pendingSignal='';signalAttempts=0;
    emit('live_check',{signal_version:version});
  }
  function liveTick(){
    if(model.recovery?.state)return; // Dedicated bounded recovery owns outage attempts.
    if(pendingSignal){signalTick(pendingSignal);return;}
    if(busy||menu||model.delete_confirmation||document.hidden||!model.configured||Date.now()-lastLiveCheck<55000)return;
    lastLiveCheck=Date.now();emit('live_check');
  }
  // Only standalone fixtures/embeds need a timer; the OS supplies its existing heartbeat.
  let standaloneTimer=null;
  try{if(!window.parent.SportsCaveTopBar)standaloneTimer=setInterval(()=>{
    // The shell may finish mounting after this iframe. Relinquish fallback ownership.
    if(window.parent.SportsCaveTopBar){clearInterval(standaloneTimer);standaloneTimer=null;return;}
    liveTick();
  },30000);}catch(_){}
  window.addEventListener('pagehide',()=>clearInterval(standaloneTimer));
  let sentTimer=null;
  function scheduleSentCheck(){
    clearTimeout(sentTimer);
    const sent=model.last_sent;
    if(!sent?.operation_id||sent.copy?.status!=='pending'||sent.checks>=3||busy)return;
    sentTimer=setTimeout(()=>emit('auto_check_sent',{operation_id:sent.operation_id}),[6000,12000,24000][sent.checks||0]);
  }
  window.addEventListener('pagehide',()=>clearTimeout(sentTimer));
  let sendTimer=null;
  function scheduleSendStage(){
    clearTimeout(sendTimer);
    if(busy||!model.send_result?.operation_id||!['SENDING','SAVING_SENT_COPY'].includes(model.send_stage))return;
    const operation_id=model.send_result.operation_id;
    // Only continue the operation created by an explicit Send click, after painting its real stage.
    sendTimer=setTimeout(()=>emit('advance_send',{operation_id}),100);
  }
  window.addEventListener('pagehide',()=>clearTimeout(sendTimer));
  let reconnectTimer=null;
  function scheduleReconnect(){
    clearTimeout(reconnectTimer);
    if(model.recovery?.state!=='waiting')return;
    reconnectTimer=setTimeout(()=>{
      if(busy||menu||model.delete_confirmation||document.hidden){scheduleReconnect();return;}
      emit('reconnect');
    },Math.max(1000,model.recovery.delay_ms||0));
  }
  window.addEventListener('pagehide',()=>clearTimeout(reconnectTimer));
  const post=(type,extra={})=>window.parent.postMessage({isStreamlitMessage:true,type,...extra},'*');
  const $=id=>document.getElementById(id);
  const button=(label,action,data='',disabled=false,klass='')=>`<button type="button" class="${klass}" data-action="${action}" ${data} ${disabled?'disabled':''}>${label}</button>`;
  function snapshot() {
    if (!$('editor') || !model.draft || locked(model)) return localDraft;
    localDraft={id:model.draft.id,html:$('editor').innerHTML,signature:$('signature').value,include_quote:!!$('include-quote')?.checked};
    for (const key of ['to','cc','bcc','subject']) localDraft[key]=$('draft-'+key).value;
    return localDraft;
  }
  function emit(action, values={}) {
    const selecting=['open_thread','open_message'].includes(action);
    if (busy) {
      if(selecting || ['open_thread','open_message','resolve_thread','load_visible_body','load_initial_mailbox','auto_check_sent','live_check'].includes(pendingAction)){
        queued={action,values};
        if(selecting) optimistic(action,values);
      }
      return;
    }
    const draft=snapshot();
    if(action==='send'){model.send_result={status:'in_progress'};model.sent_result={};model.send_stage='VALIDATING';if($('send-status'))$('send-status').innerHTML=sendStatus(model);}
    clearTimeout(historyTimer);
    pending=crypto.randomUUID(); busy=true; pendingAction=action;
    if(selecting) optimistic(action,values);
    else if(!['resolve_thread','load_visible_body','load_initial_mailbox','auto_check_sent','live_check','reconnect'].includes(action)){root.classList.add('busy');freeze();}
    if (!selecting && !['resolve_thread','load_visible_body','load_initial_mailbox','auto_check_sent','live_check'].includes(action) && $('notice')) $('notice').textContent=action==='send'?'Sending…':action==='download'?'Opening attachment…':action==='refresh'?'Refreshing…':'Working…';
    if(['reconnect','retry_connection'].includes(action)&&$('notice'))$('notice').innerHTML=recoveryFeedback(model,true);
    post('streamlit:setComponentValue',{value:{id:pending,action,...values,draft},dataType:'json'});
  }
  const viewKey=(m,key)=>JSON.stringify([m.mailbox,m.mailbox_version,key]);
  function markSelection(){
    root.querySelectorAll('.conversation').forEach(e=>{const active=e.dataset.key===model.selected;e.classList.toggle('selected',active);e.setAttribute('aria-selected',String(active));});
  }
  function optimistic(action,values){
    snapshot();mobileReading=true;
    if(action==='open_thread'){
      const hit=views.get(viewKey(model,values.thread_key));
      model={...model,view:'mail',selected:values.thread_key,messages:hit?.messages||[],active_message:hit?.active_message};
      if(hit)paintReading(true,true);
      if(!hit){
        const t=model.threads.find(t=>t.key===values.thread_key);
        root.querySelector('.reading').innerHTML=`<div class="subject-header"><h2>${esc(t?.subject||'')}</h2><div class="customer">${esc(t?.customer||'')}</div><small>${esc(t?.email||'')}</small></div><div class="message-loading" role="status">Loading message…</div>`;
        readingStamp='';
      }
    }else{
      model={...model,active_message:values.message_key};
      paintReading();
      const row=model.messages.find(m=>m.key===values.message_key);
      if(row&&!row.expanded){
        const article=[...root.querySelectorAll('.message-head')].find(e=>e.dataset.key===values.message_key)?.closest('article');
        if(article&&!article.querySelector('.message-loading'))article.insertAdjacentHTML('beforeend','<div class="message-loading" role="status">Loading message…</div>');
      }
    }
    markSelection();
    root.querySelector('.workspace').classList.toggle('show-reading',mobileReading);
    // Cached content can paint instantly; writes wait until the server validates this selection.
    root.querySelectorAll('.reading button').forEach(e=>e.disabled=true);
    selectionControlsDisabled=true;
  }
  function freeze(){
    root.querySelectorAll('button,input,select,textarea').forEach(e=>e.disabled=true);
    root.querySelectorAll('[contenteditable=true]').forEach(e=>e.contentEditable='false');
  }
  function fit() {
    let height=700;
    try {height=Math.max(280,Math.floor(window.parent.innerHeight-window.frameElement.getBoundingClientRect().top-6));} catch (_) {}
    if(height!==lastHeight){lastHeight=height;root.style.height=height+'px';post('streamlit:setFrameHeight',{height});}
  }
  const roleLabels={inbox:'Inbox',sent:'Sent',drafts:'Drafts',archive:'Archive',junk:'Junk',trash:'Trash'};
  const symbols={inbox:'▤',sent:'↗',drafts:'▧',archive:'▣',junk:'⊘',trash:'⌫'};
  const roleOf=f=>Object.keys(model.roles||{}).find(r=>model.roles[r]===f.name);
  function inboxUnread(payload) {
    if (!Number.isInteger(payload?.unread_count) || Date.now()/1000-Number(payload.checked_at||0)>120) return;
    if (Number(payload.checked_at||0)<Number(model.inbox_status?.checked_at||0)) return;
    model.inbox_status=payload;
    const folder=(model.folders||[]).find(f=>f.name.toUpperCase()==='INBOX');
    if(folder)folder.unread=payload.unread_count;
    const count=root.querySelector('[data-action="folder"][data-folder="INBOX"] .folder-count');
    if(count)count.textContent=payload.unread_count>0?String(payload.unread_count):'';
  }
  function folders() {
    return `<nav class="folders" aria-label="Mail folders"><div class="folder-heading label">Mailbox</div>${model.initial_load_pending?Object.values(roleLabels).map(label=>`<div class="folder muted">${esc(label)}</div>`).join(''):''}${(model.folders||[]).map(f=>{
      const role=roleOf(f); return `<div class="folder-wrap"><button class="folder ${model.folder===f.name?'selected':''}" data-action="folder" data-folder="${esc(f.name)}" title="${esc(f.label)}" aria-label="${esc(roleLabels[role]||f.label)}"><span class="folder-symbol">${symbols[role]||'▱'}</span><span class="folder-name">${esc(roleLabels[role]||f.label)}</span><span class="folder-count">${f.unread>0?esc(f.unread):''}</span></button><button class="folder-more" data-action="folder_menu" data-folder="${esc(f.name)}" aria-label="Actions for ${esc(roleLabels[role]||f.label)}">⋯</button></div>`;
    }).join('')}${button('☰ <span>Collapse folders</span>','collapse','','', 'collapse plain')}</nav>`;
  }
  function conversations() {
    const folder=(model.folders||[]).find(f=>f.name===model.folder);
    return `<section class="listpane" aria-label="Conversations"><div class="list-heading row spread"><strong>${esc(roleLabels[roleOf(folder||{})]||folder?.label||'Mailbox')}</strong><small>${esc(mailboxCount(model))}</small></div><div class="conversations">${model.error?`<div class="empty">${esc(model.error)}</div>`:(model.threads||[]).map(t=>`<div class="conversation-wrap"><button class="conversation ${t.unread?'unread':''} ${model.selected===t.key?'selected':''}" data-action="open_thread" data-key="${esc(t.key)}" aria-label="${esc(t.customer+' · '+t.subject)}"><div class="row spread"><span class="sender ellipsis">${esc(t.customer||t.email||'Unknown sender')}</span><time>${esc(t.time)}</time></div><div class="subject ellipsis">${esc(t.subject)}</div><div class="row spread"><span class="preview ellipsis grow">${esc(t.snippet||'Open conversation')}</span><small>${t.attachment?'⌁ ':''}${t.starred?'★ ':''}${t.count>1?t.count:''}</small></div></button><button class="row-more" data-action="message_menu" data-key="${esc(t.key)}" aria-label="More actions for ${esc(t.subject)}">⋯</button></div>`).join('')||`<div class="empty">${model.initial_load_pending?'Loading conversations…':'No messages in this view.'}</div>`}</div><div class="list-footer">${model.has_more&&!model.error?button('Load 50 more','load_more'): '<span class="muted">'+(model.error?'Mailbox unavailable':model.live_error?'Cached mailbox · last successful view':model.query?'Live search · current folder':'Live mailbox · latest messages')+'</span>'}</div></section>`;
  }
  const names=people=>(people||[]).map(p=>p.name?`${p.name} <${p.email}>`:p.email).join(', ');
  function messages() {
    const rows=model.messages||[], active=rows.find(m=>m.key===model.active_message)||rows[rows.length-1];
    const selectedThread=(model.threads||[]).find(t=>t.key===model.selected);
    if (!active) return `<div class="reading-scroll empty">${model.error?esc(model.error):'Select a conversation to read it.'}${model.draft?'<p class="attachments">'+button('Resume draft','resume_composer')+'</p>':''}</div>`;
    return `<div class="reading-toolbar">${button('←','back','','','mobile-back')}${button('Reply','compose','data-mode="reply"')}${button('Reply all','compose','data-mode="reply_all"')}${button('Forward','compose','data-mode="forward"')}<span class="grow"></span>${button('Archive','archive','',!model.roles.archive)}${button('Trash','trash','',!model.roles.trash)}${button(active.unread?'Mark read':'Mark unread',active.unread?'mark_read':'mark_unread')}${button(active.starred?'★':'☆',active.starred?'unstar':'star','title="Star / unstar"')}${button('Junk','junk','',!model.roles.junk)}${button('⋯','message_menu','title="More message actions" aria-label="More message actions"')}</div><div class="reading-scroll"><div class="subject-header"><div class="row spread"><h2>${esc(active.subject)}</h2>${button('Customer / Order','context','','','plain')}</div><div class="customer">${esc(selectedThread?.customer||active.sender.name||active.sender.email)}</div><small>${esc(selectedThread?.email||active.sender.email)}</small><div class="meta">Actions apply to the selected message · ${esc(active.folder)} · ${esc(active.time)}</div>${active.draft?'<div class="attachments">'+button('Edit mailbox draft','edit_draft')+'</div>':''}${model.draft?'<div class="attachments">'+button('Resume draft','resume_composer')+'</div>':''}</div><div class="messages">${rows.map(m=>`<article class="message ${m.key===active.key?'active':''}"><button class="message-head" data-action="open_message" data-key="${esc(m.key)}" aria-expanded="${m.expanded}"><div class="row spread"><span class="label">${m.own?'Sports Cave':'Customer'} ${m.expanded?'':'· expand'}</span><small>${esc(m.time)}</small></div><div class="person">${esc(m.sender.name||m.sender.email)}</div><div class="meta">${esc(m.sender.email)}${m.expanded?'<br>To: '+esc(names(m.to))+(m.cc.length?' · CC: '+esc(names(m.cc)):''):''}</div></button>${m.expanded?`${receivedBody(m)}${m.quote&&!m.reader_document?`<details><summary>Show quoted text</summary><div class="quote">${m.quote}</div></details>`:''}${(m.warnings||[]).map(w=>'<p class="muted">'+esc(w)+'</p>').join('')}<div class="attachments">${m.attachments.map(a=>button('⌁ '+esc(a.filename)+' · '+size(a.encoded_size)+' ↓','download',`data-key="${esc(m.key)}" data-section="${esc(a.section)}" title="Download directly from mailbox"`)).join('')}</div>`:''}</article>`).join('')}</div></div>`;
  }
  function formatBar(target='editor') {
    return `<div class="format-bar" data-editor="${target}">${[['B','bold'],['I','italic'],['U','underline'],['↗ Link','createLink'],['• List','insertUnorderedList'],['1. List','insertOrderedList']].map(([label,cmd])=>`<button type="button" data-command="${cmd}" title="${cmd}" ${target==='editor'&&locked(model)?'disabled':''}>${label}</button>`).join('')}</div>`;
  }
  function signaturePreview(key) {
    return (model.settings.signatures[key]?.html||'').replaceAll('cid:sports-cave-signature-logo@sportscaveshop.com',model.signature_logo||'');
  }
  function signaturesOptions(value,none=true) {
    return Object.entries(model.settings.signatures).map(([key,s])=>`<option value="${key}" ${value===key?'selected':''}>${esc(s.label)}</option>`).join('')+(none?`<option value="none" ${value==='none'?'selected':''}>No signature</option>`:'');
  }
  function composer() {
    if (!model.draft) return messages();
    const draft={...model.draft,...(localDraft?.id===model.draft.id?localDraft:{})}, lock=locked(model), status=model.send_result?.status;
    const forwarded=draft.mode==='forward'?(model.messages||[]).flatMap(m=>m.attachments.map(a=>({...a,message_key:m.key}))):[];
    return `<section class="panel" aria-label="Compose mail"><div class="panel-head"><div class="reply-heading"><strong>${{new:'New mail',reply:'Reply',reply_all:'Reply all',forward:'Forward'}[draft.mode]||'Draft'}</strong>${replyPromptControls(draft.mode)}</div>${button('Close · Esc','close_composer','','','plain')}</div><div class="compose-fields"><div class="compose-field"><label>From</label><span>${esc(model.settings.sender_name)} &lt;${esc(model.mailbox)}&gt;</span></div>${['to','cc','bcc','subject'].map(key=>`<div class="compose-field"><label for="draft-${key}">${key==='subject'?'Subject':key.toUpperCase()}</label><input id="draft-${key}" value="${esc(draft[key])}" ${lock?'disabled':''} autocomplete="off" maxlength="${key==='subject'?998:4000}" placeholder="${key==='to'?'name@example.com':''}"></div>`).join('')}</div>${formatBar()}<div class="compose-scroll"><div id="editor" class="editor" contenteditable="${!lock}" role="textbox" aria-label="Message body" aria-multiline="true">${draft.html}</div><div id="signature-preview" class="signature-preview" contenteditable="false" role="group" aria-label="Signature preview">${signaturePreview(draft.signature)}</div>${draft.quote_html?`<details><summary>Previous message</summary><label class="checkbox"><input id="include-quote" type="checkbox" ${draft.include_quote?'checked':''} ${lock?'disabled':''}>Include quoted message</label><div class="quote">${draft.quote_html}</div>${forwarded.length?'<p class="muted">Include original attachments:</p><div class="attachments">'+forwarded.map(a=>button('＋ '+esc(a.filename),'forward_attachment',`data-key="${esc(a.message_key)}" data-section="${esc(a.section)}"`,lock)).join('')+'</div>':''}</details>`:''}<div class="attachments">${draft.attachments.map(a=>`<span class="pill">⌁ ${esc(a.filename)} <small>${size(a.size)}</small>${button('×','remove_attachment',`data-attachment="${esc(a.id)}" title="Remove attachment"`,lock)}</span>`).join('')}</div></div><div class="compose-bottom"><div id="send-status" class="send-status" role="status" aria-live="polite" aria-atomic="true">${sendStatus(model)}</div>${['accepted','unknown'].includes(status)&&model.sent_result?.status!=='present'?button('Check Sent copy','check_sent'):status==='rejected'?button('Try again','retry_rejected'):''}<div class="row wrap">${status==='accepted'?button('Close','close_composer','','','primary'):button('Send','send','title="Ctrl+Enter"',lock||status==='rejected'||!model.smtp_configured,'primary')}${button('Attach file','choose_file','',lock)}<input id="attachment" class="hidden-file" type="file" ${lock?'disabled':''}>${button('Save draft','save_draft','',!model.roles.drafts||['accepted','unknown','in_progress'].includes(status))}<span class="grow"></span><select id="signature" aria-label="Signature" ${lock?'disabled':''}>${signaturesOptions(draft.signature)}</select>${button('Discard','discard_draft','',lock,'plain')}</div>${!model.smtp_configured?'<small>SMTP needs configuration before sending.</small>':'<small>10 MB per file · 14 MB attachments total · 20 MB encoded message</small>'}${model.draft_pending?'<p class="muted">Draft save is pending. Save draft checks for its existing copy.</p>':''}</div></section>`;
  }
  function settings() {
    const s=model.settings;
    const previews=Object.entries(s.signatures).map(([key,sig])=>`<div><label>${esc(sig.label)} <small>Preview</small></label>${model.admin?formatBar('sig-'+key):''}<div id="sig-${key}" class="signature-edit" contenteditable="${model.admin}" role="${model.admin?'textbox':'group'}" aria-label="${esc(sig.label)} signature">${signaturePreview(key)}</div></div>`).join('');
    const mailbox=model.admin?`<div class="section stack"><div class="label">Mailbox settings</div><label>Sender display name<input id="sender-name" value="${esc(s.sender_name)}" maxlength="120"></label><div class="mapping">${['sent','drafts','archive','junk','trash'].map(role=>`<label for="map-${role}">${roleLabels[role]}</label><select id="map-${role}"><option value="">Use special-use discovery</option>${model.folders.filter(f=>f.name.toUpperCase()!=='INBOX').map(f=>`<option value="${esc(f.name)}" ${s.folder_mapping[role]===f.name?'selected':''}>${esc(f.label)}</option>`).join('')}</select>`).join('')}</div><label>Sent copy handling<select id="sent-policy">${[['verify','Automatic · find or save Sent copy'],['server','Server saves Sent · confirmed'],['append','App saves Sent copy']].map(([v,l])=>`<option value="${v}" ${s.sent_policy===v?'selected':''}>${l}</option>`).join('')}</select></label><small>Automatic checks the real Sent folder by Message-ID before saving a missing copy. Use server saving only when confirmed for this mailbox.</small></div>`:'';
    return `<section class="panel"><div class="panel-head"><strong>Email settings</strong>${button('Close','close_panel','','','plain')}</div><div class="panel-scroll stack"><div><div class="label">Connection</div><p>${esc(model.mailbox)}</p><small>IMAP ${model.configured?'configured':'not configured'} · SMTP ${model.smtp_configured?'configured':'not configured'}</small></div>${button('Test IMAP connection','test_connection','',!model.configured)}<label>Your default signature<select id="preference">${signaturesOptions(model.signature_preference)}</select></label>${button('Save my preference','save_preference','',!model.settings_available)}${!model.settings_available?'<small>Settings storage is unavailable. Defaults remain usable.</small>':''}${mailbox}<div class="section stack"><div class="label">Signatures</div>${previews}${model.admin?button('Save mailbox settings','save_settings','',!model.settings_available,'primary'):''}</div></div></section>`;
  }
  function external(label,url){url=safeLink(url); return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:'';}
  function appURL(query) {try{return window.parent.location.href.split('?')[0].split('#')[0]+query;}catch(_){return '';}}
  function contextPanel(){
    const c=model.context||{},o=c.order,w=c.workflow||{};
    return `<section class="panel"><div class="panel-head"><strong>Customer / Order</strong>${button('Close','close_panel','','','plain')}</div><div class="panel-scroll"><h3>${esc(c.label||'No order matched')}</h3>${(c.candidates||[]).map(v=>'<p class="context-item">'+esc(v.name)+' · '+esc(v.date)+'</p>').join('')}${o?`<div class="context-item"><strong>${esc(o.name)}</strong><br>${esc(o.date)}<br>Fulfilment: ${esc(o.fulfilment)}</div>${o.lines.map(l=>`<div class="context-item">${esc(l.product_title)}<br><small>${esc(l.variant_title)}</small></div>`).join('')}${o.editions.map(e=>`<div class="context-item">Edition ${esc(e.edition_number)} / ${esc(e.edition_total)}<br>Certificate: ${esc(e.certificate_status||'Not recorded')}<br>${external('Open Edition',appURL(o.edition_url))}</div>`).join('')}<div class="section stack">${external('Open Shopify order',o.shopify_url)}${external('Open Sports Cave order',appURL(o.os_url))}${o.tracking.map(u=>external('Open tracking',u)).join('')}</div>${o.previous.length?'<div class="section"><div class="label">Previous orders</div>'+o.previous.map(p=>'<p class="context-item">'+esc(p.name)+' · '+esc(p.date)+'</p>').join('')+'</div>':''}`:''}<div class="section stack"><div class="label">Internal support workflow</div>${c.workflow_available&&!w.conflict?`<label>Status<select id="workflow-status">${['Needs Reply','Waiting on Customer','Waiting on Sports Cave','Resolved'].map(s=>`<option ${w.support_status===s?'selected':''}>${s}</option>`).join('')}</select></label><label>Assigned<select id="workflow-assigned"><option value="">Unassigned</option>${c.assignees.map(a=>`<option value="${esc(a.id)}" ${w.assigned_user_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select></label><label>Internal notes<textarea id="workflow-notes" maxlength="8000">${esc(w.internal_notes||'')}</textarea></label><label class="checkbox"><input id="workflow-approval" type="checkbox" ${w.needs_approval?'checked':''}>Requires Nathan's approval</label><small>Internal only. Notes are never included in email.</small>${button('Save workflow','workflow')}`:'<small>Workflow metadata is unavailable or conflicting. Mail remains in the live mailbox.</small>'}</div></div></section>`;
  }
  function paintReading(force=false,reset=false){
    const stamp=JSON.stringify([model.selected,model.view,model.active_message,model.messages,model.error,model.draft,model.send_result,model.send_stage,model.sent_result,model.draft_pending,model.context,model.settings,model.settings_available,model.signature_preference]);
    const pane=root.querySelector('.reading');if(!pane)return;
    if(force||stamp!==readingStamp){
      const old=pane.querySelector('.reading-scroll,.compose-scroll,.panel-scroll');const top=reset?0:old?.scrollTop||0;
      pane.querySelectorAll('.email-document').forEach(frame=>frame._emailObserver?.disconnect());
      pane.innerHTML=model.view==='compose'?composer():model.view==='settings'?settings():model.view==='context'?contextPanel():messages();
      const scroll=pane.querySelector('.reading-scroll,.compose-scroll,.panel-scroll');if(scroll)scroll.scrollTop=top;
      pane.querySelectorAll('.email-document').forEach(frame=>{
        frame.onload=()=>{
          try {
            const body=frame.contentDocument.body;
            const resize=()=>{if(frame.isConnected)frame.style.height=Math.max(60,body.scrollHeight)+'px';};
            resize();const observer=new ResizeObserver(resize);observer.observe(body);
            frame._emailObserver=observer;
            body.querySelectorAll('img').forEach(img=>img.addEventListener('error',()=>{img.alt=img.alt||'Image unavailable';resize();},{once:true}));
          } catch(_) {frame.style.height='480px';}
        };
      });
      readingStamp=stamp;
      selectionControlsDisabled=false;
    }
  }
  function render(next) {
    // The fragment first receives the old model before processing its event. Ignore that echo.
    if(pending&&next.ack!==pending)return;
    const liveUpdate=['live_check','reconnect'].includes(pendingAction);
    if(liveUpdate)snapshot(); // Keep edits made while the network read was in flight.
    const oldFolder=model.folder, oldQuery=model.query;
    const wasFrozen=busy&&!['open_thread','open_message','resolve_thread','load_visible_body','load_initial_mailbox','auto_check_sent','live_check','reconnect'].includes(pendingAction);
    const selectionChanged=next.selected!==model.selected;
    if(next.mailbox_version!==model.mailbox_version||next.mailbox!==model.mailbox||next.error)views.clear();
    if (next.draft?.id!==model.draft?.id || next.send_result?.status==='accepted') localDraft=null;
    model=next;

    try {
      window.parent.SportsCaveTopBar?.mailboxUnreadChanged?.(model.inbox_status||{});
      inboxUnread(window.parent.SportsCaveTopBar?.emailUnreadStatus?.());
    } catch (_) {}
    if (model.ack===pending) {
      busy=false;pending='';pendingAction='';
      if (model.draft && !model.send_result?.status) submitted.delete(model.draft.operation_id);
    }
    if (model.draft && !localDraft) localDraft=Object.fromEntries(['id','to','cc','bcc','subject','html','signature','include_quote'].map(k=>[k,model.draft[k]]));
    if (model.draft && localDraft) localDraft.operation_id=model.draft.operation_id;
    if(model.view==='mail'&&!model.error&&model.selected){
      const cached=threadView(model.messages,model.folder);
      views.put(viewKey(model,model.selected),cached);
    }
    if(queued){const action=queued;queued=null;emit(action.action,action.values);return;}
    root.classList.remove('busy');
    scheduleSentCheck();
    scheduleSendStage();
    if(!root.querySelector('.workspace'))root.innerHTML='<header class="topbar"></header><div class="statusbar"></div><div class="delivery-receipt"></div><main class="workspace"><nav class="folders"></nav><section class="listpane"></section><section class="reading" aria-label="Reading and compose pane"></section></main>';
    root.querySelector('.delivery-receipt').innerHTML=(model.pending_sent||[]).map(last_sent=>sentReceipt({last_sent})).join('')+sentReceipt(model);
    const toolbarKey=JSON.stringify([model.configured,model.query,model.field]);
    if(wasFrozen||toolbarKey!==toolbarStamp){
      root.querySelector('.topbar').innerHTML=`<h1 class="brand">EMAIL</h1>${button('＋ New mail','compose','data-mode="new"',!model.configured,'primary')}<form id="search-form" class="search"><input id="search" aria-label="Search current mailbox folder" placeholder="Search mail · name, subject, order number" value="${esc((model.field!=='TEXT'&&model.query?model.field.toLowerCase()+': ':'')+model.query)}" maxlength="256"><button title="Search the live mailbox, including older messages">Search</button></form>${button('↻ Refresh','refresh','',!model.configured)}${button('⚙','settings','title="Email settings"')}`;
      toolbarStamp=toolbarKey;
    }
    root.querySelector('.statusbar').innerHTML=`<span title="Mail source: VentraIP IMAP"><span class="dot ${model.error||model.live_error||!model.configured?'off':''}"></span>${model.initial_load_pending?'Loading mailbox…':!model.configured?'Not configured':model.recovery?.state==='stopped'?'Connection unavailable':model.error?'Connection error':model.live_error?'Connection interrupted · Reconnecting…':'Live'} · ${esc(model.mailbox)}${model.refreshed?' · '+esc(model.refreshed):''}</span><span id="notice" class="notice" role="status" title="${esc(model.notice||model.error)}">${esc(model.notice||model.error)}</span>`;
    if(model.recovery?.state){
      $('notice').innerHTML=recoveryFeedback(model);
    }
    scheduleReconnect();
    const foldersKey=JSON.stringify([model.folders,model.roles,model.folder,model.initial_load_pending]);
    if(wasFrozen||foldersKey!==folderStamp){const node=root.querySelector('.folders'),top=node.scrollTop;node.outerHTML=folders();root.querySelector('.folders').scrollTop=top;folderStamp=foldersKey;}
    const listKey=JSON.stringify([model.mailbox_version,model.folder,model.query,model.field,model.error,Boolean(model.live_error),model.limit,model.initial_load_pending]);
    if(wasFrozen||listKey!==listStamp){const node=root.querySelector('.listpane'),top=node.querySelector('.conversations')?.scrollTop||0;node.outerHTML=conversations();root.querySelector('.conversations').scrollTop=oldFolder===model.folder&&oldQuery===model.query?top:0;listStamp=listKey;}
    root.querySelector('.workspace').className=`workspace ${collapsed?'collapsed':''} ${mobileReading?'show-reading':''}`;
    markSelection();if(!(liveUpdate&&model.view==='compose'))paintReading(wasFrozen,selectionChanged);
    // Selection-only reads never freeze folder/list/toolbar nodes. Re-enable selected-message controls
    // by repainting only their pane after the server acknowledges the selected reference.
    if(selectionControlsDisabled&&!locked(model)&&model.view==='mail')paintReading(true);
    wire();renderDeleteConfirmation();fit();
    if(pendingSignal&&!busy)setTimeout(()=>signalTick(pendingSignal),0);
    clearTimeout(signalRetryTimer);
    if(seenSignal&&model.idle_version!==seenSignal&&signalAttempts<3&&!busy){
      const version=seenSignal;
      signalRetryTimer=setTimeout(()=>{
        if(!busy&&!menu&&!document.hidden&&seenSignal===version){
          signalAttempts++;emit('live_check',{signal_version:version});
        }
      },1500);
    }
    if(focusSearch&&!busy){focusSearch=false;$('search')?.focus();}
    if(model.download && model.download.id!==downloaded){
      downloaded=model.download.id;
      const bytes=Uint8Array.from(atob(model.download.base64),c=>c.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
      const a=document.createElement('a'); a.href=url;a.download=model.download.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
    }
    clearTimeout(historyTimer);
    if(model.initial_load_pending){
      historyTimer=setTimeout(()=>{if(!busy&&model.initial_load_pending)emit('load_initial_mailbox');},0);
    }else if(model.body_pending&&model.view==='mail'&&!model.error){
      const message_key=model.body_pending;
      historyTimer=setTimeout(()=>{if(!busy&&model.active_message===message_key)emit('load_visible_body',{message_key});},0);
    } else if(model.history_pending&&model.view==='mail'&&!model.error){
      const key=model.selected,version=model.mailbox_version;
      // Yield first paint. This fetches headers only, never speculative bodies or attachments.
      historyTimer=setTimeout(()=>{if(!busy&&model.selected===key&&model.mailbox_version===version)emit('resolve_thread',{thread_key:key,mailbox_version:version});},120);
    }
  }
  function compose(mode) {
    if (model.draft && !locked(model) && !confirm('Replace this open compose session? Save a mailbox draft first if you want to keep it.')) return;
    localDraft=null;mobileReading=true;emit('compose',{mode,message_key:model.active_message});
  }
  function send(){
    if(!model.draft||busy||locked(model)||!model.smtp_configured||model.send_result?.status==='rejected')return;
    const id=model.draft.operation_id;if(submitted.has(id))return;
    submitted.add(id);emit('send',{operation_id:id});
  }
  function closeReplyPrompts() {
    const popup=$('reply-prompts-popup');
    if(popup)popup.hidden=true;
    root.querySelectorAll('[data-action="reply_prompts"],[data-action="reply_prompt_help"]').forEach(b=>b.setAttribute('aria-expanded','false'));
  }
  function positionReplyPopup(popup,anchor) {
    const rect=anchor.getBoundingClientRect();
    popup.style.left=Math.max(8,Math.min(rect.left,window.innerWidth-popup.offsetWidth-8))+'px';
    popup.style.top=Math.max(8,Math.min(rect.bottom+7,window.innerHeight-popup.offsetHeight-8))+'px';
  }
  function showReplyPrompts(button,help=false) {
    const popup=$('reply-prompts-popup');if(!popup)return;
    const feedback=$('reply-prompt-feedback');if(feedback)feedback.hidden=true;
    clearTimeout(replyPromptFeedbackTimer);
    const wasOpen=!popup.hidden&&popup.dataset.kind===(help?'help':'menu');
    closeReplyPrompts();if(wasOpen)return;
    popup.dataset.kind=help?'help':'menu';
    popup.setAttribute('role',help?'note':'menu');
    popup.innerHTML=help?`<strong>HOW PROMPTS WORK</strong><p>Choose a reply prompt and Sports Cave OS will add the customer, product and message details automatically.</p><p>Copy the prompt into ChatGPT, then paste ChatGPT's finished reply back into this email.</p>`:
      (model.reply_prompts?.length?model.reply_prompts:[{id:'five_star_review',label:'5-star review response'}]).map(p=>`<button type="button" role="menuitem" data-action="copy_reply_prompt" data-prompt="${esc(p.id)}">${esc(p.label)}</button>`).join('');
    popup.hidden=false;button.setAttribute('aria-expanded','true');positionReplyPopup(popup,button);
    if(!help)popup.querySelector('button')?.focus();
  }
  async function copySelectedReplyPrompt(id) {
    const prompt=(model.reply_prompts||[]).find(p=>p.id===id);
    const feedback=$('reply-prompt-feedback'),anchor=root.querySelector('[data-action="reply_prompts"]');
    closeReplyPrompts();
    const result=await copyReplyPrompt(prompt,navigator.clipboard);
    if(!feedback?.isConnected)return;
    feedback.textContent=result.message;feedback.hidden=false;feedback.dataset.error=String(!result.ok);
    positionReplyPopup(feedback,anchor);clearTimeout(replyPromptFeedbackTimer);
    replyPromptFeedbackTimer=setTimeout(()=>{feedback.hidden=true;},result.ok?4000:6500);
  }
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('.reply-tools'))closeReplyPrompts();});
  window.addEventListener('resize',closeReplyPrompts);
  function wire(){
    $('search-form').onsubmit=e=>{e.preventDefault();emit('search',{query:$('search').value});};
    root.onclick=e=>{
      const more=e.target.closest('[data-action="message_menu"],[data-action="folder_menu"]');
      if(more){const rect=more.getBoundingClientRect();showMenu(targetFor(more),rect.right,rect.bottom);return;}
      const b=e.target.closest('button');if(!b||b.disabled)return;
      if(b.dataset.command){
        const target=$(b.closest('[data-editor]').dataset.editor);if(target.contentEditable!=='true')return;
        target.focus();if(selection&&target.contains(selection.commonAncestorContainer)){const s=window.getSelection();s.removeAllRanges();s.addRange(selection);}
        let value=null;if(b.dataset.command==='createLink'){value=safeLink(prompt('Link URL (https://… or mailto:…)')||'');if(!value)return;}
        document.execCommand(b.dataset.command,false,value);snapshot();return;
      }
      const action=b.dataset.action;if(!action)return;
      if(action==='reply_prompts'){showReplyPrompts(b);return;}
      if(action==='reply_prompt_help'){showReplyPrompts(b,true);return;}
      if(action==='copy_reply_prompt'){void copySelectedReplyPrompt(b.dataset.prompt);return;}
      if(action==='collapse'){collapsed=!collapsed;snapshot();render(model);return;}
      if(action==='back'){mobileReading=false;snapshot();render(model);return;}
      if(action==='compose'){compose(b.dataset.mode);return;}
      if(action==='send'){send();return;}
      if(action==='choose_file'){$('attachment').click();return;}
      if(action==='discard_draft'&&!confirm(model.draft?.saved?'Move the saved draft to Trash?':'Discard this unsaved draft?'))return;
      if(['trash','junk'].includes(action)&&!confirm(`Move this message to ${action==='trash'?'Trash':'Junk'}?`))return;
      let data={message_key:b.dataset.key||model.active_message};
      if(action==='open_thread'){data.thread_key=b.dataset.key;mobileReading=true;}
      if(action==='settings'||action==='resume_composer')mobileReading=true;
      if(action==='folder')data.folder=b.dataset.folder;
      if(b.dataset.section)data.section=b.dataset.section;
      if(b.dataset.attachment)data.attachment_id=b.dataset.attachment;
      if(b.dataset.operation)data.operation_id=b.dataset.operation;
      if(action==='save_preference')data.signature=$('preference').value;
      if(action==='save_settings'){
        data.settings={sender_name:$('sender-name').value,sent_policy:$('sent-policy').value,folder_mapping:{},signatures:{}};
        for(const r of ['sent','drafts','archive','junk','trash'])data.settings.folder_mapping[r]=$('map-'+r).value;
        for(const k of ['company','nathan','reina'])data.settings.signatures[k]={html:$('sig-'+k).innerHTML};
      }
      if(action==='workflow')Object.assign(data,{status:$('workflow-status').value,assigned:$('workflow-assigned').value,notes:$('workflow-notes').value,approval:$('workflow-approval').checked});
      emit(action,data);
    };
    root.querySelectorAll('[contenteditable=true]').forEach(e=>{
      if(e.dataset.wired)return;e.dataset.wired='true';
      e.addEventListener('paste',event=>{event.preventDefault();document.execCommand('insertText',false,event.clipboardData.getData('text/plain'));});
      e.addEventListener('drop',event=>event.preventDefault());
      e.addEventListener('keyup',()=>{const s=window.getSelection();if(s.rangeCount)selection=s.getRangeAt(0).cloneRange();});
      e.addEventListener('mouseup',()=>{const s=window.getSelection();if(s.rangeCount)selection=s.getRangeAt(0).cloneRange();});
    });
    root.querySelectorAll('[data-command]').forEach(b=>b.onmousedown=e=>e.preventDefault());
    if($('signature'))$('signature').onchange=()=>{$('signature-preview').innerHTML=signaturePreview($('signature').value);snapshot();};
    if($('attachment'))$('attachment').onchange=async()=>{const f=$('attachment').files[0];if(!f)return;if(f.size>10*1048576){$('notice').textContent='Attachment too large. Maximum file size is 10 MB.';return;}const reader=new FileReader();reader.onload=()=>emit('attach',{filename:f.name,base64:reader.result.split(',')[1]});reader.readAsDataURL(f);};
  }
  function targetFor(node){
    const folder=node.closest('[data-folder]');
    if(folder)return {kind:'folder',folder:folder.dataset.folder};
    const row=node.closest('[data-key]'),key=row?.dataset.key;
    const thread=model.threads.find(t=>t.key===key);
    if(thread)return {kind:'message',thread_key:thread.key,message_key:thread.message_key,
      unread:thread.message_unread,starred:thread.message_starred,folder:model.folder};
    const message=model.messages.find(m=>m.key===(key||model.active_message));
    return message?{kind:'message',message_key:message.key,unread:message.unread,starred:message.starred,folder:message.folder}:null;
  }
  function renderDeleteConfirmation(){
    const pending=model.delete_confirmation,existing=$('trash-delete-confirmation');
    if(existing?.dataset.token===pending?.token&&existing)return;
    existing?.remove();if(!pending)return;
    closeMenu();
    const dialog=document.createElement('dialog');dialog.id='trash-delete-confirmation';dialog.className='trash-delete-dialog';
    dialog.dataset.token=pending.token;dialog.setAttribute('aria-labelledby','trash-delete-title');
    dialog.innerHTML=`<h3 id="trash-delete-title">Delete permanently?</h3><p>“${esc(pending.subject)}” will be permanently deleted from Trash.</p><p class="muted">${pending.count>1?esc(pending.count)+' messages in this Trash conversation. ':''}This cannot be undone.</p><div class="row"><button type="button" data-delete="cancel">Cancel</button><button type="button" data-delete="confirm">Delete forever</button></div>`;
    let requested=false;
    const submit=action=>{if(requested||busy)return;requested=true;dialog.querySelectorAll('button').forEach(b=>b.disabled=true);emit(action,{token:pending.token});};
    dialog.onclick=e=>{const action=e.target.closest('[data-delete]')?.dataset.delete;if(action)submit(action==='confirm'?'confirm_delete_forever':'cancel_delete_forever');};
    dialog.oncancel=e=>{e.preventDefault();submit('cancel_delete_forever');};
    document.body.append(dialog);dialog.showModal();dialog.querySelector('[data-delete="cancel"]').focus();
  }
  function closeMenu(){menu?.remove();menu=null;menuTarget=null;if(pendingSignal)setTimeout(()=>signalTick(pendingSignal),0);}
  function showMenu(target,x,y,items=null,heading=''){
    closeMenu();if(!target||(busy&&!['resolve_thread','live_check'].includes(pendingAction)))return;
    menuTarget=target;menu=document.createElement('div');menu.className='mail-context';menu.setAttribute('role','menu');menu.setAttribute('aria-label',target.kind==='folder'?'Folder actions':'Message actions');
    const rows=items||(target.kind==='folder'?[['Refresh','refresh_folder'],['Search messages…','search_folder'],['Mark folder read','confirm_folder']]:messageMenuItems(target,model.roles,model.view==='mail'?model.folder:null));
    menu.innerHTML=(heading?'<p>'+esc(heading)+'</p>':'')+rows.map(([label,action,disabled,destination])=>`<button role="menuitem" type="button" data-menu-action="${esc(action)}" ${disabled?'disabled':''} ${destination?`data-destination="${esc(destination)}"`:''}>${esc(label)}</button>`).join('');
    document.body.append(menu);menu.style.left=Math.max(4,Math.min(x,window.innerWidth-menu.offsetWidth-4))+'px';menu.style.top=Math.max(4,Math.min(y,window.innerHeight-menu.offsetHeight-4))+'px';
    menu.onclick=e=>{
      const button=e.target.closest('[data-menu-action]');if(!button||button.disabled)return;
      const action=button.dataset.menuAction,target=menuTarget,rect=menu.getBoundingClientRect();
      if(action==='move'||action==='copy'){
        showMenu(target,rect.x,rect.y,model.folders.filter(f=>f.name!==target.folder).map(f=>[roleLabels[roleOf(f)]||f.label,action+'_to',false,f.name]),action==='move'?'Move to':'Copy to');return;
      }
      if(action==='confirm_folder'){showMenu(target,rect.x,rect.y,[['Cancel','cancel'],['Mark read','mark_folder_read']],`Mark all messages in ${target.folder} as read?`);return;}
      closeMenu();if(action==='cancel')return;
      if(action==='request_delete_forever'){emit(action,{thread_key:target.thread_key});return;}
      if(['reply','reply_all','forward'].includes(action)){
        if(model.draft&&!locked(model)&&!confirm('Replace this open compose session? Save a mailbox draft first if you want to keep it.'))return;
        localDraft=null;mobileReading=true;emit('compose',{mode:action,message_key:target.message_key});return;
      }
      if(action==='open'){emit(target.thread_key?'open_thread':'open_message',target);return;}
      if(action==='search_folder'){focusSearch=true;emit(action,{folder:target.folder});return;}
      if(action==='refresh_folder'||action==='mark_folder_read'){emit(action,{folder:target.folder,confirmed:action==='mark_folder_read'});return;}
      if(['trash','junk'].includes(action)&&!confirm(`Move this message to ${action==='trash'?'Trash':'Junk'}?`))return;
      emit(action.replace('_to',''),{message_key:target.message_key,destination:button.dataset.destination});
    };
    menu.querySelector('button:not(:disabled)')?.focus();
  }
  root.addEventListener('contextmenu',e=>{
    const target=e.target.closest('.conversation,.folder,.message-head');if(!target)return;
    e.preventDefault();showMenu(targetFor(target),e.clientX,e.clientY);
  });
  document.addEventListener('pointerdown',e=>{if(menu&&!menu.contains(e.target))closeMenu();});
  const parentMenuListeners=new AbortController();
  try{window.parent.document.addEventListener('pointerdown',closeMenu,{signal:parentMenuListeners.signal});}catch(_){}
  window.addEventListener('pagehide',()=>parentMenuListeners.abort());
  document.addEventListener('keydown',e=>{
    if(e.key==='Delete'&&!menu){const thread_key=trashDeleteTarget(model,e,busy);if(thread_key){e.preventDefault();emit('request_delete_forever',{thread_key});return;}}
    if(menu){
      if(e.key==='Escape'){e.preventDefault();e.stopPropagation();closeMenu();return;}
      if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const items=[...menu.querySelectorAll('button:not(:disabled)')];const at=items.indexOf(document.activeElement);items[(at+(e.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus();return;}
      if(e.key==='Enter'){e.preventDefault();document.activeElement?.click();return;}
    }
    const promptPopup=$('reply-prompts-popup');
    if(e.key==='Escape'&&promptPopup&&!promptPopup.hidden){
      e.preventDefault();e.stopPropagation();closeReplyPrompts();root.querySelector('[data-action="reply_prompts"]')?.focus();return;
    }
    if(promptPopup&&!promptPopup.hidden&&['ArrowDown','ArrowUp'].includes(e.key)){
      const items=[...promptPopup.querySelectorAll('button')];if(items.length){e.preventDefault();const at=items.indexOf(document.activeElement);items[(at+(e.key==='ArrowDown'?1:-1)+items.length)%items.length]?.focus();return;}
    }
    if(e.ctrlKey&&e.key==='Enter'&&model.view==='compose'){e.preventDefault();send();}
    if(e.key==='Escape'&&model.view==='compose'){e.preventDefault();emit('close_composer');}
    const typing=(e.composedPath?.()||[e.target]).some(node=>node?.isContentEditable||node?.closest?.('input,textarea,select,button,[contenteditable],[role="textbox"],[role="combobox"],[data-email-composer],.email-composer'));
    if(!typing&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&model.view==='mail'&&model.active_message){if(e.key.toLowerCase()==='r')compose('reply');if(e.key.toLowerCase()==='f')compose('forward');}
  });
  window.addEventListener('message',event=>{
    if(['sc:email-unread','sc:email-tick','sc:email-change'].includes(event.data?.type)){
      // The OS header runs in a sibling Streamlit srcdoc iframe, not the parent realm.
      let trusted=event.source===window.parent;
      try{trusted=trusted||[...window.parent.document.querySelectorAll('iframe')].some(f=>f.contentWindow===event.source&&f.dataset.scTopBar==='true');}catch(_){}
      if(!trusted)return;
      if(event.data.type==='sc:email-unread')inboxUnread(event.data);
      else if(event.data.type==='sc:email-change')signalTick(event.data.version);
      else liveTick();
      return;
    }
    if(event.source!==window.parent)return;
    if(event.data.type==='streamlit:render')render(event.data.args.model);
  });
  window.addEventListener('resize',fit);try{window.parent.addEventListener('resize',fit);new ResizeObserver(fit).observe(window.frameElement);}catch(_){}
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&pendingSignal)signalTick(pendingSignal);});
  window.addEventListener('pagehide',()=>clearTimeout(signalRetryTimer));
  post('streamlit:componentReady',{apiVersion:1});fit();
})();
