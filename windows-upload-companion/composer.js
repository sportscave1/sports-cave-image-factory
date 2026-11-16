(() => {
  'use strict';
  const project = 'https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project';
  const conversation = /^https:\/\/chatgpt\.com\/g\/g-p-6a387a17627081918e1700ec2783a12b(?:-sc-mockups-uploads)?\/c\/[a-f0-9-]{36}$/;
  const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
  // Block wrappers created by Edge can add a visual blank line to innerText.
  const normalize = text => text.replace(/\r\n?/g, '\n').replace(/\u00a0/g, ' ')
    .replace(/\n{3,}/g, '\n\n').trimEnd();
  let busy = false;
  const inProject = () => location.href === project;
  const workEditor = '[role="textbox"][contenteditable="true"][aria-label="New chat in SC Mockups/Uploads"]';
  const input = () => document.querySelector(workEditor) || document.querySelector('#prompt-textarea[contenteditable="true"]');
  const formFor = node => node?.closest('form');
  const sendButton = form => form?.querySelector('button[data-testid="send-button"], button[type="submit"][aria-label="Send"]');
  const existingTurn = () => document.querySelector('[data-message-author-role="user"], [data-message-author-role="assistant"], h4[data-conversation-role="user"], h4[data-conversation-role="assistant"]');
  const attachments = form => Array.from(form?.querySelectorAll('button[aria-label^="Remove file"], button[aria-label^="Remove image"], button[aria-label="Remove pasted text attachment"], button[data-testid*="attachment"]') || []);
  const pastedText = 'Remove pasted text attachment';
  async function waitFor(check, ms) {
    const end = Date.now() + ms;
    do {
      const value = check();
      if (value) return value;
      await delay(150);
    } while (Date.now() < end);
    return null;
  }
  async function fill(node, form, prompt) {
    // Work turns long pastes into a text attachment, just like Ctrl+V.
    if (node.matches(workEditor)) {
      const data = new DataTransfer();
      data.setData('text/plain', prompt);
      node.dispatchEvent(new ClipboardEvent('paste', {clipboardData:data, bubbles:true, cancelable:true}));
      const pasted = await waitFor(() => node.innerText.trim() || attachments(form).length, 1200);
      if (pasted) return;
    }
    if (inProject() && document.activeElement === node && !node.innerText.trim() && !attachments(form).length) {
      document.execCommand('insertText', false, prompt);
    }
  }

  function submittedPrompt(prompt, sentAsAttachment) {
    if (!inProject() && !conversation.test(location.href)) return false;
    const workTurns = Array.from(document.querySelectorAll('h4[data-conversation-role="user"]'));
    if (sentAsAttachment) {
      return conversation.test(location.href) && workTurns.length === 1 &&
        !!workTurns[0].nextElementSibling?.querySelector('button[aria-label^="Pasted text("]');
    }
    const bodies = [...workTurns.map(turn => turn.nextElementSibling),
      ...Array.from(document.querySelectorAll('[data-message-author-role="user"]'),
        turn => turn.querySelector('.whitespace-pre-wrap') || turn)];
    return bodies.some(body => body && normalize(body.innerText) === normalize(prompt));
  }
  async function send({id, prompt}) {
    if (!inProject() || busy || typeof prompt !== 'string') return {sent:false};
    busy = true;
    try {
      const node = await waitFor(() => inProject() && input(), 7500);
      const form = formFor(node);
      if (!node || !form || existingTurn() || attachments(form).length || node.innerText.trim()) return {sent:false};

      node.focus();
      if (!inProject() || document.activeElement !== node || node.innerText.trim()) return {sent:false};
      await fill(node, form, prompt);
      const promptText = normalize(prompt);
      const isWork = node.matches(workEditor);
      const previewText = promptText.replace(/\s+/g, ' ');
      const ready = () => {
        if (!inProject() || existingTurn()) return null;
        // Work can replace the composer while it uploads a pasted attachment.
        const editor = input();
        if (!editor || editor.matches(workEditor) !== isWork) return null;
        const composer = formFor(editor);
        const button = sendButton(composer);
        if (!button?.isConnected || button.disabled || button.getAttribute('aria-disabled') === 'true') return null;
        const files = attachments(composer);
        if (!files.length && normalize(editor.innerText) === promptText) return {button, asAttachment:false};
        if (!isWork || editor.innerText.trim() || files.length !== 1 ||
          files[0].getAttribute('aria-label') !== pastedText) return null;
        const preview = files[0].parentElement?.querySelector('button[aria-label]:not([aria-label="Remove pasted text attachment"])');
        const prefix = preview?.getAttribute('aria-label')?.replace(/…$/, '');
        if (!prefix || prefix.length < 32 || !previewText.startsWith(prefix.replace(/\s+/g, ' ').trimEnd())) return null;
        return {button, asAttachment:true};
      };
      // Long Work pastes upload before Send is enabled.
      if (!await waitFor(ready, isWork ? 25000 : 4500)) {
        return {sent:false, reason:'ChatGPT did not make the pasted prompt ready to send.'};
      }
      const permission = await chrome.runtime.sendMessage({type:'project:permit', id});
      const current = ready();
      if (!permission?.ok || !current) return {sent:false};
      const {button, asAttachment:sentAsAttachment} = current;
      button.click();
      const accepted = await waitFor(() => submittedPrompt(prompt, sentAsAttachment), 12000);
      if (accepted && prompt.includes('SC_UPLOAD_BLOCKED: REFERENCE')) watchStaffResponse();
      return {sent:Boolean(accepted)};
    } finally {
      busy = false;
    }
  }
  function watchStaffResponse() {
    const timer = setInterval(() => {
      if (!conversation.test(location.href)) return;
      const turns = document.querySelectorAll('[data-message-author-role="assistant"], h4[data-conversation-role="assistant"]');
      const last = turns[turns.length - 1];
      const body = last?.matches('h4') ? last.nextElementSibling : last;
      if (!body || document.querySelector('[data-testid="stop-button"], button[aria-label="Stop generating"]')) return;
      const status = body.innerText.trim().match(/(?:^|\n)SC_UPLOAD_BLOCKED: ([A-Z_]+)\s*$/);
      if (!status) return;
      clearInterval(timer);
      void chrome.runtime.sendMessage({type:'project:blocked', code:status[1]}).catch(() => {});
    }, 3500);
    setTimeout(() => clearInterval(timer), 2 * 60 * 60 * 1000);
  }
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id || !inProject()) return;
    if (message?.type === 'project:ready') {
      reply({ready:Boolean(input() && formFor(input()) && !existingTurn())});
      return;
    }
    if (message?.type !== 'project:send') return;
    send(message).then(reply, () => reply({sent:false}));
    return true;
  });
})();
