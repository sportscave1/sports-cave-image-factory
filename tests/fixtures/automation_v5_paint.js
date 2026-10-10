// Measurement only: no application events, layout changes or network calls.
window.v5Click = performance.now();
window.v5Paints = {};
const visible = element => element && element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden';
document.addEventListener('click', event => {
  if (!event.isTrusted) return;
  window.v5Click = performance.now();
  sessionStorage.setItem('v5-click-absolute', String(Date.now()));
  window.v5Paints = {};
  window.v5Feedback = null;
  const link = event.target.closest?.('a[data-flow-open]');
  window.v5FeedbackTarget = link || event.target.closest?.('.st-key-sidebar-row-crm_automations_manage button');
  if (link) requestAnimationFrame(() => { if (link.getAttribute('aria-busy') === 'true') window.v5Feedback = performance.now() - window.v5Click; });
  if (event.target.closest?.('.st-key-sidebar-row-crm_automations_manage')) requestAnimationFrame(() => {
    if (document.body.classList.contains('sc-navigation-pending')) window.v5Feedback = performance.now() - window.v5Click;
  });
}, true);
const sample = () => {
  if (window.v5Feedback === null && window.v5FeedbackTarget?.isConnected
      && (window.v5FeedbackTarget.getAttribute('aria-busy') === 'true'
          || window.v5FeedbackTarget.dataset.scAutomationPending === 'true')) window.v5Feedback = performance.now() - window.v5Click;
  const elapsed = Date.now() - Number(sessionStorage.getItem('v5-click-absolute') || Date.now());
  const kind = sessionStorage.getItem('v5-expected-view');
  if (elapsed < 10000) {
    let shell, first, all, optional;
    const route = document.querySelector('[data-automation-route]');
    const url = new URL(location.href);
    if (route && route.dataset.automationRoute === (url.searchParams.get('automation') || '')
        && route.dataset.automationEmail === (url.searchParams.get('automation_email') || '')
        && window.v5Paints.accepted === undefined) window.v5Paints.accepted = elapsed;
    if (kind === 'overview') {
      shell = document.querySelector('.st-key-crm-campaign-home h1');
      first = document.querySelector('.sc-auto-row');
      all = first && document.querySelector('input[aria-label="Search automations"]');
      optional = all && document.querySelectorAll('.sc-auto-kpi').length === 6 && !document.querySelector('.sc-home-unresolved');
    } else if (kind === 'flow') {
      first = document.querySelector('[class*="st-key-flow-row-"]');
      shell = document.querySelector('.sc-auto-editor-loading') || first;
      const buttons = [...document.querySelectorAll('.st-key-flow-workspace button')].filter(b => b.textContent.trim() === 'Edit Email');
      all = first && buttons.length >= Number(sessionStorage.getItem('v5-stages') || 1);
      optional = all && [...document.querySelectorAll('.sc-flow-metrics')].every(e => ['READY','ERROR','TIMED_OUT'].includes(e.dataset.phase));
    } else if (kind === 'editor') {
      shell = document.querySelector('.st-key-crm-composer-controls');
      first = document.querySelector('input[aria-label="Subject"]');
      all = first; optional = all;
    }
    for (const [name, element] of Object.entries({shell, first, all, optional})) {
      if (window.v5Paints[name] === undefined && (element === true || visible(element))) window.v5Paints[name] = elapsed;
    }
  }
  requestAnimationFrame(sample);
};
requestAnimationFrame(sample);
