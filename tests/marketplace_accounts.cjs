// Exercise actual account form behavior without a browser, server or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const source = fs.readFileSync(require('node:path').join(__dirname, '../static/marketplace/marketplace-accounts.js'), 'utf8');

function fixture(action, values, selectValue) {
  const status = {textContent: '', setAttribute() {}, removeAttribute() {}};
  const button = {disabled: false};
  const events = {};
  const elements = Object.fromEntries(Object.entries(values).map(([name, value]) => [name, {value}]));
  const paymentFields = {hidden: true}, invoiceFields = {hidden: true};
  const select = selectValue ? {value: selectValue, addEventListener(name, fn) { this[name] = fn; }} : null;
  const form = {dataset: {accountAction: action}, elements, addEventListener(name, fn) { events[name] = fn; },
    querySelector(selector) {
      if (selector === 'button[type=submit]') return button;
      if (selector === '.form-status') return status;
      if (selector === 'select[name=kind]') return select;
      throw new Error('Unexpected form query ' + selector);
    }, querySelectorAll(selector) { return selector === '[data-payment-fields]' ? [paymentFields] : [invoiceFields]; }};
  const calls = [], redirects = [], historyCalls = [];
  let reply = {ok: true, redirect: '/marketplace/inbox'};
  const context = {crypto, URL, setTimeout,
    location: {hash: '#access_token=discard-this', pathname: '/marketplace/account/confirmed', search: '', assign(value) { redirects.push(value); }},
    history: {replaceState(...args) { historyCalls.push(args); }},
    document: {querySelectorAll() { return [form]; }, querySelector() { return null; }},
    FormData: class { constructor() { this.values = Object.entries(elements).map(([k, v]) => [k, v.value]); } entries() { return this.values; } },
    fetch: async (url, options) => { calls.push({url, options}); return {ok: reply.ok, json: async () => reply}; }};
  vm.runInNewContext(source, context);
  return {form, select, elements, paymentFields, invoiceFields, calls, redirects, historyCalls, status,
    reply(value) { reply = value; }, submit() { return events.submit({preventDefault() {}}); }};
}

(async () => {
  const signin = fixture('signin', {email: 'buyer@example.invalid', password: 'synthetic password', next: '/marketplace/contact/demo?intent=offer'});
  await signin.submit();
  assert.equal(signin.calls[0].url, '/marketplace/api/auth/signin');
  assert.equal(signin.calls[0].options.credentials, 'same-origin');
  assert.equal(JSON.parse(signin.calls[0].options.body).next, '/marketplace/contact/demo?intent=offer');
  assert.equal(signin.historyCalls.length, 1);
  assert.equal(signin.historyCalls[0][2], '/marketplace/account/confirmed');
  assert.deepEqual(signin.redirects, ['/marketplace/inbox']);

  const contact = fixture('start', {listing_id: 'synthetic-item', kind: 'text', text: 'Is it available?'});
  contact.reply({ok: false, error: 'Temporary failure'});
  await contact.submit();
  assert.equal(contact.status.textContent, 'Temporary failure');
  const firstId = JSON.parse(contact.calls[0].options.body).request_id;
  contact.reply({ok: true, redirect: '/marketplace/inbox/synthetic-thread'});
  await contact.submit();
  assert.equal(JSON.parse(contact.calls[1].options.body).request_id, firstId);
  assert.equal(contact.calls[1].url, '/marketplace/api/conversations');
  contact.elements.text.value = 'A different question';
  await contact.submit();
  assert.notEqual(JSON.parse(contact.calls[2].options.body).request_id, firstId);

  const seller = fixture('send', {thread_id: 'thread', kind: 'text', text: '', amount: '', url: ''}, 'text');
  assert.equal(seller.elements.amount.required, false);
  assert.equal(seller.elements.url.required, false);
  seller.select.value = 'invoice'; seller.select.change();
  assert.equal(seller.paymentFields.hidden, false);
  assert.equal(seller.invoiceFields.hidden, false);
  assert.equal(seller.elements.amount.required, true);
  assert.equal(seller.elements.url.required, true);
  assert.equal(seller.elements.text.required, false);
  seller.select.value = 'text'; seller.select.change();
  assert.equal(seller.invoiceFields.hidden, true);
  assert.equal(seller.elements.url.required, false);
  assert.equal(seller.elements.text.required, true);
  const preference = fixture('notifications', {email_notifications: 'on'});
  preference.elements.email_notifications.checked = false;
  preference.reply({ok: true, message: 'Email preference saved.'});
  await preference.submit();
  assert.equal(preference.calls[0].url, '/marketplace/api/auth/notifications');
  assert.equal(JSON.parse(preference.calls[0].options.body).email_notifications, false);
  preference.elements.email_notifications.checked = true;
  await preference.submit();
  assert.equal(JSON.parse(preference.calls[1].options.body).email_notifications, true);
  console.log('Accounts: secure form requests, confirmation cleanup, retry deduplication and invoice fields passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
