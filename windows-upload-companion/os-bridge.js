(() => {
  'use strict';
  const channel = 'sports-cave-upload-companion-v1';
  if (window === top) return;
  try { if (top.location.origin !== location.origin) return; }
  catch { return; }

  window.addEventListener('message', async event => {
    const message = event.data;
    if (event.source !== window || event.origin !== location.origin ||
        message?.channel !== channel || message.direction !== 'request' ||
        !['health', 'start', 'pair', 'wake'].includes(message.action)) return;
    const frame = window.frameElement;
    if (!frame || (message.action === 'start' && frame.id !== 'sc-product-upload-copy') ||
        (message.action === 'pair' && frame.id !== 'sc-upload-companion-health') ||
        (message.action === 'wake' && frame.id !== 'sc-upload-queue-wake')) return;
    let result;
    try {
      result = await chrome.runtime.sendMessage({
        type: 'os:' + message.action, receipt: message.receipt, prompt: message.prompt,
        staffJob: message.staffJob, token: message.token, reference:message.reference,
      });
    } catch { return; }
    window.postMessage({channel, direction: 'response', id: message.id, result}, location.origin);
  });
})();
