// Progressive enhancement over Streamlit's supported query-bound widgets.
// Modified link clicks retain the ordinary deep link/new-tab behaviour.
(() => {
  if (window.scAutomationLinks) return;
  window.scAutomationLinks = true;
  window.scAutomationIntent = 0;
  window.addEventListener('popstate',() => { window.scAutomationIntent++; });
  window.scAutomationCommitRoute = (target, push) => {
    const intent = ++window.scAutomationIntent;
    const fields = ['automation', 'automation_email'].map(key => ({
      input:document.querySelector('.st-key-' + key + ' input'), value:target.searchParams.get(key) || ''
    }));
    if (fields.some(field => !field.input)) return false;
    if (push) history.pushState({}, '', target);
    const changed = fields.filter(field => field.input.value !== field.value);
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;
    for (const field of changed) {
      setter.call(field.input, field.value);
      field.input.dispatchEvent(new Event('input', {bubbles:true}));
    }
    // Re-apply the latest values after React's event flush. A preceding native
    // widget response may replace the bound URL while this intent is pending.
    setTimeout(() => {
      if (intent !== window.scAutomationIntent) return;
      if (new URL(location.href).searchParams.get('page') !== target.searchParams.get('page')) return;
      if (location.href !== target.href) history.replaceState({},'',target);
      for (const field of fields) {
        if (!field.input.isConnected) return;
        if (field.input.value !== field.value) {
          setter.call(field.input,field.value);
          field.input.dispatchEvent(new Event('input',{bubbles:true}));
        }
      }
      setTimeout(() => {
        if (intent !== window.scAutomationIntent) return;
        for (const field of fields) if (field.input.isConnected) field.input.dispatchEvent(new FocusEvent('focusout',{bubbles:true}));
      },0);
    }, 25);
    return true;
  };
  document.addEventListener('click', event => {
    if (event.target.closest?.('[class*="st-key-sidebar-row-"] button')) window.scAutomationIntent++;
    const link = event.target.closest?.('a[data-flow-open]');
    const back = event.target.closest?.('.st-key-toolbar-back button');
    const flow = event.target.closest?.('.st-key-toolbar-sequence button');
    const button = event.target.closest?.('[class*="st-key-flow-step-"] button');
    const editKey = button && [...button.closest('[class*="st-key-flow-step-"]').classList]
      .find(key => key.startsWith('st-key-flow-step-') && key.endsWith('-edit'));
    if ((!link && !back && !flow && !editKey) || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const target = new URL(location.href);
    // A newly created or legacy in-session Flow can paint before its initial
    // query binding reaches the address bar. Its rendered identity owns Edit.
    const current = document.querySelector('[data-automation-route]')?.dataset.automationRoute;
    if ((flow || editKey) && current) target.searchParams.set('automation',current);
    if (link) { target.searchParams.set('automation',link.dataset.flowOpen); target.searchParams.delete('automation_email'); }
    else if (back) { target.searchParams.delete('automation'); target.searchParams.delete('automation_email'); }
    else if (editKey) target.searchParams.set('automation_email',editKey.slice('st-key-flow-step-'.length,-'-edit'.length));
    else target.searchParams.delete('automation_email');
    if (window.scAutomationCommitRoute(target,true)) {
      event.preventDefault();event.stopPropagation();
      if(link)link.setAttribute('aria-busy','true');
      return;
    }
    if (!link) return;
    const buttonFallback = document.querySelector('.st-key-auto-open-' + CSS.escape(link.dataset.flowOpen) + ' button');
    if (!buttonFallback || buttonFallback.disabled) return;
    event.preventDefault();link.setAttribute('aria-busy','true');buttonFallback.click();
  }, true);
})();
