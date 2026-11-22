'use strict';
(() => {
  const base = '/marketplace';
  // Never adopt implicit-flow credentials from a URL. Account confirmation is
  // followed by a password sign-in; password recovery uses server-side PKCE.
  if (location.hash.includes('access_token=') || location.hash.includes('error_description=')) {
    history.replaceState(null, '', location.pathname + location.search);
  }
  async function post(path, data) {
    const response = await fetch(base + path, {method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Please try again shortly.');
    return result;
  }
  function requestId(form, data) {
    const fingerprint = JSON.stringify(data);
    if (form.dataset.pendingPayload !== fingerprint) {
      form.dataset.pendingPayload = fingerprint;
      form.dataset.pendingId = crypto.randomUUID();
    }
    return form.dataset.pendingId;
  }
  for (const form of document.querySelectorAll('[data-account-action]')) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('button[type=submit]');
      const status = form.querySelector('.form-status');
      if (button.disabled) return;
      button.disabled = true;
      status.textContent = 'Sending…';
      status.removeAttribute('data-error');
      try {
        const data = Object.fromEntries(new FormData(form).entries());
        if (form.elements.consent) data.consent = form.elements.consent.checked;
        const action = form.dataset.accountAction;
        let endpoint = '/api/auth/' + action;
        if (action === 'start' || action === 'send') {
          data.request_id = requestId(form, data);
          endpoint = action === 'start' ? '/api/conversations' : '/api/conversations/' + data.thread_id + '/messages';
        }
        const result = await post(endpoint, data);
        if (result.redirect) { location.assign(result.redirect); return; }
        if (action === 'send') {
          form.elements.text.value = '';
          if (form.elements.amount) form.elements.amount.value = '';
          if (form.elements.url) form.elements.url.value = '';
          delete form.dataset.pendingPayload;
          status.textContent = 'Sent.';
          await poll();
        } else {
          status.textContent = result.message || 'Saved.';
          if (form.elements.password) form.elements.password.value = '';
        }
      } catch (error) {
        status.textContent = error.message || 'Please check your connection and try again.';
        status.setAttribute('data-error', 'true');
      } finally { button.disabled = false; }
    });
    const select = form.querySelector('select[name=kind]');
    if (select) {
      const update = () => {
        const paid = ['offer', 'invoice'].includes(select.value);
        for (const field of form.querySelectorAll('[data-payment-fields]')) field.hidden = !paid;
        for (const field of form.querySelectorAll('[data-invoice-fields]')) field.hidden = select.value !== 'invoice';
        form.elements.amount.required = paid;
        if (form.elements.url) form.elements.url.required = select.value === 'invoice';
        form.elements.text.required = !paid;
        form.elements.text.maxLength = paid ? 500 : 2000;
        form.elements.text.placeholder = paid ? 'Add a note (optional)…' : 'Write a message…';
      };
      select.addEventListener('change', update);
      update();
    }
  }
  const chat = document.querySelector('[data-conversation]');
  const log = chat && chat.querySelector('.message-log');
  let cursor = log ? Math.max(0, ...Array.from(log.querySelectorAll('[data-seq]'), n => Number(n.dataset.seq))) : 0;
  let pending = false;
  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }
  const fmt = value => 'A$' + (value / 100).toLocaleString('en-AU', {minimumFractionDigits: 2, maximumFractionDigits: 2});
  function append(message) {
    if (log.querySelector(`[data-seq="${message.seq}"]`)) return;
    const mine = message.sender === chat.dataset.role;
    const article = node('article', undefined, 'message ' + (mine ? 'mine' : 'theirs'));
    article.dataset.seq = String(message.seq);
    article.dataset.kind = message.kind;
    const header = node('header');
    const time = node('time', message.created_at.slice(0, 16).replace('T', ' ') + ' UTC');
    time.dateTime = message.created_at;
    header.append(node('strong', mine ? 'You' : message.sender === 'seller' ? 'Seller' : 'Buyer'), time);
    article.append(header);
    if (message.kind !== 'text') {
      const label = message.kind === 'invoice' ? 'Seller-provided PayPal invoice'
        : 'Offer ' + (message.kind === 'offer' ? message.status : message.choice);
      article.append(node('strong', label, 'message-label'), node('span', fmt(message.amount_cents) + ' AUD', 'message-amount'));
    }
    if (message.text) article.append(node('p', message.text));
    if (message.kind === 'invoice') {
      const link = node('a', 'View & pay on PayPal ↗', 'button dark');
      // The server only returns validated PayPal invoice links; check the host
      // again before creating a clickable payment destination in the browser.
      const url = new URL(message.url);
      if (url.protocol === 'https:' && url.hostname === 'www.paypal.com' && url.pathname.startsWith('/invoice/')) {
        link.href = message.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
        article.append(link);
      }
      article.append(node('small', 'Check the recipient and total on PayPal. Payment status is not tracked here.'));
    }
    if (message.kind === 'offer' && chat.dataset.role === 'seller' && message.status === 'pending') {
      const actions = node('div', undefined, 'offer-actions');
      for (const choice of ['accepted', 'declined']) {
        const button = node('button', choice === 'accepted' ? 'Accept offer' : 'Decline');
        button.type = 'button'; button.dataset.offer = String(message.seq); button.dataset.choice = choice;
        actions.append(button);
      }
      article.append(actions);
    }
    if (message.kind === 'offer_response') {
      const original = log.querySelector(`[data-seq="${message.offer_seq}"]`);
      if (original) {
        original.querySelector('.message-label').textContent = 'Offer ' + message.choice;
        const actions = original.querySelector('.offer-actions');
        if (actions) actions.remove();
      }
    }
    log.append(article);
  }
  async function poll() {
    if (!chat || pending || document.hidden) return;
    pending = true;
    const status = chat.querySelector('.chat-status');
    try {
      const response = await fetch(`${base}/api/conversations/${chat.dataset.conversation}/messages?after=${cursor}`,
        {credentials: 'same-origin', cache: 'no-store'});
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Messages are temporarily unavailable.');
      const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100;
      for (const message of result.messages) { append(message); cursor = Math.max(cursor, message.seq); }
      chat.querySelector('.message-composer').hidden = result.conversation.blocked;
      if (atBottom) log.scrollTop = log.scrollHeight;
      status.textContent = '';
      if (result.has_more) setTimeout(poll, 50);
    } catch (error) { status.textContent = error.message || 'Reconnecting… Your written message is still here.'; }
    finally { pending = false; }
  }
  if (chat) {
    log.scrollTop = log.scrollHeight;
    setInterval(poll, 6000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) poll(); });
    log.addEventListener('click', async event => {
      const button = event.target.closest('[data-offer]');
      if (!button || button.disabled) return;
      button.disabled = true;
      try {
        if (!button.dataset.requestId) button.dataset.requestId = crypto.randomUUID();
        await post(`/api/conversations/${chat.dataset.conversation}/messages`, {kind: 'offer_response',
          offer_seq: button.dataset.offer, choice: button.dataset.choice, request_id: button.dataset.requestId});
        await poll();
      } catch (error) { chat.querySelector('.chat-status').textContent = error.message; }
      finally { button.disabled = false; }
    });
    for (const button of chat.querySelectorAll('[data-safety]')) button.addEventListener('click', async () => {
      button.disabled = true;
      try { await post(`/api/conversations/${chat.dataset.conversation}/safety`, {action: button.dataset.safety}); location.reload(); }
      catch (error) { chat.querySelector('[data-safety-status]').textContent = error.message; button.disabled = false; }
    });
    const report = chat.querySelector('[data-report]');
    report.addEventListener('submit', async event => {
      event.preventDefault();
      const button = report.querySelector('button'); button.disabled = true;
      try {
        await post(`/api/conversations/${chat.dataset.conversation}/safety`, {action: 'report', reason: report.elements.reason.value});
        chat.querySelector('[data-safety-status]').textContent = 'Report saved for Sports Cave to review.';
      } catch (error) { chat.querySelector('[data-safety-status]').textContent = error.message; }
      finally { button.disabled = false; }
    });
    poll();
  }
})();
