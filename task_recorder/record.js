(() => {
  if (window.__scRecorder) return;
  const privateName = /password|passwd|secret|token|authorization|session|credential|one.?time|verification.?code|otp|csrf|api.?key/i;
  const token = /Bearer\s+\S+|eyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+|(?:sk-|ghp_|xoxb-)[A-Za-z0-9_-]{10,}|[A-Za-z0-9_+/=-]{64,}/i;
  const authURL = /(?:login|log-in|signin|sign-in|oauth|authorize|authentication|\/auth(?:\/|$))/i;
  const visible = e => !!(e.getBoundingClientRect().width && e.getBoundingClientRect().height);
  const sensitive = () => authURL.test(location.pathname) ||
    [...document.querySelectorAll('input')].some(e => visible(e) &&
      (e.type === 'password' || /username|current-password|new-password|one-time-code/.test(e.autocomplete) ||
       privateName.test([e.name,e.id,e.getAttribute('aria-label'),...(e.labels || [])].join(' '))));
  let active = false, pending = null;
  function badge() {
    if (!document.body || document.getElementById('__scRecorderBadge')) return;
    const mark=document.createElement('div');mark.id='__scRecorderBadge';
    mark.textContent='Sports Cave recorder browser';
    mark.style.cssText='position:fixed;right:8px;top:8px;z-index:2147483647;background:#172c43;color:white;padding:5px 9px;border-radius:4px;font:12px system-ui;pointer-events:none';
    document.body.append(mark);
  }
  if(document.body)badge();else document.addEventListener('DOMContentLoaded',badge,{once:true});
  const send = data => window.__scRecord(data).catch(() => {});
  const privacy = () => { if (active && sensitive()) { active = false; pending = null; send({kind:'privacy'}); return true; } return !active; };
  const unsupported = code => send({kind:'unsupported', code});
  const clean = t => typeof t === 'string' && t.trim().length <= 180 && !privateName.test(t) && !token.test(t);
  function locator(e) {
    const label = e.getAttribute('aria-label') || (e.labels && e.labels[0]?.textContent.trim());
    if (label && clean(label)) return {by:'label', value:label};
    const testId = e.getAttribute('data-testid');
    if (testId && clean(testId)) return {by:'test_id', value:testId};
    const roles = {BUTTON:'button', A:'link', SELECT:'combobox', TEXTAREA:'textbox'};
    const role = e.getAttribute('role') || roles[e.tagName];
    const name = e.getAttribute('aria-label') || e.innerText?.trim();
    if (['button','link','tab','menuitem','heading','option'].includes(role) && name && clean(name))
      return {by:'role', role, value:name};
    if (e.id && clean(e.id)) return {by:'id', value:e.id};
    const placeholder = e.getAttribute('placeholder');
    if (placeholder && clean(placeholder)) return {by:'placeholder', value:placeholder};
    return null;
  }
  function capture(e) {
    if (privacy()) return;
    if (!(e instanceof Element)) return;
    if (privateName.test([e.name,e.id,e.getAttribute('aria-label')].join(' ')) ||
        e.type === 'password' || token.test(e.value || '')) {
      active = false; pending = null; send({kind:'privacy'}); return;
    }
    const loc = locator(e);
    if (!loc) { unsupported('field_target'); return; }
    if (e.type === 'file') {
      if (e.files?.length !== 1) unsupported('multiple_files');
      else return send({kind:'step', step:{action:'upload', locator:loc}});
    } else if (e.tagName === 'SELECT') {
      if (e.multiple) unsupported('multiple_selection');
      else return send({kind:'step', step:{action:'select', locator:loc, value:e.value}});
    } else if (['checkbox','radio'].includes(e.type)) {
      return send({kind:'step', step:{action:'check', locator:loc, value:e.checked}});
    } else if (e.matches('input,textarea')) {
      return send({kind:'step', step:{action:'fill', locator:loc, value:e.value}});
    } else if (e.isContentEditable) unsupported('rich_text');
  }
  function flush() { if (pending) { const e = pending; pending = null; return capture(e); } }
  window.__scRecorder = {
    set: value => { active = value; pending = null; privacy(); },
    flush,
    sensitive,
    locator
  };
  send({kind:'ready'});
  document.addEventListener('input', ev => { if (!privacy()) pending = ev.target; }, true);
  document.addEventListener('change', ev => { if(pending && pending !== ev.target) flush(); pending = null; capture(ev.target); }, true);
  document.addEventListener('click', ev => {
    if (privacy()) return;
    flush();
    const raw = ev.composedPath()[0];
    if (!(raw instanceof Element)) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey || ev.shiftKey) { unsupported('modified_click'); return; }
    if (raw.closest('canvas,[contenteditable=true]') || (raw.closest('svg') && !raw.closest('button,a,[role=button]'))) { unsupported('rich_edit'); return; }
    if (raw.matches('input,textarea,select,option') || raw.closest('label')?.querySelector('input')) return;
    const e = raw.closest('button,a,[role=button],[role=tab],[role=menuitem]') || raw;
    if (e.matches('a[target=_blank]')) { unsupported('new_tab'); return; }
    const loc = locator(e);
    if (!loc) { unsupported('click_target'); return; }
    send({kind:'step', step:{action:'click',locator:loc}});
  }, true);
  document.addEventListener('keydown', ev => {
    if (privacy()) return;
    if (ev.key === 'Enter' && ev.target.matches('input,textarea')) { flush(); unsupported('enter_submit'); }
    else if ((ev.ctrlKey || ev.metaKey) && !['a','c','v','x'].includes(ev.key.toLowerCase()))
      unsupported('shortcut');
  }, true);
  for (const event of ['dblclick','contextmenu','dragstart','drop']) {
    document.addEventListener(event, () => { if (!privacy()) unsupported('pointer_gesture'); }, true);
  }
  new MutationObserver(() => privacy()).observe(document, {childList:true, subtree:true, attributes:true, attributeFilter:['type','autocomplete']});
})();
