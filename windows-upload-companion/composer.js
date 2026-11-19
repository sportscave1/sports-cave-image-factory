(() => {
  'use strict';
  const design = /^https:\/\/chatgpt\.com\/g\/g-p-6a1e449948e881919c1e345006d63654(?:-[a-z0-9-]+)?\//.test(location.href);
  const ad = /^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\//.test(location.href);
  const project = ad ? 'https://chatgpt.com/g/g-p-6a6bd98cd6f081918788b544dcdecfc2/project' : design ? 'https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/project' : 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
  const conversation = ad ? /^https:\/\/chatgpt\.com\/g\/g-p-6a6bd98cd6f081918788b544dcdecfc2(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/ : design ? /^https:\/\/chatgpt\.com\/g\/g-p-6a1e449948e881919c1e345006d63654(?:-[a-z0-9-]+)?\/c\/[a-f0-9-]{36}$/ : /^https:\/\/chatgpt\.com\/g\/g-p-6a387a17627081918e1700ec2783a12b(?:-sc-mockups-uploads)?\/c\/[a-f0-9-]{36}$/;
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  // Block wrappers created by Edge can add a visual blank line to innerText.
  const normalize = text => text.replace(/\r\n?/g, '\n').replace(/\u00a0/g, ' ')
    .replace(/\n{3,}/g, '\n\n').trimEnd();
  let busy = false;
  let cancelled = false;
  const inProject = () => location.href === project;
  const workEditor = ad ? '[role="textbox"][contenteditable="true"][aria-label="New chat in Sports Cave Meta Ads"]' : design ? '[role="textbox"][contenteditable="true"][aria-label^="New chat in "]' : '[role="textbox"][contenteditable="true"][aria-label="New chat in SC Mockups/Uploads"]';
  const input = () => document.querySelector(workEditor) || document.querySelector('#prompt-textarea[contenteditable="true"]');
  const formFor = node => node?.closest('form');
  const sendButton = form => {
    const buttons = Array.from(form?.querySelectorAll('button[data-testid="send-button"], button[aria-label="Send"]') || []);
    const visible = buttons.filter(button => button.isConnected &&
      (!button.getClientRects || button.getClientRects().length));
    return visible.find(button => !button.disabled && button.getAttribute('aria-disabled') !== 'true') || visible[0];
  };
  const existingTurn = () => document.querySelector('[data-message-author-role="user"], [data-message-author-role="assistant"], h4[data-conversation-role="user"], h4[data-conversation-role="assistant"]');
  // Work now labels image controls "Remove <filename>". Keep the search scoped
  // to this composer; referenceControl still verifies the expected filename.
  const attachments = form => {
    const controls = Array.from(form?.querySelectorAll('button[aria-label^="Remove "]') || []);
    // Attachment previews may also have an attachment test ID. Count the
    // removal controls, not both a preview and its removal control.
    return controls.length ? controls : Array.from(form?.querySelectorAll('button[data-testid*="attachment"]') || []);
  };
  const pastedText = 'Remove pasted text attachment';
  const pickerSelector = 'button[aria-label="Select ChatGPT model"]';
  const stepsFromMaximum = 1;
  async function waitFor(check, ms) {
    const end = Date.now() + ms;
    do {
      const value = check();
      if (value) return value;
      await delay(150);
    } while (Date.now() < end);
    return null;
  }
  const keyDown = (element, key) => element.dispatchEvent(
    new KeyboardEvent('keydown', {key, code:key, bubbles:true, cancelable:true}));
  function powerControl(trigger) {
    if (!trigger) return null;
    const controlled = trigger.getAttribute('aria-controls');
    if (trigger.getAttribute('aria-expanded') === 'false') return null;
    const menu = (controlled && document.getElementById(controlled)) ||
      document.querySelector('[role="menu"][aria-label="Select ChatGPT model"]');
    if (!menu?.matches('[role="menu"]')) return null;
    const power = Array.from(menu.querySelectorAll('[role="menuitem"]')).find(item =>
      /^Power(?:\s|$)/i.test(item.getAttribute('aria-label') || item.textContent.trim()));
    const steps = Array.from(menu.querySelectorAll('[role="status"], [aria-live]'))
      .map(status => status.textContent.match(/(?:^|\D)(\d+)\s+of\s+(\d+)\.?\s*$/i))
      .find(Boolean);
    if (!power || !steps) return null;
    const [, current, total] = steps.map(Number);
    if (current < 1 || current > total || total <= stepsFromMaximum) return null;
    return {power, current, total};
  }
  async function setThinkingLevel() {
    const currentTrigger = () => {
      if (cancelled || !inProject() || existingTurn()) return null;
      const inside = formFor(input())?.querySelector(pickerSelector);
      const pickers = document.querySelectorAll(pickerSelector);
      return inside || (pickers.length === 1 ? pickers[0] : null);
    };
    const trigger = await waitFor(currentTrigger, 10000);
    if (!trigger) return false;
    // Never retain the old trigger/menu across React updates.
    if (trigger.getAttribute('aria-expanded') !== 'true') {
      trigger.focus();
      keyDown(trigger, 'Enter');
      if (!await waitFor(() => currentTrigger()?.getAttribute('aria-expanded') === 'true', 1800)) {
        currentTrigger()?.click();
      }
    }
    try {
      let control = await waitFor(() => powerControl(currentTrigger()), 10000);
      if (!control) return false;
      const target = control.total - stepsFromMaximum;
      while (!cancelled && inProject() && control.current !== target) {
        const {power, current, total} = control;
        const direction = current < target ? 1 : -1;
        power.focus();
        keyDown(power, direction > 0 ? 'ArrowRight' : 'ArrowLeft');
        control = await waitFor(() => {
          const next = powerControl(currentTrigger());
          return next?.current === current + direction && next.total === total ? next : null;
        }, 5000);
        if (!control) return false;
      }
      if (cancelled || !inProject() || control.current !== target) return false;
    } finally {
      if (currentTrigger()?.getAttribute('aria-expanded') === 'true') {
        keyDown(powerControl(currentTrigger())?.power || currentTrigger(), 'Escape');
        if (!await waitFor(() => currentTrigger()?.getAttribute('aria-expanded') !== 'true', 1800)) {
          // Some Work menus ignore synthetic Escape. Toggle the same picker
          // closed, then verify it actually closed before allowing Send.
          currentTrigger().focus();
          keyDown(currentTrigger(), 'Enter');
          if (!await waitFor(() => currentTrigger()?.getAttribute('aria-expanded') !== 'true', 1800)) {
            currentTrigger().click();
            await waitFor(() => currentTrigger()?.getAttribute('aria-expanded') !== 'true', 1800);
          }
        }
      }
    }
    const closed = !cancelled && currentTrigger()?.getAttribute('aria-expanded') === 'false';
    return closed;
  }
  const thinkingUnavailable = () => ({
    sent:false,
    reason:'Could not verify one step below maximum thinking level in the ChatGPT project composer.',
  });
  async function fill(node, form, prompt, reference) {
    const promptAttachments=()=>attachments(form).filter(file=>file!==referenceControl(form,reference));
    // Work turns long pastes into a text attachment, just like Ctrl+V.
    if (node.matches(workEditor)) {
      const data = new DataTransfer();
      data.setData('text/plain', prompt);
      node.dispatchEvent(new ClipboardEvent('paste', {clipboardData:data, bubbles:true, cancelable:true}));
      const pasted = await waitFor(() => node.innerText.trim() || promptAttachments().length, 1200);
      if (pasted) return;
    }
    if (inProject() && document.activeElement === node && !node.innerText.trim() && !promptAttachments().length) {
      document.execCommand('insertText', false, prompt);
    }
  }

  const sentReference=(body,reference)=>!reference || Boolean(body &&
    (body.innerText?.includes(reference.name) || body.querySelector('img, [data-testid*="image-attachment"]')));
  function submittedPrompt(prompt, sentAsAttachment, reference) {
    if (!inProject() && !conversation.test(location.href)) return false;
    const workTurns = Array.from(document.querySelectorAll('h4[data-conversation-role="user"]'));
    if (sentAsAttachment) {
      return conversation.test(location.href) && workTurns.length === 1 &&
        !!workTurns[0].nextElementSibling?.querySelector('button[aria-label^="Pasted text("]') &&
        sentReference(workTurns[0].nextElementSibling,reference);
    }
    const bodies = [...workTurns.map(turn => turn.nextElementSibling),
      ...Array.from(document.querySelectorAll('[data-message-author-role="user"]'),
        turn => turn.querySelector('.whitespace-pre-wrap') || turn)];
    return bodies.some(body => body && (normalize(body.innerText) === normalize(prompt) ||
      (reference && normalize(body.innerText).includes(normalize(prompt)))) && sentReference(body,reference));
  }
  function referenceControl(form,reference){
    if(!reference)return null;
    const files=attachments(form).filter(file=>file.getAttribute('aria-label')!==pastedText);
    if(files.length!==1)return null;
    const file=files[0],label=file.getAttribute('aria-label')||'';
    // ChatGPT adds a numeric duplicate suffix after the verified bytes finish
    // uploading (original.webp -> original(5).webp). It is still the sole image
    // this invocation attached, not a missing or different reference.
    const sameName = name => name === reference.name ||
      name.replace(/ ?\(\d+\)(?=\.webp$)/, '') === reference.name;
    const displayed = label.replace(/^Remove (?:file |image )?/, '').trim();
    return sameName(displayed) || sameName(file.parentElement?.textContent?.trim() || '') ||
      label==='Remove image' || label==='Remove file' ? file : null;
  }
  async function attachReference(node,form,reference){
    if(!reference)return true;
    if(reference.type!=='image/webp' || !reference.name?.endsWith('.webp') || /[/\\]/.test(reference.name) ||
       !Number.isInteger(reference.size) || reference.size<1 || reference.size>16*1024*1024 ||
       typeof reference.data!=='string' || reference.data.length>24*1024*1024)return false;
    const bytes=Uint8Array.from(atob(reference.data),c=>c.charCodeAt(0));
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
    if(bytes.length!==reference.size || hash!==reference.sha256)return false;
    const data=new DataTransfer();
    data.items.add(new File([bytes],reference.name,{type:'image/webp'}));
    const inputs=Array.from(form.querySelectorAll('input[type="file"]'));
    if(inputs.length===1){
      inputs[0].files=data.files;
      inputs[0].dispatchEvent(new Event('change',{bubbles:true}));
    }else{
      node.focus();
      node.dispatchEvent(new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true}));
    }
    return Boolean(await waitFor(()=>inProject() && !existingTurn() && referenceControl(formFor(input()),reference),25000));
  }
  async function preserveRestoredDraft(id, node, form, freshUpload) {
    if (!node.innerText.trim()) return true;
    if ((!design && !freshUpload) || existingTurn() || attachments(form).length) return false;
    const text=node.innerText;
    const saved=await chrome.runtime.sendMessage({type:'project:backup-draft',id,text});
    if (!saved?.ok || !inProject() || input()!==node || node.innerText!==text ||
        existingTurn() || attachments(form).length) return false;
    // Only the new tab owned by this upload is cleared. Keep a durable local
    // backup plus a selectable copy in that tab; never submit the restored draft.
    const note=document.createElement('details');
    note.id='sc-companion-preserved-draft';
    const title=document.createElement('summary');
    title.textContent='Previous unsent draft — saved locally';
    const body=document.createElement('pre');
    body.textContent=text;
    body.style.whiteSpace='pre-wrap';
    note.append(title,body);
    note.style.cssText='position:fixed;bottom:12px;right:12px;z-index:2147483000;max-width:420px;max-height:240px;overflow:auto;background:#fff;color:#222;border:1px solid #bbb;border-radius:8px;padding:8px;font:12px sans-serif';
    document.body.append(note);
    node.focus();
    if (document.activeElement!==node) return false;
    const range=document.createRange();
    range.selectNodeContents(node);
    const selection=window.getSelection();
    selection.removeAllRanges();selection.addRange(range);
    document.execCommand('insertText',false,'');
    return Boolean(await waitFor(()=>inProject() && !existingTurn() && input() &&
      !input().innerText.trim() && !attachments(formFor(input())).length,1500));
  }
  async function send({id, prompt, freshUpload=false, reference}) {
    if (!inProject() || busy || typeof prompt !== 'string') return {sent:false};
    busy = true;
    try {
      let node = await waitFor(() => inProject() && input(), 7500);
      let form = formFor(node);
      if (!node || !form || existingTurn() || attachments(form).length) return {sent:false,
        reason:'ChatGPT is not a new empty project chat; existing messages or attachments were left untouched.'};
      if (!await preserveRestoredDraft(id,node,form,freshUpload)) return {sent:false,
        reason:'The restored draft could not be saved safely. It was left untouched.'};
      if (!await setThinkingLevel()) return thinkingUnavailable();
      node = input();
      form = formFor(node);
      if (!node || !form || existingTurn() || attachments(form).length || node.innerText.trim()) return {sent:false};

      if(!await attachReference(node,form,reference))return {sent:false,
        reason:'ChatGPT could not attach the verified black-frame WebP. The prompt was not sent without its original.'};
      node=input();form=formFor(node);
      if(!node || !form || existingTurn())return {sent:false};

      node.focus();
      if (!inProject() || document.activeElement !== node || node.innerText.trim()) return {sent:false};
      await fill(node, form, prompt, reference);
      const promptText = normalize(prompt);
      const isWork = node.matches(workEditor);
      const sendWait = isWork ? 120000 : 4500;
      let waitingFor = 'prepared composer';
      const waiting = reason => {waitingFor = reason; return null;};
      const ready = () => {
        if (cancelled || !inProject() || existingTurn()) return waiting('unchanged new-chat destination');
        // Work can replace the composer while it uploads a pasted attachment.
        const editor = input();
        if (!editor || editor.matches(workEditor) !== isWork) return waiting('project text editor');
        const composer = formFor(editor);
        const button = sendButton(composer);
        if (!button?.isConnected) return waiting('Send button inside the current composer');
        if (button.disabled || button.getAttribute('aria-disabled') === 'true') return waiting('enabled Send button');
        const allFiles = attachments(composer);
        const original=referenceControl(composer,reference);
        if(reference && !original)return waiting('verified reference image attachment');
        const files=allFiles.filter(file=>file!==original);
        if (!files.length && normalize(editor.innerText) === promptText) return {button, asAttachment:false};
        if (!isWork || editor.innerText.trim() || files.length !== 1 ||
          files[0].getAttribute('aria-label') !== pastedText) return waiting('one pasted prompt attachment and empty text editor');
        // This invocation started with an empty composer and pasted the exact
        // supplied prompt. The single pasted-text control is its upload receipt;
        // its abbreviated preview is presentation, not a second content gate.
        return {button, asAttachment:true};
      };
      // Long Work pastes upload before Send is enabled.
      if (!await waitFor(ready, sendWait)) {
        return {sent:false, reason:'ChatGPT did not make the pasted prompt ready to send: waiting for ' + waitingFor + '.'};
      }
      // Power was selected and verified before preparing the draft. Do not
      // reopen the model menu after upload: it can rerender this ready composer.
      const permission = await chrome.runtime.sendMessage({type:'project:permit', id});
      if (cancelled || !permission?.ok) return {sent:false,
        reason:'The companion could not reserve this submission. Check the upload status before retrying.'};
      const current = await waitFor(ready, sendWait);
      if (cancelled || !current) return {sent:false,
        reason:'ChatGPT submission stopped after reserving Send: waiting for ' + waitingFor + '.'};
      const {button, asAttachment:sentAsAttachment} = current;
      button.click();
      const accepted = await waitFor(() => submittedPrompt(prompt, sentAsAttachment,reference), 12000);
      if (accepted && prompt.includes('SC_UPLOAD_BLOCKED: REFERENCE')) watchStaffResponse();
      return {sent:Boolean(accepted)};
    } finally {
      busy = false;
    }
  }
  function projectProgress() {
    const turns = document.querySelectorAll('[data-message-author-role="assistant"], h4[data-conversation-role="assistant"]');
    const last = turns[turns.length - 1];
    const body = last?.matches('h4') ? last.nextElementSibling : last;
    const text = body?.innerText || '';
    const generating = Boolean(document.querySelector('[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"], button[aria-label="Stop response"], button[aria-label="Stop"]'));
    const clean = text.replace(/[*`]/g, '');
    const marker = !generating && clean.match(ad ? /(?:^|\n)\s*SC_AD_BLOCKED:\s*([^\n]+)/ : design ? /(?:^|\n)\s*SC_DESIGN_BLOCKED:\s*([^\n]+)/ : /(?:^|\n)\s*SC_UPLOAD_BLOCKED:\s*([A-Z_]+)/);
    const alert = !generating && [...document.querySelectorAll('[role="alert"]')].find(node =>
      node.getClientRects?.().length && /something went wrong|network error|failed to|unable to|error generating|conversation not found|try again/i.test(node.innerText || ''));
    // A completed response can report a tool rejection without emitting our
    // status marker. Preserve that concrete blocker instead of an idle timeout.
    const moderationBlocked = !design && !ad && !generating &&
      /\bmoderation_blocked\b/i.test(clean) &&
      /\b(?:pending|unfinished|remain(?:s)? blocked|cannot complete)\b/i.test(clean);
    // Require both a concrete failure and unfinished delivery. Review concerns,
    // repaired failures and a still-streaming answer must not release the slot.
    const designIncomplete = /\b(?:replacement PSD|updated JSON|delivery|deliverables?|treatment|revision|handoff)\b[^.!?\n]{0,180}\b(?:still |remain(?:s)? )?(?:pending|unfinished|not (?:saved|delivered|completed))\b/i.test(clean) ||
      /\bbefore I could\b[^.!?\n]{0,160}\b(?:save|deliver|finish)\b/i.test(clean);
    const designFailure = /\b(?:image (?:service|tool)|generation)\b[^.!?\n]{0,100}\b(?:rejected|blocked|failed|cancelled|canceled)\b|\b(?:workspace|session)\b[^.!?\n]{0,80}\bdisconnected\b|\b(?:cannot|could not|unable to)\s+(?:complete|finish|deliver)\b/i.test(clean);
    const designBlocked = design && !generating && designIncomplete && designFailure;
    const reason = marker ? (design || ad ? marker[1] : 'ChatGPT reported an upload failure: ' + marker[1]) :
      designBlocked ? 'Design stopped before delivery: ' + clean.trim() :
      moderationBlocked ? 'ChatGPT reported an upload failure: MODERATION' :
      alert ? 'ChatGPT error: ' + alert.innerText : '';
    let activity = 0;
    for (let i = 0; i < text.length; i++) activity = ((activity << 5) - activity + text.charCodeAt(i)) | 0;
    return {blocked:Boolean(reason), reason:reason.slice(0,1600), generating,
      finished:!generating && Boolean(text.trim()), activity:String(activity), chat_url:location.href};
  }
  function watchDesignResponse() {
    if (!design || typeof setInterval !== 'function') return;
    let previous = '', notified = '';
    const timer = setInterval(() => {
      if (!conversation.test(location.href)) return;
      const progress = projectProgress();
      const signature = progress.blocked ? location.href + ':' + progress.activity : '';
      // Two matching observations avoid waking on a transient render between
      // tool calls. The worker re-reads progress from the owned tab itself.
      if (signature && signature === previous && signature !== notified) {
        try {
          const runtime = globalThis.chrome?.runtime;
          if (runtime?.id && typeof runtime.sendMessage === 'function') {
            notified = signature;
            Promise.resolve(runtime.sendMessage({type:'project:design-progress'})).then(result => {
              if (typeof result?.accepted === 'boolean') clearInterval(timer);
              if (!result?.accepted) notified = '';
            }, () => {notified = '';});
          } else clearInterval(timer);
        } catch { notified = ''; }
      }
      previous = signature;
    }, 1500);
    timer?.unref?.();
    const expiry = setTimeout(() => clearInterval(timer), 2 * 60 * 60 * 1000);
    expiry?.unref?.();
  }
  function watchStaffResponse() {
    const timer = setInterval(() => {
      if (!conversation.test(location.href)) return;
      const status = projectProgress().reason.match(/ChatGPT reported an upload failure: ([A-Z_]+)/);
      if (!status) return;
      clearInterval(timer);
      void chrome.runtime.sendMessage({type:'project:blocked', code:status[1]}).catch(() => {});
    }, 3500);
    setTimeout(() => clearInterval(timer), 2 * 60 * 60 * 1000);
  }
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id) return;
    if (message?.type === 'project:cancel' && (inProject() || conversation.test(location.href))) {
      cancelled = true;
      const stop = document.querySelector('[data-testid="stop-button"], button[aria-label="Stop generating"], button[aria-label="Stop streaming"], button[aria-label="Stop response"], button[aria-label="Stop"]');
      stop?.click();
      reply({stopped:true});
      return;
    }
    if (message?.type === 'project:progress' && conversation.test(location.href)) {
      reply(projectProgress());
      return;
    }
    if (!inProject()) return;
    if (message?.type === 'project:ready') {
      reply({ready:Boolean(input() && formFor(input()) && !existingTurn())});
      return;
    }
    if (message?.type !== 'project:send') return;
    send(message).then(reply, error => reply({sent:false, reason:'Companion submission error: ' + String(error?.message || error).slice(0,240)}));
    return true;
  });
  watchDesignResponse();
})();
