/* Local accessibility projection for Streamlit's Base Web single select.
 * No input recording, event injection, application state writes or network.
 * Virtual-menu overrides omit listbox identity and leave aria-controls dangling.
 * Bind only the unique new menu in a single observed expansion transaction.
 */
(() => {
  'use strict';
  const prefix = 'Sports Cave Edge select v1: ';
  const groupMarker = 'Sports Cave Edge select owner v1';
  const privateName = /password|passwd|credential|secret|token|authorization|one.?time|otp|api.?key/i;
  const credential = /Bearer\s+\S+|eyJ[\w-]{12,}\.[\w-]+|(?:sk-|ghp_|xoxb-)[\w-]{10,}/i;
  const states = new WeakMap();
  let menusBefore = new Set(), active = null, nextId = 0, scheduled = false;
  const clean = value => typeof value === 'string' && value.length <= 180 && !privateName.test(value) && !credential.test(value);
  const visible = node => node.isConnected && node.getBoundingClientRect().width > 0 && node.getBoundingClientRect().height > 0;
  const menus = () => [...document.querySelectorAll('[data-baseweb="popover"] ul[data-testid="stSelectboxVirtualDropdown"]')].filter(visible);
  const put = (node, key, value) => { if (node.getAttribute(key) !== value) node.setAttribute(key, value); };
  const labelOf = combo => combo.closest('[data-testid="stSelectbox"]')?.querySelector('label')?.textContent.trim() || combo.getAttribute('aria-label') || '';
  function safe(combo) {
    return combo instanceof HTMLInputElement && combo.type !== 'password' && !combo.disabled &&
      !/password|one-time-code|username/.test(combo.autocomplete) && clean(labelOf(combo)) && labelOf(combo).length > 0 &&
      clean(combo.name) && clean(combo.id) && !/login|signin|oauth|authorize|\/auth(?:\/|$)/i.test(location.pathname);
  }
  function sync() {
    scheduled = false;
    const widgets = [...document.querySelectorAll('[data-testid="stSelectbox"] [data-baseweb="select"]')];
    const owners = [];
    if (widgets.length > 64) return;
    for (const widget of widgets) {
      const matches = widget.querySelectorAll('input[role="combobox"]');
      if (matches.length !== 1 || !safe(matches[0])) continue;
      const combo = matches[0], label = labelOf(combo);
      if (document.querySelectorAll('input[role="combobox"]').length > 64) continue;
      if ([...document.querySelectorAll('input[role="combobox"]')].filter(c => labelOf(c) === label).length !== 1) continue;
      // This component has one display sibling beside the search-input wrapper.
      // The search input's value is deliberately never read.
      const display = [...combo.parentElement.parentElement.children].filter(e => !e.contains(combo) && e.tagName === 'DIV');
      if (display.length !== 1) continue;
      const selected = display[0].textContent.trim();
      if (!clean(selected)) continue;
      let state = states.get(combo);
      const expanded = combo.getAttribute('aria-expanded') === 'true';
      if (!state) {
        state = {expanded, description: combo.getAttribute('aria-description') || '', title: combo.getAttribute('title') || '', menu: null};
        states.set(combo, state);
      } else if (!state.expanded && expanded) {
        active = {combo, before: new Set(menusBefore)};
      }
      state.expanded = expanded;
      if (!expanded && active?.combo === combo) active = null;
      if (!clean(state.description)) continue;
      if (!clean(state.title)) continue;
      // Current Streamlit includes the selection in aria-label. Keep the
      // visible field label stable while the projected selected value changes.
      put(combo, 'aria-label', label);
      put(widget, 'role', 'group');
      put(widget, 'aria-label', label + ' selection');
      put(widget, 'aria-description', groupMarker);
      // Chromium's Windows provider exposes title as UIA HelpText; versions
      // that expose aria-description only through FullDescription need this.
      if (!widget.getAttribute('title') || widget.getAttribute('title') === groupMarker) put(widget, 'title', groupMarker);
      put(combo, 'aria-description', (state.description ? state.description + '\n' : '') + prefix + encodeURIComponent(selected));
      put(combo, 'title', (state.title ? state.title + '\n' : '') + prefix + encodeURIComponent(selected));
      owners.push(combo);
    }
    const currentMenus = menus();
    const expanded = owners.filter(c => c.getAttribute('aria-expanded') === 'true');
    if (active && active.combo.isConnected && expanded.length === 1 && expanded[0] === active.combo) {
      const state = states.get(active.combo);
      const candidates = currentMenus.filter(menu => menu === state.menu || !active.before.has(menu));
      if (candidates.length === 1 && candidates[0].querySelector('[role="option"]')) {
        const menu = candidates[0];
        if (!menu.id) put(menu, 'id', 'sc-recorder-options-' + (++nextId));
        // Preserve a real existing relationship; refuse conflicting ownership.
        const controlled = document.getElementById(active.combo.getAttribute('aria-controls'));
        if (!controlled || controlled === menu) {
          put(menu, 'role', 'listbox');
          put(menu, 'aria-label', labelOf(active.combo) + ' choices');
          put(menu, 'title', 'Sports Cave Edge select menu v1: ' + encodeURIComponent(labelOf(active.combo)));
          put(menu, 'aria-multiselectable', 'false');
          put(active.combo, 'aria-controls', menu.id);
          state.menu = menu;
        }
      }
    }
    menusBefore = new Set(currentMenus);
  }
  function schedule() { if (!scheduled) { scheduled = true; queueMicrotask(sync); } }
  new MutationObserver(schedule).observe(document, {subtree:true,childList:true,characterData:true,attributes:true,
    attributeFilter:['aria-expanded','aria-controls','aria-label','disabled','type','autocomplete','aria-selected']});
  sync();
})();
