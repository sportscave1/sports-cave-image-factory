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
  const input = () => document.querySelector('#prompt-textarea[contenteditable="true"]');
  const formFor = node => node?.closest('form');
  const sendButton = form => form?.querySelector('button[data-testid="send-button"]');
  const existingTurn = () => document.querySelector('[data-message-author-role="user"], [data-message-author-role="assistant"]');
  const hasAttachment = form => form?.querySelector('[aria-label^="Remove file"], [aria-label^="Remove image"], [data-testid*="attachment"]');
  async function waitFor(check, ms) {
    const end = Date.now() + ms;
    do {
      const value = check();
      if (value) return value;
      await delay(150);
    } while (Date.now() < end);
    return null;
  }
  async function send({id, prompt}) {
    if (!inProject() || busy || typeof prompt !== 'string') return {sent:false};
    busy = true;
    try {
      const node = await waitFor(() => inProject() && input(), 7500);
      const form = formFor(node);
      if (!node || !form || existingTurn() || hasAttachment(form) || node.innerText.trim()) return {sent:false};

      // Edge's editing command makes the same DOM input update as pasting text,
      // without reading or replacing the user's system clipboard.
      node.focus();
      if (!inProject() || document.activeElement !== node || node.innerText.trim()) return {sent:false};
      if (!document.execCommand('insertText', false, prompt)) return {sent:false};
      const exact = () => inProject() && input() === node && !existingTurn() && !hasAttachment(form) &&
        normalize(node.innerText) === normalize(prompt);
      const ready = () => {
        const button = sendButton(form);
        return exact() && button?.isConnected && !button.disabled &&
          button.getAttribute('aria-disabled') !== 'true' && button;
      };
      const button = await waitFor(ready, 4500);
      if (!button) return {sent:false};
      const permission = await chrome.runtime.sendMessage({type:'project:permit', id});
      if (!permission?.ok || ready() !== button) return {sent:false};
      button.click();

      const accepted = await waitFor(() => {
        if (!inProject() && !conversation.test(location.href)) return false;
        return Array.from(document.querySelectorAll('[data-message-author-role="user"]'))
          .some(turn => normalize((turn.querySelector('.whitespace-pre-wrap') || turn).innerText) === normalize(prompt));
      }, 12000);
      return {sent:Boolean(accepted)};
    } finally {
      busy = false;
    }
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
