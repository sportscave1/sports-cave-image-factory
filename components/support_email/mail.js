(function () {
  'use strict';
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const size = n => Number(n) >= 1048576 ? (Number(n)/1048576).toFixed(1)+' MB' : Math.max(1, Math.round(Number(n)/1024))+' KB';
  const safeLink = value => {try {const u=new URL(value); return ['https:','http:','mailto:'].includes(u.protocol) && !u.username && !u.password ? u.href : '';} catch (_) {return '';}};
  const locked = m => Boolean((m.draft && ['accepted','unknown','in_progress'].includes((m.send_result || {}).status)) || m.draft_pending);
  const mailboxCount = m => m.error ? '' : (m.query ? 'Search · ' : '') + (m.threads || []).length + ' conversations';
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
    if(m.send_stage==='VALIDATING')return '<div>Validating email…</div>';
    if(status==='in_progress')return `<div>${m.send_result?.transport_status==='queued'?'Queued securely':'Submitting to mail server…'}</div>`;
    if(m.sent_view_pending&&!m.draft)return '<div>Opening sent email…</div>';
    if(m.send_stage==='CONFIRMING_SENT_COPY'&&(m.last_sent?.checks||0)>=3) return '<div class="send-uncertain">Email sent. Sent-copy confirmation is taking longer than expected.</div><small>Your message will not be sent again. Check the Sent copy to continue.</small>';
    if(['SAVING_SENT_COPY','CONFIRMING_SENT_COPY'].includes(m.send_stage)) return '<div class="send-success">Accepted by mail server — confirming Sent copy…</div>';
    if(m.send_stage==='VALIDATION_FAILED') return `<div class="send-failed">${esc(m.notice||'Email was not sent. Review the draft and try again.')}</div>`;
    if(status==='accepted') return '';
    if(status==='unknown') return (m.uncertain_checks||0)>=6
      ? '<div class="send-uncertain">Unable to confirm original send</div><small>Use Check Sent copy or ask the mailbox administrator to verify delivery. Do not resend.</small>'
      : '<div class="send-uncertain">Confirming original send…</div><small>Checking automatically. Do not resend.</small>';
    if(status==='rejected') return `<div class="send-failed">Email not sent. ${esc(m.send_result?.notice||'Check the details and try again.')}</div>`;
    return '';
  }
  function sendFeedback(m) {
    const content=sendStatus(m);
    if(!content)return '';
    const active=m.sent_view_pending||m.send_result?.status==='in_progress'||m.send_stage==='SAVING_SENT_COPY'||
      (m.send_stage==='CONFIRMING_SENT_COPY'&&(m.last_sent?.checks||0)<3)||
      (m.send_result?.status==='unknown'&&(m.uncertain_checks||0)<6);
    const check=m.send_result?.status==='unknown'&&(m.uncertain_checks||0)>=6;
    const copy=m.sent_result||{}, copyAction=m.send_stage==='CONFIRMING_SENT_COPY'&&(['failed','unknown'].includes(copy.status)||(m.last_sent?.checks||0)>=3)
      ? `<button type="button" data-action="${copy.retryable?'retry_sent_copy':'check_sent'}" data-operation="${esc(m.last_sent?.operation_id||'')}">${copy.retryable?'Retry saving Sent copy':'Check Sent copy'}</button>`:'';
    return content+copyAction+(check?'<button type="button" data-action="check_sent">Check Sent copy</button>':'')+
      (active?'<progress aria-label="Email delivery progress"></progress>':'');
  }
  function sentReceipt(m){
    const sent=m.last_sent;
    if(!sent?.operation_id)return '';
    const copy=sent.copy||{}, saved=['present','appended'].includes(copy.status);
    const preview=sent.html?`<details><summary>View sent message</summary><p>To: ${esc(sent.to)}</p><div class="message-body">${sent.html}</div></details>`:'';
    return `<div class="sent-receipt" role="status"><span class="send-success">✓ Sent</span> <span>${esc(sent.subject)}</span>${saved?'':`<span class="send-pending">Accepted by the mail server; ${copy.status==='pending'?'the Sent-folder copy is not visible yet.':'the Sent-folder copy could not be saved or verified.'} ${esc(copy.notice||'')}</span><button type="button" data-action="${copy.retryable?'retry_sent_copy':'check_sent'}" data-operation="${esc(sent.operation_id)}">${copy.retryable?'Retry saving Sent copy':'Check Sent copy'}</button>`}${sent.draft_warning?`<span>${esc(sent.draft_warning)}</span>`:''}${preview}${saved?`<button type="button" data-action="dismiss_receipt" data-operation="${esc(sent.operation_id)}">Dismiss</button>`:''}</div>`;
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
    const active=messages[0];
    if(!active?.expanded)return null;
    return {active_message:active.key,messages:messages.map(m=>m.key===active.key?{...m}:{...m,expanded:false,html:'',quote:'',reader_document:'',attachments:[],body_loading:false,body_error:''})};
  }
  function recoveryFeedback(m,active=false){
    const recovery=m.recovery||{};
    if(active)return '<span class="reconnect-spinner" aria-hidden="true"></span><span role="status">'+(m.read_pending?'Syncing…':'Reconnecting mailbox…')+'</span>';
    if(!recovery.state)return '';
    return `<span role="status">${esc(recovery.message)}</span>${recovery.state==='stopped'?'<button type="button" data-action="retry_connection" class="connection-retry">Retry</button>':''}`;
  }
  function receivedBody(message) {
    const allowed=message.images_allowed&&message.approved_reader_document;
    const control=message.blocked_images?`<div class="image-permission">${allowed?'Images shown for this message':`External images blocked · <button type="button" data-action="show_images" data-key="${esc(message.key)}" data-reader-identity="${esc(message.reader_identity)}" title="Loads images from the sender’s servers, which may reveal that you opened this email">Show Images</button>`}</div>`:'';
    return message.reader_document ? `<div class="received-content" data-reader-id="${esc(message.reader_identity)}">${control}<iframe class="email-document" title="Email content" sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox" referrerpolicy="no-referrer" srcdoc="${esc(allowed||message.reader_document)}"></iframe></div>` : `<div class="message-body">${message.html||''}</div>`;
  }
  function safeReaderView(messages){
    return messages.map(m=>({...m,images_allowed:false,approved_reader_document:''}));
  }
  function bindEmailFrame(frame){
    if(frame._emailBound)return;
    frame._emailBound=true;
    frame.onload=()=>{
      frame._emailObserver?.disconnect();
      try{
        const doc=frame.contentDocument,body=doc.querySelector('.sc-email-content')||doc.body;
        let scheduled=false;
        const resize=()=>{
          if(scheduled)return;scheduled=true;
          requestAnimationFrame(()=>{
            scheduled=false;if(!frame.isConnected)return;
            const height=Math.max(60,Math.ceil(Math.max(body.getBoundingClientRect().height,body.scrollHeight)));
            if(frame.style.height!==height+'px')frame.style.height=height+'px';
          });
        };
        const observer=new ResizeObserver(resize);observer.observe(body);frame._emailObserver=observer;
        doc.querySelectorAll('img').forEach(img=>{
          // An auto-sized frame has no independent viewport for lazy images.
          img.loading='eager';
          img.addEventListener('load',resize,{once:true});
          img.addEventListener('error',()=>{img.alt=img.alt||'Image unavailable';resize();},{once:true});
        });
        doc.fonts?.ready.then(resize);resize();
      }catch(_){frame.style.height='480px';}
    };
  }
  function readerStamp(m,ignoreFlags=false){
    const rows=ignoreFlags?(m.messages||[]).map(({unread,starred,...row})=>row):m.messages;
    return JSON.stringify([m.selected,m.view,m.active_message,rows,m.error,m.draft,m.send_result,m.send_stage,m.sent_result,m.draft_pending,m.context,m.settings,m.settings_available,m.signature_preference]);
  }
  function patchReadFlags(pane,active){
    if(!active)return;
    const read=pane.querySelector('.reading-toolbar [data-action="mark_read"],.reading-toolbar [data-action="mark_unread"]');
    if(read){read.dataset.action=active.unread?'mark_read':'mark_unread';read.textContent=active.unread?'Mark read':'Mark unread';read.disabled=false;}
    const flag=pane.querySelector('.reading-toolbar [data-action="star"],.reading-toolbar [data-action="unstar"]');
    if(flag){flag.dataset.action=active.starred?'unstar':'star';flag.textContent=active.starred?'★':'☆';flag.disabled=false;}
  }
  function searchKnownRows(rows, query){
    const match=String(query).trim().match(/^(from|to|subject|text):\s*(.*)$/i);
    const field=match?match[1].toLowerCase():'text', term=(match?match[2]:query).trim().toLowerCase();
    return rows.filter(row=>{
      const values=field==='from'?[row.email,row.customer]:field==='to'?[row.recipients]:
        field==='subject'?[row.subject]:[row.email,row.customer,row.recipients,row.subject,row.snippet];
      return values.some(value=>String(value||'').toLowerCase().includes(term));
    });
  }
  function patchImagePermission(pane,messages){
    for(const row of messages){
      if(!row.images_allowed||!row.approved_reader_document)continue;
      const wrap=[...pane.querySelectorAll('.received-content')].find(n=>n.dataset.readerId===row.reader_identity);
      const frame=wrap?.querySelector('.email-document');if(!frame)continue;
      frame._emailObserver?.disconnect();frame.srcdoc=row.approved_reader_document;
      const article=wrap.closest?.('[data-message-key]');if(article)article._emailRow=JSON.stringify(row);
      const control=wrap.querySelector('.image-permission');if(control)control.textContent='Images shown for this message';
    }
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
  function componentHandshake(post,schedule=setTimeout,cancel=clearTimeout){
    let attempts=0,stopped=false,timer=null;
    function announce(){
      if(stopped)return;
      post('streamlit:componentReady',{apiVersion:1});
      if(!stopped&&++attempts<20)timer=schedule(announce,500);
    }
    announce();
    return ()=>{stopped=true;if(timer!==null)cancel(timer);};
  }
  if (typeof module !== 'undefined') {module.exports={componentHandshake,bindEmailFrame,readerStamp,patchReadFlags,searchKnownRows,safeReaderView,patchImagePermission,receivedBody,replyPromptControls,copyReplyPrompt,esc,size,safeLink,locked,mailboxCount,messageMenuItems,trashDeleteTarget,sendStatus,sendFeedback,sentReceipt,createViewCache,threadView,recoveryFeedback}; return;}
  const root=document.getElementById('mail');
  let model={}, busy=false, pending='', collapsed=false, mobileReading=false, localDraft=null, downloaded='', selection=null;
  let pendingAction='', queued=null, historyTimer=null, lastHeight=0, readingStamp='', listStamp='', folderStamp='', toolbarStamp='';
  let selectionControlsDisabled=false;
  let completionRequest=null;
  let searchTimer=null, searchText=null, searchFolder='';
  let journal=null,journalScope='',journalError='',recoveryDrafts=[],editRevision=0;
  function persistEdits(){
    const draft=snapshot();if(!draft||locked(model))return;
    if(model.draft_save_status==='Saved'&&editRevision<=Number(model.draft_saved_revision??-1))return;
    try{journal?.write(draft);journalError='';}catch(_){journalError='Recovery storage unavailable. Save or copy your text before leaving.';}
  }
  function saveLabel(){
    if(journalError)return journalError;
    if(['Conflict','Failed'].includes(model.draft_save_status))return model.draft_save_status+' — edits retained';
    if(editRevision>Number(model.draft_saved_revision??-1))return pendingAction==='autosave_draft'?'Saving…':'Unsaved';
    return model.draft_save_status||'';
  }
  let replyPromptFeedbackTimer=null;
  const views=createViewCache();
  const folderViews=createViewCache(10,2*1024*1024);
  const folderKey=(m,folder)=>JSON.stringify([m.reader_scope,m.mailbox,folder]);
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
  let autosaveTimer=null;
  function scheduleAutosave(){
    if(!model.durable_drafts||!model.draft||locked(model))return;
    clearTimeout(autosaveTimer);
    editRevision++;persistEdits();
    if($('draft-save-status'))$('draft-save-status').textContent='Unsaved';
    const save=()=>{if(busy){autosaveTimer=setTimeout(save,300);return;}autosaveTimer=null;emit('autosave_draft');};
    autosaveTimer=setTimeout(save,700);
  }
  root.addEventListener('input',e=>{if(e.target.closest('[data-email-compose],.compose')||e.target.id==='editor'||e.target.id?.startsWith('draft-'))scheduleAutosave();});
  root.addEventListener('change',e=>{if(['signature','include-quote'].includes(e.target.id))scheduleAutosave();});
  window.addEventListener('pagehide',()=>{persistEdits();clearTimeout(autosaveTimer);});
  document.addEventListener('visibilitychange',()=>{if(document.hidden)persistEdits();});
  window.addEventListener('beforeunload',e=>{if(model.draft&&!locked(model)&&editRevision>Number(model.draft_saved_revision??-1)){e.preventDefault();e.returnValue='';}});
  let sentTimer=null;
  function scheduleSentCheck(){
    clearTimeout(sentTimer);
    if(model.send_result?.status==='unknown'&&(model.uncertain_checks||0)<6&&!busy){sentTimer=setTimeout(()=>emit('auto_check_sent'),10000);return;}
    const sent=model.last_sent;
    if(!sent?.operation_id||!['pending','unknown','failed','attempting'].includes(sent.copy?.status)||sent.checks>=3||busy)return;
    sentTimer=setTimeout(()=>emit('auto_check_sent',{operation_id:sent.operation_id}),[6000,12000,24000][sent.checks||0]);
  }
  window.addEventListener('pagehide',()=>clearTimeout(sentTimer));
  let sendTimer=null;
  function scheduleSendStage(){
    clearTimeout(sendTimer);
    if(busy||!model.send_result?.operation_id||!['SENDING','SAVING_SENT_COPY'].includes(model.send_stage))return;
    const operation_id=model.send_result.operation_id;
    // Only continue the operation created by an explicit Send click, after painting its real stage.
    sendTimer=setTimeout(()=>emit('advance_send',{operation_id}),Math.max(100,model.send_result.retry_delay_ms||100));
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
  let stopReady=()=>{};
  const $=id=>document.getElementById(id);
  const button=(label,action,data='',disabled=false,klass='')=>`<button type="button" class="${klass}" data-action="${action}" ${data} ${disabled?'disabled':''}>${label}</button>`;
  function snapshot() {
    if (!$('editor') || !model.draft || locked(model)) return localDraft;
    localDraft={id:model.draft.id,html:$('editor').innerHTML,signature:$('signature').value,include_quote:!!$('include-quote')?.checked,
      edit_revision:editRevision,storage_version:model.draft.storage_version,attachment_ids:(model.draft.attachments||[]).map(a=>a.id)};
    for (const key of ['to','cc','bcc','subject']) localDraft[key]=$('draft-'+key).value;
    return localDraft;
  }
  function emit(action, values={}) {
    const selecting=['open_thread','open_message'].includes(action);
    if (busy) {
      if(selecting || ['folder','search','compose','settings','close_composer','resume_composer','context'].includes(action) || ['open_thread','open_message','resolve_thread','load_visible_body','load_conversation_body','load_initial_mailbox','sync_index','auto_check_sent','autosave_draft','live_check','load_mail_metadata','mark_visible_read','contact_search'].includes(pendingAction)){
        queued={action,values};
        if(selecting) optimistic(action,values);
      }
      return;
    }
    const draft=snapshot();
    if(['refresh','mark_read','mark_unread','star','unstar','archive','move','copy','trash','junk','confirm_delete_forever','mark_folder_read','bulk_action','restore'].includes(action))folderViews.clear();
    if(action==='folder'){
      const cached=folderViews.get(folderKey(model,values.folder));
      const usable=cached&&Date.now()-cached.at<20000;
      const pane=root.querySelector('.listpane');
      if(pane)pane.outerHTML=conversations({...model,...(usable?cached.value:{}),folder:values.folder,query:'',selected:null,
        threads:usable?cached.value.threads:[],local_drafts:[],error:'',initial_load_pending:!usable});
      const footer=root.querySelector('.list-footer');if(footer)footer.textContent=usable?'Cached folder · refreshing…':'Loading folder…';
      mobileReading=false;root.querySelector('.workspace')?.classList.remove('show-reading');listStamp='';
    }
    persistEdits();
    if(action==='autosave_draft'&&$('draft-save-status'))$('draft-save-status').textContent='Saving…';
    if(action==='send'){model.send_result={status:'in_progress'};model.sent_result={};model.send_stage='VALIDATING';if($('send-status'))$('send-status').innerHTML=sendFeedback(model);}
    clearTimeout(historyTimer);
    completionRequest?.abort();completionRequest=null;
    pending=crypto.randomUUID(); busy=true; pendingAction=action;
    if(['mark_read','mark_unread','star','unstar','archive','move','copy','trash','junk','show_images'].includes(action)){
      root.querySelectorAll(`[data-action="${action}"]`).forEach(b=>{b.disabled=true;b.setAttribute('aria-busy','true');});
    }
    if(selecting) optimistic(action,values);
    else if(['send','discard_draft','attach','remove_attachment','forward_attachment','save_draft'].includes(action)){root.classList.add('busy');freeze();}
    if (!selecting && !['resolve_thread','load_visible_body','load_conversation_body','load_initial_mailbox','sync_index','auto_check_sent','autosave_draft','live_check','load_mail_metadata','mark_visible_read'].includes(action) && $('notice')) $('notice').textContent=action==='send'?'Sending…':action==='download'?'Downloading attachment…':action==='refresh'?'Refreshing…':'Working…';
    if(['reconnect','retry_connection'].includes(action)&&$('notice'))$('notice').innerHTML=recoveryFeedback(model,true);
    post('streamlit:setComponentValue',{value:{id:pending,action,...values,draft},dataType:'json'});
  }
  function waitForBody(message_key){
    const completion=model.body_completion, scope=model.reader_scope;
    if(!completion){emit('load_visible_body',{message_key});return;}
    const controller=new AbortController();completionRequest=controller;
    const current=()=>model.reader_scope===scope&&model.active_message===message_key&&model.body_pending===message_key&&model.view==='mail'&&model.body_completion?.ticket===completion.ticket;
    const wait=async()=>{
      try{
        const response=await fetch('/api/os/email/read-ready',{headers:{Authorization:'Bearer '+completion.token,'X-Email-Read':completion.ticket},cache:'no-store',signal:controller.signal});
        if(!current()||controller.signal.aborted)return;
        if(response.ok&&!(await response.json()).ready){await wait();return;}
        // Standalone embeds without the route use the same bounded component
        // request. No email content passes through the readiness endpoint.
        if(!busy)emit('load_visible_body',{message_key});
      }catch(error){if(error.name!=='AbortError'&&current()&&!busy)emit('load_visible_body',{message_key});}
    };
    wait();
  }
  const viewKey=(m,key)=>JSON.stringify([m.reader_scope,m.mailbox,m.mailbox_version,key]);
  function markSelection(){
    root.querySelectorAll('.conversation').forEach(e=>{const active=e.dataset.key===model.selected;e.classList.toggle('selected',active);e.setAttribute('aria-selected',String(active));});
  }
  function optimistic(action,values){
    snapshot();mobileReading=true;
    if(model.view==='mail'&&model.selected){
      const oldKey=viewKey(model,model.selected),oldView=views.get(oldKey);
      if(oldView)views.put(oldKey,{...oldView,scrollTop:root.querySelector('.reading-scroll')?.scrollTop||0});
    }
    if(action==='open_thread'){
      const hit=views.get(viewKey(model,values.thread_key));
      model={...model,view:'mail',selected:values.thread_key,messages:hit?.messages||[],active_message:hit?.active_message};
      if(hit){
        paintReading(true,true);
        const scroll=root.querySelector('.reading-scroll');if(scroll)scroll.scrollTop=hit.scrollTop||0;
      }
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
  function conversations(view) {
    const current=view||model;
    const folder=(current.folders||[]).find(f=>f.name===current.folder);
    return `<section class="listpane" aria-label="Conversations"><div class="list-heading row spread"><strong>${esc(current.filters?.scope==='all'?'All folders':roleLabels[roleOf(folder||{})]||folder?.label||'Mailbox')}</strong><small>${esc(mailboxCount(current))}</small></div><div class="conversations">${(current.local_drafts||[]).map(d=>`<button class="conversation" data-action="open_local_draft" data-draft="${esc(d.draft_id)}"><div class="subject ellipsis">${esc(d.subject||"(No subject)")}</div><div class="preview ellipsis">Saved draft · ${esc(d.recipients)}</div></button>`).join('')}${current.error?`<div class="empty">Waiting for mailbox data…</div>`:(current.threads||[]).map(t=>`<div class="conversation-wrap"><button class="conversation ${t.unread?'unread':''} ${current.selected===t.key?'selected':''}" data-action="open_thread" data-key="${esc(t.key)}" aria-label="${esc(t.customer+' · '+t.subject)}"><div class="row spread"><span class="sender ellipsis">${esc(t.customer||t.email||'Unknown sender')}</span><time>${esc(t.time)}</time></div><div class="subject ellipsis">${esc(t.subject)}</div><div class="row spread"><span class="preview ellipsis grow">${esc(t.snippet||'Open conversation')}</span><small>${current.filters?.scope==='all'?esc(t.folder)+' · ':''}${t.attachment?'⌁ ':''}${t.starred?'★ ':''}${t.count>1?t.count:''}</small></div></button><button class="row-more" data-action="message_menu" data-key="${esc(t.key)}" aria-label="More actions for ${esc(t.subject)}">⋯</button></div>`).join('')||`<div class="empty">${(current.initial_load_pending||current.read_pending)?'Loading conversations…':'No messages in this view.'}</div>`}</div><div class="list-footer">${current.has_more&&!current.error?button('Load 50 more','load_more'): '<span class="muted">'+(current.error?'':current.live_error?'Cached mailbox · last successful view':current.query?(current.read_pending?'Searching current folder…':'Live search · current folder'):'Live mailbox · latest messages')+'</span>'}</div></section>`;
  }
  const names=people=>(people||[]).map(p=>p.name?`${p.name} <${p.email}>`:p.email).join(', ');
  function messages() {
    const rows=model.messages||[], active=rows.find(m=>m.key===model.active_message)||rows[rows.length-1];
    const selectedThread=(model.threads||[]).find(t=>t.key===model.selected);
    if (!active) return `<div class="reading-toolbar">${button('Back to list','back','','','mobile-back')}</div><div class="reading-scroll empty">${'Select a conversation to read it.'}${model.draft?'<p class="attachments">'+button('Resume draft','resume_composer')+'</p>':''}</div>`;
    return `<div class="reading-toolbar">${button('←','back','','','mobile-back')}${button('Reply','compose','data-mode="reply"')}${button('Reply all','compose','data-mode="reply_all"')}${button('Forward','compose','data-mode="forward"')}<span class="grow"></span>${button('Archive','archive','',!model.roles.archive)}${button('Trash','trash','',!model.roles.trash)}${button(active.unread?'Mark read':'Mark unread',active.unread?'mark_read':'mark_unread')}${button(active.starred?'★':'☆',active.starred?'unstar':'star','title="Flag / unflag" aria-label="Flag / unflag"')}${button('Junk','junk','',!model.roles.junk)}${button('⋯','message_menu','title="More message actions" aria-label="More message actions"')}</div><div class="reading-scroll"><div class="subject-header"><div class="row spread"><h2>${esc(active.subject)}</h2>${button('Customer / Order','context','','','plain')}</div><div class="customer">${esc(selectedThread?.customer||active.sender.name||active.sender.email)}</div><small>${esc(selectedThread?.email||active.sender.email)}</small><div class="meta">Actions apply to the selected message · ${esc(active.folder)} · ${esc(active.time)}</div>${active.draft?'<div class="attachments">'+button('Edit mailbox draft','edit_draft')+'</div>':''}${model.draft?'<div class="attachments">'+button('Resume draft','resume_composer')+'</div>':''}</div><div class="messages">${rows.map(m=>`<article data-message-key="${esc(m.key)}" class="message ${m.key===active.key?'active':''}"><button class="message-head" data-action="open_message" data-key="${esc(m.key)}" aria-expanded="${m.expanded}" aria-label="${m.expanded?'Select':'Expand'} message from ${esc(m.sender.name||m.sender.email)}"><div class="row spread"><span class="label">${m.own?'Sports Cave':'Customer'} ${m.expanded?'':'· expand'}</span><small>${esc(m.time)}</small></div><div class="person">${esc(m.sender.name||m.sender.email)}</div><div class="meta">${esc(m.sender.email)}${m.reply_to?.length&&names(m.reply_to)!==names([m.sender])?'<br>Reply-To: '+esc(names(m.reply_to)):''}${m.expanded?'<br>To: '+esc(names(m.to))+(m.cc.length?' · CC: '+esc(names(m.cc)):''):''}</div>${!m.expanded&&m.preview?'<div class="preview ellipsis">'+esc(m.preview)+'</div>':''}</button>${m.expanded?`${button('Collapse message','collapse_message',`data-key="${esc(m.key)}"`)}${receivedBody(m)}${m.quote&&!m.reader_document?`<div class="quote">${m.quote}</div>`:''}${(m.warnings||[]).map(w=>'<p class="muted">'+esc(w)+'</p>').join('')}<div class="attachments">${m.attachments.map(a=>button('⌁ '+esc(a.filename)+' · '+size(a.encoded_size)+' ↓','download',`data-key="${esc(m.key)}" data-section="${esc(a.section)}" title="${esc(a.content_type)} · Download directly from mailbox"`)).join('')}</div>`:m.body_loading?'<div class="message-loading" role="status">Loading message…</div>':m.body_error?`<div class="message-error" role="status">${esc(m.body_error)} ${button('Retry','open_message',`data-key="${esc(m.key)}"`)}</div>`:'' }</article>`).join('')}</div></div>`;
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
    return `<section class="panel" aria-label="Compose mail"><div class="panel-head"><div class="reply-heading"><strong>${{new:'New mail',reply:'Reply',reply_all:'Reply all',forward:'Forward'}[draft.mode]||'Draft'}</strong>${replyPromptControls(draft.mode)}<small id="draft-save-status" role="status">${esc(model.draft_save_status||'')}</small></div>${button('Close · Esc','close_composer','','','plain')}</div><div class="compose-main">${model.draft_source_unavailable?'<p class="muted">Original conversation unavailable. Saved recipients and quoted content are preserved.</p>':''}${['Conflict','Failed'].includes(model.draft_save_status)?'<div class="attachments">'+button('Recover as separate draft','recover_current_copy')+button('Download unsaved text','export_draft_text')+'</div>':''}<div class="compose-fields"><div class="compose-field"><label>From</label><span>${esc(model.settings.sender_name)} &lt;${esc(model.mailbox)}&gt;</span></div>${['to','cc','bcc','subject'].map(key=>`<div class="compose-field"><label for="draft-${key}">${key==='subject'?'Subject':key.toUpperCase()}</label><input id="draft-${key}" value="${esc(draft[key])}" ${lock?'disabled':''} autocomplete="off" maxlength="${key==='subject'?998:4000}" placeholder="${key==='to'?'name@example.com':''}"></div>`).join('')}</div>${formatBar()}<div class="compose-scroll"><div id="editor" class="editor" contenteditable="${!lock}" role="textbox" aria-label="Message body" aria-multiline="true">${draft.html}</div><div id="signature-preview" class="signature-preview" contenteditable="false" role="group" aria-label="Signature preview">${signaturePreview(draft.signature)}</div>${draft.quote_html?`<details><summary>Previous message</summary><label class="checkbox"><input id="include-quote" type="checkbox" ${draft.include_quote?'checked':''} ${lock?'disabled':''}>Include quoted message</label><div class="quote">${draft.quote_html}</div>${forwarded.length?'<p class="muted">Include original attachments:</p><div class="attachments">'+forwarded.map(a=>button('＋ '+esc(a.filename),'forward_attachment',`data-key="${esc(a.message_key)}" data-section="${esc(a.section)}"`,lock)).join('')+'</div>':''}</details>`:''}<div class="attachments">${draft.attachments.map(a=>`<span class="pill">⌁ ${esc(a.filename)} <small>${size(a.size)}</small>${button('×','remove_attachment',`data-attachment="${esc(a.id)}" title="Remove attachment"`,lock)}</span>`).join('')}</div></div></div><div class="compose-bottom"><div class="row wrap">${status==='accepted'?button('Close','close_composer','','','primary'):button('Send','send','title="Ctrl+Enter"',lock||!model.smtp_configured||!model.settings_available,'primary')}${button('Attach file','choose_file','',lock)}<input id="attachment" class="hidden-file" type="file" ${lock?'disabled':''}>${button('Save draft','save_draft','',!model.roles.drafts||['accepted','unknown','in_progress'].includes(status))}<span class="grow"></span><select id="signature" aria-label="Signature" ${lock?'disabled':''}>${signaturesOptions(draft.signature)}</select>${button('Discard','discard_draft','',lock,'plain')}</div>${!model.smtp_configured?'<small>SMTP needs configuration before sending.</small>':'<small>10 MB per file · 14 MB attachments total · 20 MB encoded message</small>'}${model.draft_pending?'<p class="muted">Draft save is pending. Save draft checks for its existing copy.</p>':''}</div></section>`;
  }
  function settings() {
    const s=model.settings;
    const previews=Object.entries(s.signatures).map(([key,sig])=>`<div><label>${esc(sig.label)} <small>Preview</small></label>${model.admin?formatBar('sig-'+key):''}<div id="sig-${key}" class="signature-edit" contenteditable="${model.admin}" role="${model.admin?'textbox':'group'}" aria-label="${esc(sig.label)} signature">${signaturePreview(key)}</div></div>`).join('');
    const mailbox=model.admin?`<div class="section stack"><div class="label">Mailbox settings</div><label>Sender display name<input id="sender-name" value="${esc(s.sender_name)}" maxlength="120"></label><div class="mapping">${['sent','drafts','archive','junk','trash'].map(role=>`<label for="map-${role}">${roleLabels[role]}</label><select id="map-${role}"><option value="">Use special-use discovery</option>${model.folders.filter(f=>f.name.toUpperCase()!=='INBOX').map(f=>`<option value="${esc(f.name)}" ${s.folder_mapping[role]===f.name?'selected':''}>${esc(f.label)}</option>`).join('')}</select>`).join('')}</div><label>Sent copy handling<select id="sent-policy">${[['verify','Automatic · find or save Sent copy'],['server','Server saves Sent · confirmed'],['append','App saves Sent copy']].map(([v,l])=>`<option value="${v}" ${s.sent_policy===v?'selected':''}>${l}</option>`).join('')}</select></label><small>Automatic checks the real Sent folder by Message-ID before saving a missing copy. Use server saving only when confirmed for this mailbox.</small></div>`:'';
    return `<section class="panel"><div class="panel-head"><strong>Email settings</strong>${button('Close','close_panel','','','plain')}</div><div class="panel-scroll stack"><div><div class="label">Connection</div><p>${esc(model.mailbox)}</p><small>IMAP ${model.configured?'configured':'not configured'} · SMTP ${model.smtp_configured?'configured':'not configured'}</small></div>${button('Test IMAP connection','test_connection','',!model.configured)}<label>Your default signature<select id="preference">${signaturesOptions(model.signature_preference)}</select></label>${button('Save my preference','save_preference','',!model.settings_available)}${!model.settings_available?'<small>Settings storage is unavailable. Defaults remain usable.</small>':''}${model.can_diagnose?button('Mailbox diagnostics','mail_diagnostics'):''}${model.admin_diagnostics?'<pre>'+esc(JSON.stringify({inbound:model.sync_health,outbound:model.admin_diagnostics},null,2))+'</pre>':''}${mailbox}<div class="section stack"><div class="label">Signatures</div>${previews}${model.admin?button('Save mailbox settings','save_settings','',!model.settings_available,'primary'):''}</div></div></section>`;
  }
  function external(label,url){url=safeLink(url); return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:'';}
  function appURL(query) {try{return window.parent.location.href.split('?')[0].split('#')[0]+query;}catch(_){return '';}}
  function contextPanel(){
    const c=model.context||{},o=c.order,w=c.workflow||{};
    return `<section class="panel"><div class="panel-head"><strong>Customer / Order</strong>${button('Close','close_panel','','','plain')}</div><div class="panel-scroll"><h3>${esc(c.label||'No order matched')}</h3>${(c.candidates||[]).map(v=>'<p class="context-item">'+esc(v.name)+' · '+esc(v.date)+'</p>').join('')}${o?`<div class="context-item"><strong>${esc(o.name)}</strong><br>${esc(o.date)}<br>Fulfilment: ${esc(o.fulfilment)}</div>${o.lines.map(l=>`<div class="context-item">${esc(l.product_title)}<br><small>${esc(l.variant_title)}</small></div>`).join('')}${o.editions.map(e=>`<div class="context-item">Edition ${esc(e.edition_number)} / ${esc(e.edition_total)}<br>Certificate: ${esc(e.certificate_status||'Not recorded')}<br>${external('Open Edition',appURL(o.edition_url))}</div>`).join('')}<div class="section stack">${external('Open Shopify order',o.shopify_url)}${external('Open Sports Cave order',appURL(o.os_url))}${o.tracking.map(u=>external('Open tracking',u)).join('')}</div>${o.previous.length?'<div class="section"><div class="label">Previous orders</div>'+o.previous.map(p=>'<p class="context-item">'+esc(p.name)+' · '+esc(p.date)+'</p>').join('')+'</div>':''}`:''}<div class="section stack"><div class="label">Internal support workflow</div>${c.workflow_available&&!w.conflict?`<label>Status<select id="workflow-status">${['Needs Reply','Waiting on Customer','Waiting on Sports Cave','Resolved'].map(s=>`<option ${w.support_status===s?'selected':''}>${s}</option>`).join('')}</select></label><label>Assigned<select id="workflow-assigned"><option value="">Unassigned</option>${c.assignees.map(a=>`<option value="${esc(a.id)}" ${w.assigned_user_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select></label><label>Internal notes<textarea id="workflow-notes" maxlength="8000">${esc(w.internal_notes||'')}</textarea></label><label class="checkbox"><input id="workflow-approval" type="checkbox" ${w.needs_approval?'checked':''}>Requires Nathan's approval</label><small>Internal only. Notes are never included in email.</small>${button('Save workflow','workflow')}`:'<small>Workflow metadata is unavailable or conflicting. Mail remains in the live mailbox.</small>'}</div></div></section>`;
  }
  function paintReading(force=false,reset=false){
    const stamp=readerStamp(model);
    const pane=root.querySelector('.reading');if(!pane)return;
    if(force||stamp!==readingStamp){
      const scrollSelector=window.matchMedia?.('(max-width:540px) and (max-height:650px)')?.matches?'.reading-scroll,.compose-main,.panel-scroll':'.reading-scroll,.compose-scroll,.panel-scroll';
      const old=pane.querySelector(scrollSelector);const top=reset?0:old?.scrollTop||0;
      const retained=new Map([...pane.querySelectorAll('[data-message-key]')].map(node=>[node.dataset.messageKey,node]));
      const anchor=old&&[...retained.values()].find(node=>node.getBoundingClientRect().bottom>old.getBoundingClientRect().top);
      const offset=anchor?.getBoundingClientRect().top;
      const html=model.view==='compose'?composer():model.view==='settings'?settings():model.view==='context'?contextPanel():messages();
      const rows=new Map((model.messages||[]).map(row=>[row.key,JSON.stringify(row)]));
      if(model.view==='mail'&&model.selected&&pane._emailThread===model.selected&&pane.querySelector('.messages')){
        const template=document.createElement('div');template.innerHTML=html;
        for(const selector of ['.reading-toolbar','.subject-header']){
          const next=template.querySelector(selector),current=pane.querySelector(selector);
          if(next&&current)current.replaceWith(next);
        }
        const target=pane.querySelector('.messages');let cursor=target.firstElementChild;
        template.querySelectorAll('[data-message-key]').forEach(node=>{
          const previous=retained.get(node.dataset.messageKey),row=rows.get(node.dataset.messageKey);
          if(previous&&previous._emailRow===row){
            // Optimistic selection disables cached controls until its acknowledgement.
            if(!busy&&!locked(model))previous.querySelectorAll('button').forEach(button=>button.disabled=false);
            previous.classList.toggle('active',node.dataset.messageKey===model.active_message);
            if(previous!==cursor)target.insertBefore(previous,cursor);
            cursor=previous.nextElementSibling;retained.delete(node.dataset.messageKey);
          }else{
            node._emailRow=row;
            if(previous){
              previous.querySelectorAll('.email-document').forEach(frame=>frame._emailObserver?.disconnect());
              if(previous===cursor)cursor=previous.nextElementSibling;
              previous.replaceWith(node);retained.delete(node.dataset.messageKey);
            }else target.insertBefore(node,cursor);
          }
        });
        for(const node of retained.values()){
          node.querySelectorAll('.email-document').forEach(frame=>frame._emailObserver?.disconnect());node.remove();
        }
      }else{
        pane.querySelectorAll('.email-document').forEach(frame=>frame._emailObserver?.disconnect());
        pane.innerHTML=html;
        pane.querySelectorAll('[data-message-key]').forEach(node=>node._emailRow=rows.get(node.dataset.messageKey));
      }
      pane._emailThread=model.view==='mail'?model.selected:null;
      const scroll=pane.querySelector(scrollSelector);if(scroll){
        scroll.scrollTop=top;
        const nextAnchor=anchor&&[...pane.querySelectorAll('[data-message-key]')].find(node=>node.dataset.messageKey===anchor.dataset.messageKey);
        if(!reset&&nextAnchor&&offset!==undefined)scroll.scrollTop+=nextAnchor.getBoundingClientRect().top-offset;
      }
      pane.querySelectorAll('.email-document').forEach(bindEmailFrame);
      readingStamp=stamp;
      selectionControlsDisabled=false;
    }
  }
  function render(next) {
    if(model.reader_scope&&model.reader_scope!==next.reader_scope){
      views.clear();pending='';busy=false;queued=null;readingStamp='';
    }
    // The fragment first receives the old model before processing its event. Ignore that echo.
    if(pending&&next.ack!==pending)return;
    const flagsOnly=Boolean(readingStamp)&&readerStamp(model)!==readerStamp(next)&&model.view==='mail'&&next.view==='mail'&&model.reader_scope===next.reader_scope&&readerStamp(model,true)===readerStamp(next,true);
    const imageOnly=pendingAction==='show_images'&&model.view==='mail'&&next.view==='mail'&&
      model.reader_scope===next.reader_scope&&model.selected===next.selected&&model.error===next.error&&
      JSON.stringify(safeReaderView(model.messages||[]))===JSON.stringify(safeReaderView(next.messages||[]));
    if(next.draft_scope&&next.draft_scope!==journalScope){
      try{journal=window.EmailDraftJournal.create(window.parent.sessionStorage,next.draft_scope);journalScope=next.draft_scope;recoveryDrafts=journal.list();}
      catch(_){journalError='Recovery storage unavailable. Save or copy your text before leaving.';}
    }
    if(model.draft&&(next.send_result?.status==='accepted'||(pendingAction==='discard_draft'&&!next.draft))){
      try{journal?.remove(model.draft.id);}catch(_){}
    }
    if(next.draft?.id!==model.draft?.id)editRevision=Number(next.draft?.edit_revision||0);
    if(next.draft&&next.draft_save_status==='Saved'){
      try{journal?.acknowledge(next.draft.id,next.draft_saved_revision);recoveryDrafts=journal?.list()||[];}catch(_){}
      if(pendingAction==='recover_draft_copy'&&next.draft.recovered_from){try{journal?.remove(next.draft.recovered_from);recoveryDrafts=journal?.list()||[];}catch(_){}}
    }
    const liveUpdate=['live_check','reconnect','sync_index','auto_check_sent','autosave_draft','load_mail_metadata','mark_visible_read','contact_search'].includes(pendingAction);
    const focused=document.activeElement;
    const focusOwner=focused&&(!pendingAction||liveUpdate)&&model.reader_scope===next.reader_scope&&model.folder===next.folder&&root.contains(focused)?{
      node:focused,id:focused.id,action:focused.dataset.action,key:focused.dataset.key,folder:focused.dataset.folder,mode:focused.dataset.mode,pane:focused.dataset.pane,
      checkbox:focused.classList.contains('mail-select'),thread:focused.closest('.conversation-wrap')?.querySelector('.conversation')?.dataset.key
    }:null;
    snapshot(); // Keep edits/caret made while any nonblocking request was in flight.
    if(pendingAction==='search')listStamp=''; // A repeated query must restore provider matches hidden by the local preview.
    const oldFolder=model.folder, oldQuery=model.query;
    if(next.folder!==model.folder||next.reader_scope!==model.reader_scope){clearTimeout(searchTimer);searchText=null;}
    const wasFrozen=busy&&['send','discard_draft','attach','remove_attachment','forward_attachment','save_draft'].includes(pendingAction);
    const selectionChanged=next.selected!==model.selected;
    if(next.mailbox_version!==model.mailbox_version||next.mailbox!==model.mailbox||next.error)views.clear();
    if (next.draft?.id!==model.draft?.id || next.send_result?.status==='accepted') localDraft=null;
    if(next.reader_scope!==model.reader_scope||next.error||(['live_check','sync_index'].includes(pendingAction)&&next.mailbox_version!==model.mailbox_version))folderViews.clear();
    model=next;
    if(model.folder&&!model.query&&!Object.keys(model.filters||{}).length&&!model.error&&!model.initial_load_pending&&!model.read_pending){
      folderViews.put(folderKey(model,model.folder),{at:Date.now(),value:{threads:model.threads,has_more:model.has_more,limit:model.limit}});
    }

    try {
      window.parent.SportsCaveTopBar?.mailboxUnreadChanged?.(model.inbox_status||{});
      inboxUnread(window.parent.SportsCaveTopBar?.emailUnreadStatus?.());
    } catch (_) {}
    if (model.ack===pending) {
      busy=false;pending='';pendingAction='';
      if (model.draft && !model.send_result?.status) submitted.delete(model.draft.operation_id);
    }
    if (model.draft && !localDraft) localDraft=Object.fromEntries(['id','to','cc','bcc','subject','html','signature','include_quote','edit_revision','storage_version'].map(k=>[k,model.draft[k]]));
    if (model.draft && localDraft) localDraft.operation_id=model.draft.operation_id;
    if(model.view==='mail'&&!model.error&&model.selected){
      const cached=threadView(safeReaderView(model.messages),model.folder);
      views.put(viewKey(model,model.selected),cached?{...cached,scrollTop:root.querySelector('.reading-scroll')?.scrollTop||0}:cached);
    }
    if(queued){const action=queued;queued=null;emit(action.action,action.values);return;}
    root.classList.remove('busy');
    scheduleSentCheck();
    scheduleSendStage();
    if(!root.querySelector('.workspace'))root.innerHTML='<header class="topbar"></header><div id="send-status" class="send-status" role="status" aria-live="polite" aria-atomic="true"></div><div class="statusbar"></div><div class="delivery-receipt"></div><main class="workspace"><nav class="folders"></nav><section class="listpane"></section><section class="reading" aria-label="Reading and compose pane"></section></main>';
    $('send-status').innerHTML=sendFeedback(model);
    if(model.send_result?.status==='rejected')submitted.delete(model.send_result.operation_id);
    root.querySelector('.delivery-receipt').innerHTML=(model.pending_sent||[]).map(last_sent=>sentReceipt({last_sent})).join('')+(model.send_stage==='CONFIRMING_SENT_COPY'?'':sentReceipt(model));
    const toolbarKey=JSON.stringify([model.configured,model.query,model.field]);
    if(wasFrozen||toolbarKey!==toolbarStamp){
      root.querySelector('.topbar').innerHTML=`<h1 class="brand">EMAIL</h1>${button('＋ New mail','compose','data-mode="new"',!model.configured,'primary')}<form id="search-form" class="search"><input id="search" aria-label="Search current mailbox folder" placeholder="Search mail · name, subject, order number" value="${esc((model.field!=='TEXT'&&model.query?model.field.toLowerCase()+': ':'')+model.query)}" maxlength="256"><button title="Search the live mailbox, including older messages">Search</button></form>${button('↻ Refresh','refresh','',!model.configured)}${button('⚙','settings','title="Email settings"')}`;
      toolbarStamp=toolbarKey;
    }
    const health=model.sync_health||{}, reconnecting=Boolean(model.error||model.live_error||model.recovery?.state==='stopped'||health.state==='RECONNECTING');
    const attention=['authentication','configuration','tls'].includes(health.category)||model.recovery?.state==='stopped';
    const status=!model.configured?'Not configured':attention?'Mailbox connection needs attention':reconnecting?(model.threads?.length?'Reconnecting · showing last synced mail':'Mailbox unavailable · retrying automatically'):model.initial_load_pending||model.read_pending||health.state==='SYNCING'?'Syncing…':'Connected';
    root.querySelector('.statusbar').innerHTML=`<span title="${esc(health.diagnosis||'Mail source: VentraIP IMAP')}"><span class="dot ${status==='Connected'?'':'off'}"></span>${esc(status)} · ${esc(model.mailbox)}${model.refreshed?' · Last synced: '+esc(model.refreshed):''}</span><span id="notice" class="notice" role="status">${attention?esc(health.diagnosis||'')+' <button type="button" data-action="retry_connection" class="connection-retry">Retry</button>':esc(model.recovery?.state||model.live_error?health.diagnosis||'':model.notice||health.diagnosis||'')}</span>`;
    if(model.recoverable_drafts?.length)root.querySelector('.statusbar').insertAdjacentHTML('beforeend',`<details><summary>${model.recoverable_drafts.length} saved drafts</summary>${model.recoverable_drafts.map(d=>button(esc(d.subject||'(No subject)'),'open_local_draft',`data-draft="${esc(d.draft_id)}"`)).join('')}</details>`);
    if(recoveryDrafts.length)root.querySelector('.statusbar').insertAdjacentHTML('beforeend',`<details><summary>Recover unsaved edits (${recoveryDrafts.length})</summary>${recoveryDrafts.map(d=>button('Recover copy: '+esc(d.subject||'(No subject)'),'recover_local_edits',`data-draft="${esc(d.id)}"`)+button('Download edits','export_draft_text',`data-draft="${esc(d.id)}"`)).join('')}</details>`);
    if(model.unresolved_receipts?.length)root.querySelector('.delivery-receipt').insertAdjacentHTML('beforeend',model.unresolved_receipts.map(r=>`<div class="sent-receipt">${esc(r.status==='accepted'?'Accepted by mail server; Sent copy '+r.copy_status:r.status==='unknown'?(r.notice||'Unknown send outcome. Do not resend.'):r.transport_status==='queued'?'Saved send is queued. Do not resend.':'Saved send is submitting. Do not resend.')} <small>${esc(r.operation_id)}</small>${button('Refresh status','refresh_recovery')}</div>`).join(''));
    scheduleReconnect();
    const foldersKey=JSON.stringify([model.folders,model.roles,model.folder,model.initial_load_pending]);
    if(wasFrozen||foldersKey!==folderStamp){const node=root.querySelector('.folders'),top=node.scrollTop;node.outerHTML=folders();root.querySelector('.folders').scrollTop=top;folderStamp=foldersKey;}
    const listKey=JSON.stringify([model.mailbox_version,model.folder,model.query,model.field,model.error,Boolean(model.live_error),model.limit,model.initial_load_pending,model.local_drafts,model.filters,model.read_pending,model.bulk_result]);
    if(wasFrozen||listKey!==listStamp){const node=root.querySelector('.listpane'),top=node.querySelector('.conversations')?.scrollTop||0;node.outerHTML=conversations();root.querySelector('.conversations').scrollTop=oldFolder===model.folder&&oldQuery===model.query?top:0;listStamp=listKey;}
    if(oldFolder!==model.folder||oldQuery!==model.query)mobileReading=model.view==='compose';
    root.querySelector('.workspace').className=`workspace ${collapsed?'collapsed':''} ${mobileReading?'show-reading':''}`;
    markSelection();if(imageOnly){
      patchImagePermission(root.querySelector('.reading'),model.messages);
      readingStamp=readerStamp(model);
    }else if(flagsOnly&&!wasFrozen){
      patchReadFlags(root.querySelector('.reading'),model.messages.find(row=>row.key===model.active_message));readingStamp=readerStamp(model);
    }else if(!(liveUpdate&&model.view==='compose'))paintReading(wasFrozen,selectionChanged);
    // Selection-only reads never freeze folder/list/toolbar nodes. Re-enable selected-message controls
    // by repainting only their pane after the server acknowledges the selected reference.
    if(selectionControlsDisabled&&!locked(model)&&model.view==='mail')paintReading(true);
    if($('draft-save-status'))$('draft-save-status').textContent=saveLabel();
    if(model.view==='compose'&&['Failed','Conflict'].includes(model.draft_save_status)&&!$('draft-recovery-actions')){
      $('draft-save-status')?.insertAdjacentHTML('afterend',`<span id="draft-recovery-actions">${button('Recover copy','recover_current_copy')}${button('Download edits','export_draft_text')}</span>`);
    }else if(model.draft_save_status==='Saved')$('draft-recovery-actions')?.remove();
    wire();renderDeleteConfirmation();fit();
    if(focusOwner&&!focusOwner.node.isConnected&&document.activeElement===document.body){
      const target=[...root.querySelectorAll('[id],[data-action],[data-pane],.mail-select')].find(node=>
        focusOwner.id?node.id===focusOwner.id:focusOwner.checkbox?node.classList.contains('mail-select')&&node.closest('.conversation-wrap')?.querySelector('.conversation')?.dataset.key===focusOwner.thread:
        focusOwner.pane?node.dataset.pane===focusOwner.pane:focusOwner.action&&node.dataset.action===focusOwner.action&&node.dataset.key===focusOwner.key&&node.dataset.folder===focusOwner.folder&&node.dataset.mode===focusOwner.mode);
      target?.focus({preventScroll:true});
    }
    // A fragment can finish essential mailbox loading without another app run.
    // Acknowledge only after the actual list and reading controls are painted.
    if (model.navigation_epoch !== undefined) {
      const status = model.error ? 'error' : model.initial_load_pending || model.body_pending ? 'loading' : 'ready';
      try { window.parent.SportsCaveTopBar?.completeNavigation?.({routeKey:'email', epoch:model.navigation_epoch, status}); } catch (_) {}
    }
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
      if($('notice'))$('notice').textContent='Attachment ready. Browser download started.';
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
      // One bounded request awaits the existing worker's completion. Cached
      // navigation still paints locally while the authenticated event is pending.
      completionRequest?.abort();
      historyTimer=setTimeout(()=>{if(!busy&&model.active_message===message_key&&model.body_pending===message_key)waitForBody(message_key);},0);
    } else if(model.read_mark_pending&&model.view==='mail'){
      const message_key=model.read_mark_pending;
      historyTimer=setTimeout(()=>{if(!busy&&model.active_message===message_key)emit('mark_visible_read',{message_key});},30);
    } else if(model.discovery_pending){
      historyTimer=setTimeout(()=>{if(!busy)emit('load_mail_metadata');},0);
    } else if(model.history_pending&&model.view==='mail'&&!model.error){
      const key=model.selected,version=model.mailbox_version;
      // Yield first paint. This fetches headers only, never speculative bodies or attachments.
      historyTimer=setTimeout(()=>{if(!busy&&model.selected===key&&model.mailbox_version===version)emit('resolve_thread',{thread_key:key,mailbox_version:version});},1000);
    } else if(model.live_pending){
      historyTimer=setTimeout(()=>{if(!busy)emit('live_check');},1000);
    } else if(model.sync_health?.state==='SYNCING'&&!model.recovery?.state){
      historyTimer=setTimeout(()=>{if(!busy)emit('sync_index');},1000);
    }
  }
  function compose(mode) {
    if (model.draft && !locked(model) && !confirm('Replace this open compose session? Save a mailbox draft first if you want to keep it.')) return;
    mobileReading=true;emit('compose',{mode,message_key:model.active_message});
  }
  function send(){
    if(!model.draft||busy||locked(model)||!model.smtp_configured||!model.settings_available)return;
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
  function previewKnownSearch(query){
    const known=folderViews.get(folderKey(model,model.folder))?.value.threads||model.threads||[];
    const found=searchKnownRows(known,query),rows=window.EmailInboxTools?.filterRows(found,model.filters)||found,pane=root.querySelector('.listpane');
    if(pane)pane.outerHTML=conversations({...model,threads:rows,local_drafts:[],has_more:false,error:'',query,read_pending:true});
    const footer=root.querySelector('.list-footer');
    if(footer)footer.textContent='Cached matches only · searching current folder…';
    listStamp='';
  }
  function uploadFile(f){
    if(!f||busy||locked(model)||model.view!=='compose')return;
    const attachments=model.draft?.attachments||[];
    if(f.size>10*1048576||attachments.length>=15||attachments.reduce((n,a)=>n+a.size,0)+f.size>14*1048576){$('notice').textContent='Attachment limit: 10 MB per file, 14 MB total, 15 files.';return;}
    const draft=model.draft.id,scope=model.reader_scope,reader=new FileReader();
    reader.onprogress=e=>{if(e.lengthComputable)$('notice').textContent=`Reading attachment: ${Math.round(e.loaded/e.total*100)}%`;};
    reader.onerror=()=>{$('notice').textContent='File could not be read. Try again.';};
    reader.onload=()=>{if(model.draft?.id!==draft||model.reader_scope!==scope||model.view!=='compose'){return;}emit('attach',{filename:f.name,base64:reader.result.split(',')[1]});if($('notice'))$('notice').textContent='Saving attachment…';};
    reader.readAsDataURL(f);
  }
  const inboxTools=window.EmailInboxTools?.create({root,model:()=>model,emit,busy:()=>busy,upload:uploadFile});
  function wire(){
    const searchInput=$('search');
    if(searchText!==null&&searchFolder===model.folder){
      searchInput.value=searchText;
      const authoritative=(model.field!=='TEXT'&&model.query?model.field.toLowerCase()+': ':'')+model.query;
      const requested=searchText.trim().replace(/^(from|to|subject|text):\s*/i,(_,field)=>field.toLowerCase()==='text'?'':field.toLowerCase()+': ');
      if(model.read_pending||requested!==authoritative)previewKnownSearch(searchText);
    }
    searchInput.oninput=()=>{
      searchText=searchInput.value;searchFolder=model.folder;
      previewKnownSearch(searchText);
      clearTimeout(searchTimer);
      const query=searchText,folder=searchFolder,scope=model.reader_scope;
      searchTimer=setTimeout(()=>{if(model.folder===folder&&model.reader_scope===scope)emit('search',{query});},350);
    };
    $('search-form').onsubmit=e=>{e.preventDefault();clearTimeout(searchTimer);searchText=searchInput.value;searchFolder=model.folder;emit('search',{query:searchText});};
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
      if(action==='show_images'){emit(action,{message_key:b.dataset.key,reader_identity:b.dataset.readerIdentity});return;}
      if(action==='reply_prompts'){showReplyPrompts(b);return;}
      if(action==='reply_prompt_help'){showReplyPrompts(b,true);return;}
      if(action==='copy_reply_prompt'){void copySelectedReplyPrompt(b.dataset.prompt);return;}
      if(action==='recover_local_edits'){
        const recovery=recoveryDrafts.find(d=>d.id===b.dataset.draft);
        if(recovery){mobileReading=true;emit('recover_draft_copy',{recovery});}return;
      }
      if(action==='recover_current_copy'){
        persistEdits();emit('recover_draft_copy',{recovery:snapshot()});return;
      }
      if(action==='export_draft_text'){
        const draft=b.dataset.draft?recoveryDrafts.find(d=>d.id===b.dataset.draft):snapshot();if(!draft)return;
        const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));
        const a=document.createElement('a');a.href=url;a.download='unsaved-email-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return;
      }
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
      if(action==='open_local_draft'){data.draft_id=b.dataset.draft;mobileReading=true;}
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
    if($('attachment'))$('attachment').onchange=()=>uploadFile($('attachment').files[0]);
    inboxTools?.render();
  }
  function targetFor(node){
    const folder=node.closest('[data-folder]');
    if(folder)return {kind:'folder',folder:folder.dataset.folder};
    const row=node.closest('[data-key]'),key=row?.dataset.key;
    const thread=model.threads.find(t=>t.key===key);
    if(thread)return {kind:'message',thread_key:thread.key,message_key:thread.message_key,
      unread:thread.message_unread,starred:thread.message_starred,folder:thread.folder||model.folder};
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
        mobileReading=true;emit('compose',{mode:action,message_key:target.message_key});return;
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
    // A modal owns its keys; composer send/close shortcuts must not escape it.
    if(document.querySelector('.inbox-dialog[open]'))return;
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
    if(event.data.type==='streamlit:render'){stopReady();render(event.data.args.model);}
  });
  window.addEventListener('resize',fit);try{window.parent.addEventListener('resize',fit);new ResizeObserver(fit).observe(window.frameElement);}catch(_){}
  document.addEventListener('visibilitychange',()=>{if(!document.hidden&&pendingSignal)signalTick(pendingSignal);});
  window.addEventListener('pagehide',()=>clearTimeout(signalRetryTimer));
  // Cached assets can announce before the host installs its listener. Retry only
  // until the first host render, within the component's initial loading window.
  window.addEventListener('pagehide',()=>stopReady());
  stopReady=componentHandshake(post);fit();
})();
