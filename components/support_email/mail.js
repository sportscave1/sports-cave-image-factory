(function () {
  'use strict';
  const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const size = n => Number(n) >= 1048576 ? (Number(n)/1048576).toFixed(1)+' MB' : Math.max(1, Math.round(Number(n)/1024))+' KB';
  const safeLink = value => {try {const u=new URL(value); return ['https:','http:','mailto:'].includes(u.protocol) && !u.username && !u.password ? u.href : '';} catch (_) {return '';}};
  const locked = m => ['accepted','unknown','in_progress'].includes((m.send_result || {}).status) || m.draft_pending;
  if (typeof module !== 'undefined') {module.exports={esc,size,safeLink,locked}; return;}
  const root=document.getElementById('mail');
  let model={}, busy=false, pending='', collapsed=false, mobileReading=false, localDraft=null, downloaded='', selection=null;
  const submitted=new Set();
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
    if (busy) return;
    const draft=snapshot();
    pending=crypto.randomUUID(); busy=true; root.classList.add('busy');
    freeze();
    if ($('notice')) $('notice').textContent=action==='send'?'Sending…':action==='download'?'Opening attachment…':action==='refresh'?'Refreshing…':'Working…';
    post('streamlit:setComponentValue',{value:{id:pending,action,...values,draft},dataType:'json'});
  }
  function freeze(){
    root.querySelectorAll('button,input,select,textarea').forEach(e=>e.disabled=true);
    root.querySelectorAll('[contenteditable=true]').forEach(e=>e.contentEditable='false');
  }
  function fit() {
    let height=700;
    try {height=Math.max(280,window.parent.innerHeight-window.frameElement.getBoundingClientRect().top-14);} catch (_) {}
    root.style.height=height+'px'; post('streamlit:setFrameHeight',{height});
  }
  const roleLabels={inbox:'Inbox',sent:'Sent',drafts:'Drafts',archive:'Archive',junk:'Junk',trash:'Trash'};
  const symbols={inbox:'▤',sent:'↗',drafts:'▧',archive:'▣',junk:'⊘',trash:'⌫'};
  const roleOf=f=>Object.keys(model.roles||{}).find(r=>model.roles[r]===f.name);
  function folders() {
    return `<nav class="folders" aria-label="Mail folders"><div class="folder-heading label">Mailbox</div>${(model.folders||[]).map(f=>{
      const role=roleOf(f); return `<button class="folder ${model.folder===f.name?'selected':''}" data-action="folder" data-folder="${esc(f.name)}" title="${esc(f.label)}" aria-label="${esc(roleLabels[role]||f.label)}"><span class="folder-symbol">${symbols[role]||'▱'}</span><span class="folder-name">${esc(roleLabels[role]||f.label)}</span><span class="folder-count">${f.unread>0?esc(f.unread):''}</span></button>`;
    }).join('')}${button('☰ <span>Collapse folders</span>','collapse','','', 'collapse plain')}</nav>`;
  }
  function conversations() {
    const folder=(model.folders||[]).find(f=>f.name===model.folder);
    return `<section class="listpane" aria-label="Conversations"><div class="list-heading row spread"><strong>${esc(roleLabels[roleOf(folder||{})]||folder?.label||'Mailbox')}</strong><small>${model.query?'Search · ':''}${(model.threads||[]).length} conversations</small></div><div class="conversations">${model.error?`<div class="empty">${esc(model.error)}</div>`:(model.threads||[]).map(t=>`<button class="conversation ${t.unread?'unread':''} ${model.selected===t.key?'selected':''}" data-action="open_thread" data-key="${esc(t.key)}" aria-label="${esc(t.customer+' · '+t.subject)}"><div class="row spread"><span class="sender ellipsis">${esc(t.customer||t.email||'Unknown sender')}</span><time>${esc(t.time)}</time></div><div class="subject ellipsis">${esc(t.subject)}</div><div class="row spread"><span class="preview ellipsis grow">${esc(t.snippet||'Open conversation')}</span><small>${t.attachment?'⌁ ':''}${t.starred?'★ ':''}${t.count>1?t.count:''}</small></div></button>`).join('')||'<div class="empty">No messages in this view.</div>'}</div><div class="list-footer">${model.has_more?button('Load 50 more','load_more'): '<span class="muted">'+(model.query?'Live search · current folder':'Live mailbox · latest messages')+'</span>'}</div></section>`;
  }
  const names=people=>(people||[]).map(p=>p.name?`${p.name} <${p.email}>`:p.email).join(', ');
  function messages() {
    const rows=model.messages||[], active=rows.find(m=>m.key===model.active_message)||rows[rows.length-1];
    const selectedThread=(model.threads||[]).find(t=>t.key===model.selected);
    if (!active) return `<div class="reading-scroll empty">${model.error?esc(model.error):'Select a conversation to read it.'}${model.draft?'<p class="attachments">'+button('Resume draft','resume_composer')+'</p>':''}</div>`;
    return `<div class="reading-toolbar">${button('←','back','','','mobile-back')}${button('Reply','compose','data-mode="reply"')}${button('Reply all','compose','data-mode="reply_all"')}${button('Forward','compose','data-mode="forward"')}<span class="grow"></span>${button('Archive','archive','',!model.roles.archive)}${button('Trash','trash','',!model.roles.trash)}${button(active.unread?'Mark read':'Mark unread',active.unread?'mark_read':'mark_unread')}${button(active.starred?'★':'☆',active.starred?'unstar':'star','title="Star / unstar"')}${button('Junk','junk','',!model.roles.junk)}</div><div class="reading-scroll"><div class="subject-header"><div class="row spread"><h2>${esc(active.subject)}</h2>${button('Customer / Order','context','','','plain')}</div><div class="customer">${esc(selectedThread?.customer||active.sender.name||active.sender.email)}</div><small>${esc(selectedThread?.email||active.sender.email)}</small><div class="meta">Actions apply to the selected message · ${esc(active.folder)} · ${esc(active.time)}</div>${active.draft?'<div class="attachments">'+button('Edit mailbox draft','edit_draft')+'</div>':''}${model.draft?'<div class="attachments">'+button('Resume draft','resume_composer')+'</div>':''}</div><div class="messages">${rows.map(m=>`<article class="message ${m.key===active.key?'active':''}"><button class="message-head" data-action="open_message" data-key="${esc(m.key)}" aria-expanded="${m.expanded}"><div class="row spread"><span class="label">${m.own?'Sports Cave':'Customer'} ${m.expanded?'':'· expand'}</span><small>${esc(m.time)}</small></div><div class="person">${esc(m.sender.name||m.sender.email)}</div><div class="meta">${esc(m.sender.email)}${m.expanded?'<br>To: '+esc(names(m.to))+(m.cc.length?' · CC: '+esc(names(m.cc)):''):''}</div></button>${m.expanded?`<div class="message-body">${m.html}</div>${m.quote?`<details><summary>Show quoted text</summary><div class="quote">${m.quote}</div></details>`:''}${(m.warnings||[]).map(w=>'<p class="muted">'+esc(w)+'</p>').join('')}<div class="attachments">${m.attachments.map(a=>button('⌁ '+esc(a.filename)+' · '+size(a.encoded_size)+' ↓','download',`data-key="${esc(m.key)}" data-section="${esc(a.section)}" title="Download directly from mailbox"`)).join('')}</div>`:''}</article>`).join('')}</div></div>`;
  }
  function formatBar(target='editor') {
    return `<div class="format-bar" data-editor="${target}">${[['B','bold'],['I','italic'],['U','underline'],['↗ Link','createLink'],['• List','insertUnorderedList'],['1. List','insertOrderedList']].map(([label,cmd])=>`<button type="button" data-command="${cmd}" title="${cmd}">${label}</button>`).join('')}</div>`;
  }
  function signaturesOptions(value,none=true) {
    return Object.entries(model.settings.signatures).map(([key,s])=>`<option value="${key}" ${value===key?'selected':''}>${esc(s.label)}</option>`).join('')+(none?`<option value="none" ${value==='none'?'selected':''}>No signature</option>`:'');
  }
  function composer() {
    if (!model.draft) return messages();
    const draft={...model.draft,...(localDraft?.id===model.draft.id?localDraft:{})}, lock=locked(model), status=model.send_result?.status;
    const forwarded=draft.mode==='forward'?(model.messages||[]).flatMap(m=>m.attachments.map(a=>({...a,message_key:m.key}))):[];
    return `<section class="panel" aria-label="Compose mail"><div class="panel-head"><strong>${{new:'New mail',reply:'Reply',reply_all:'Reply all',forward:'Forward'}[draft.mode]||'Draft'}</strong>${button('Close · Esc','close_composer','','','plain')}</div>${status?`<div class="delivery">${esc(model.send_result.notice)} ${['accepted','unknown'].includes(status)?button('Check Sent','check_sent'):status==='rejected'?button('Prepare again','retry_rejected'):''}</div>`:''}<div class="compose-fields"><div class="compose-field"><label>From</label><span>${esc(model.settings.sender_name)} &lt;${esc(model.mailbox)}&gt;</span></div>${['to','cc','bcc','subject'].map(key=>`<div class="compose-field"><label for="draft-${key}">${key==='subject'?'Subject':key.toUpperCase()}</label><input id="draft-${key}" value="${esc(draft[key])}" ${lock?'disabled':''} autocomplete="off" maxlength="${key==='subject'?998:4000}" placeholder="${key==='to'?'name@example.com':''}"></div>`).join('')}</div>${formatBar()}<div class="compose-scroll"><div id="editor" class="editor" contenteditable="${!lock}" role="textbox" aria-label="Message body" aria-multiline="true">${draft.html}</div><div id="signature-preview" class="signature-preview">${model.settings.signatures[draft.signature]?.html||''}</div>${draft.quote_html?`<details><summary>Previous message</summary><label class="checkbox"><input id="include-quote" type="checkbox" ${draft.include_quote?'checked':''} ${lock?'disabled':''}>Include quoted message</label><div class="quote">${draft.quote_html}</div>${forwarded.length?'<p class="muted">Include original attachments:</p><div class="attachments">'+forwarded.map(a=>button('＋ '+esc(a.filename),'forward_attachment',`data-key="${esc(a.message_key)}" data-section="${esc(a.section)}"`,lock)).join('')+'</div>':''}</details>`:''}<div class="attachments">${draft.attachments.map(a=>`<span class="pill">⌁ ${esc(a.filename)} <small>${size(a.size)}</small>${button('×','remove_attachment',`data-attachment="${esc(a.id)}" title="Remove attachment"`,lock)}</span>`).join('')}</div></div><div class="compose-bottom"><div class="row wrap">${button('Send','send','title="Ctrl+Enter"',lock||status==='rejected'||!model.smtp_configured,'primary')}${button('Attach file','choose_file','',lock)}<input id="attachment" class="hidden-file" type="file" ${lock?'disabled':''}>${button('Save draft','save_draft','',!model.roles.drafts||['accepted','unknown','in_progress'].includes(status))}<span class="grow"></span><select id="signature" aria-label="Signature" ${lock?'disabled':''}>${signaturesOptions(draft.signature)}</select>${button('Discard','discard_draft','',lock,'plain')}</div>${!model.smtp_configured?'<small>SMTP needs configuration before sending.</small>':'<small>10 MB per file · 14 MB attachments total · 20 MB encoded message</small>'}${model.draft_pending?'<p class="muted">Draft save is pending. Save draft checks for its existing copy.</p>':''}</div></section>`;
  }
  function settings() {
    const s=model.settings;
    return `<section class="panel"><div class="panel-head"><strong>Email settings</strong>${button('Close','close_panel','','','plain')}</div><div class="panel-scroll stack"><div><div class="label">Connection</div><p>${esc(model.mailbox)}</p><small>IMAP ${model.configured?'configured':'not configured'} · SMTP ${model.smtp_configured?'configured':'not configured'}</small></div>${button('Test IMAP connection','test_connection','',!model.configured)}<label>Your default signature<select id="preference">${signaturesOptions(model.signature_preference)}</select></label>${button('Save my preference','save_preference','',!model.settings_available)}${!model.settings_available?'<small>Settings storage is unavailable. Defaults remain usable.</small>':''}${model.admin?`<div class="section stack"><div class="label">Mailbox settings</div><label>Sender display name<input id="sender-name" value="${esc(s.sender_name)}" maxlength="120"></label><div class="mapping">${['sent','drafts','archive','junk','trash'].map(role=>`<label for="map-${role}">${roleLabels[role]}</label><select id="map-${role}"><option value="">Use special-use discovery</option>${model.folders.filter(f=>f.name.toUpperCase()!=='INBOX').map(f=>`<option value="${esc(f.name)}" ${s.folder_mapping[role]===f.name?'selected':''}>${esc(f.label)}</option>`).join('')}</select>`).join('')}</div><label>Sent copy handling<select id="sent-policy">${[['verify','Verify only · awaiting live test'],['server','Server saves Sent · confirmed'],['append','App saves Sent · confirmed server does not']].map(([v,l])=>`<option value="${v}" ${s.sent_policy===v?'selected':''}>${l}</option>`).join('')}</select></label><small>Choose app saving only after a supervised test confirms SMTP does not save Sent. Every send checks its Message-ID first.</small><div class="label">Signatures</div>${Object.entries(s.signatures).map(([key,sig])=>`<label>${esc(sig.label)}</label>${formatBar('sig-'+key)}<div id="sig-${key}" class="signature-edit" contenteditable="true" role="textbox" aria-label="${esc(sig.label)} signature">${sig.html}</div>`).join('')}${button('Save mailbox settings','save_settings','',!model.settings_available,'primary')}</div>`:''}</div></section>`;
  }
  function external(label,url){url=safeLink(url); return url?`<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`:'';}
  function appURL(query) {try{return window.parent.location.href.split('?')[0].split('#')[0]+query;}catch(_){return '';}}
  function contextPanel(){
    const c=model.context||{},o=c.order,w=c.workflow||{};
    return `<section class="panel"><div class="panel-head"><strong>Customer / Order</strong>${button('Close','close_panel','','','plain')}</div><div class="panel-scroll"><h3>${esc(c.label||'No order matched')}</h3>${(c.candidates||[]).map(v=>'<p class="context-item">'+esc(v.name)+' · '+esc(v.date)+'</p>').join('')}${o?`<div class="context-item"><strong>${esc(o.name)}</strong><br>${esc(o.date)}<br>Fulfilment: ${esc(o.fulfilment)}</div>${o.lines.map(l=>`<div class="context-item">${esc(l.product_title)}<br><small>${esc(l.variant_title)}</small></div>`).join('')}${o.editions.map(e=>`<div class="context-item">Edition ${esc(e.edition_number)} / ${esc(e.edition_total)}<br>Certificate: ${esc(e.certificate_status||'Not recorded')}<br>${external('Open Edition',appURL(o.edition_url))}</div>`).join('')}<div class="section stack">${external('Open Shopify order',o.shopify_url)}${external('Open Sports Cave order',appURL(o.os_url))}${o.tracking.map(u=>external('Open tracking',u)).join('')}</div>${o.previous.length?'<div class="section"><div class="label">Previous orders</div>'+o.previous.map(p=>'<p class="context-item">'+esc(p.name)+' · '+esc(p.date)+'</p>').join('')+'</div>':''}`:''}<div class="section stack"><div class="label">Internal support workflow</div>${c.workflow_available&&!w.conflict?`<label>Status<select id="workflow-status">${['Needs Reply','Waiting on Customer','Waiting on Sports Cave','Resolved'].map(s=>`<option ${w.support_status===s?'selected':''}>${s}</option>`).join('')}</select></label><label>Assigned<select id="workflow-assigned"><option value="">Unassigned</option>${c.assignees.map(a=>`<option value="${esc(a.id)}" ${w.assigned_user_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select></label><label>Internal notes<textarea id="workflow-notes" maxlength="8000">${esc(w.internal_notes||'')}</textarea></label><label class="checkbox"><input id="workflow-approval" type="checkbox" ${w.needs_approval?'checked':''}>Requires Nathan's approval</label><small>Internal only. Notes are never included in email.</small>${button('Save workflow','workflow')}`:'<small>Workflow metadata is unavailable or conflicting. Mail remains in the live mailbox.</small>'}</div></div></section>`;
  }
  function render(next) {
    const positions=[...root.querySelectorAll('.conversations,.reading-scroll,.compose-scroll,.panel-scroll')].map(e=>[e.className,e.scrollTop]);
    if (next.draft?.id!==model.draft?.id || next.send_result?.status==='accepted') localDraft=null;
    model=next;
    if (model.ack===pending) {
      busy=false;pending='';
      if (model.draft && !model.send_result?.status) submitted.delete(model.draft.operation_id);
    }
    if (model.draft && !localDraft) localDraft=Object.fromEntries(['id','to','cc','bcc','subject','html','signature','include_quote'].map(k=>[k,model.draft[k]]));
    if (model.draft && localDraft) localDraft.operation_id=model.draft.operation_id;
    root.className=busy?'busy':'';
    root.innerHTML=`<header class="topbar"><h1 class="brand">EMAIL</h1>${button('＋ New mail','compose','data-mode="new"',!model.configured,'primary')}<form id="search-form" class="search"><input id="search" aria-label="Search current mailbox folder" placeholder="Search mail · name, subject, order number" value="${esc((model.field!=='TEXT'&&model.query?model.field.toLowerCase()+': ':'')+model.query)}" maxlength="256"><button title="Search the live mailbox, including older messages">Search</button></form>${button('↻ Refresh','refresh','',!model.configured)}${button('⚙','settings','title="Email settings"')}</header><div class="statusbar"><span title="Mail source: VentraIP IMAP"><span class="dot ${model.error||!model.configured?'off':''}"></span>${!model.configured?'Not configured':model.error?'Connection error':'Live'} · ${esc(model.mailbox)}${model.refreshed?' · '+esc(model.refreshed):''}</span><span id="notice" class="notice" role="status" title="${esc(model.notice||model.error)}">${esc(model.notice||model.error)}</span></div><main class="workspace ${collapsed?'collapsed':''} ${mobileReading?'show-reading':''}">${folders()}${conversations()}<section class="reading" aria-label="Reading and compose pane">${model.view==='compose'?composer():model.view==='settings'?settings():model.view==='context'?contextPanel():messages()}</section></main>`;
    for(const [c,top] of positions) {const e=root.querySelector('.'+c.split(' ')[0]);if(e)e.scrollTop=top;}
    if (busy) freeze();
    wire();fit();
    if(model.download && model.download.id!==downloaded){
      downloaded=model.download.id;
      const bytes=Uint8Array.from(atob(model.download.base64),c=>c.charCodeAt(0));
      const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'}));
      const a=document.createElement('a'); a.href=url;a.download=model.download.filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
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
  function wire(){
    $('search-form').onsubmit=e=>{e.preventDefault();emit('search',{query:$('search').value});};
    root.onclick=e=>{
      const b=e.target.closest('button');if(!b||b.disabled)return;
      if(b.dataset.command){
        const target=$(b.closest('[data-editor]').dataset.editor);if(target.contentEditable!=='true')return;
        target.focus();if(selection&&target.contains(selection.commonAncestorContainer)){const s=window.getSelection();s.removeAllRanges();s.addRange(selection);}
        let value=null;if(b.dataset.command==='createLink'){value=safeLink(prompt('Link URL (https://… or mailto:…)')||'');if(!value)return;}
        document.execCommand(b.dataset.command,false,value);snapshot();return;
      }
      const action=b.dataset.action;if(!action)return;
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
      e.addEventListener('paste',event=>{event.preventDefault();document.execCommand('insertText',false,event.clipboardData.getData('text/plain'));});
      e.addEventListener('drop',event=>event.preventDefault());
      e.addEventListener('keyup',()=>{const s=window.getSelection();if(s.rangeCount)selection=s.getRangeAt(0).cloneRange();});
      e.addEventListener('mouseup',()=>{const s=window.getSelection();if(s.rangeCount)selection=s.getRangeAt(0).cloneRange();});
    });
    root.querySelectorAll('[data-command]').forEach(b=>b.onmousedown=e=>e.preventDefault());
    if($('signature'))$('signature').onchange=()=>{$('signature-preview').innerHTML=model.settings.signatures[$('signature').value]?.html||'';snapshot();};
    if($('attachment'))$('attachment').onchange=async()=>{const f=$('attachment').files[0];if(!f)return;if(f.size>10*1048576){$('notice').textContent='Attachment too large. Maximum file size is 10 MB.';return;}const reader=new FileReader();reader.onload=()=>emit('attach',{filename:f.name,base64:reader.result.split(',')[1]});reader.readAsDataURL(f);};
  }
  document.addEventListener('keydown',e=>{
    if(e.ctrlKey&&e.key==='Enter'&&model.view==='compose'){e.preventDefault();send();}
    if(e.key==='Escape'&&model.view==='compose'){e.preventDefault();emit('close_composer');}
    const typing=e.target.matches('input,textarea,select,[contenteditable]')||e.target.closest('[contenteditable]');
    if(!typing&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&model.view==='mail'&&model.active_message){if(e.key.toLowerCase()==='r')compose('reply');if(e.key.toLowerCase()==='f')compose('forward');}
  });
  window.addEventListener('message',event=>{if(event.source===window.parent&&event.data.type==='streamlit:render')render(event.data.args.model);});
  window.addEventListener('resize',fit);try{window.parent.addEventListener('resize',fit);}catch(_){}
  post('streamlit:componentReady',{apiVersion:1});fit();
})();
