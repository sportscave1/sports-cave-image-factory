/* Customer quiz. All shopper and catalogue text is rendered through textContent. */
(() => {
  'use strict';
  const title = 'Find your next edition';
  const key = value => String(value || '').normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
    .toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

  function searchScore(term, value, typo = false) {
    const label = key(value);
    if (!term || !label) return 0;
    if (label === term) return 5;
    if (label.startsWith(term)) return 4;
    if (label.split(' ').some(word => word.startsWith(term))) return 3;
    if (term.length > 2 && label.includes(term)) return 2;
    if (!typo || term.length < 4 || Math.abs(label.length - term.length) > 1) return 0;
    const mismatch = [...term].findIndex((letter, i) => letter !== label[i]);
    if (term.length === label.length) {
      return term.slice(mismatch + 1) === label.slice(mismatch + 1)
        || term[mismatch] === label[mismatch + 1] && term[mismatch + 1] === label[mismatch]
          && term.slice(mismatch + 2) === label.slice(mismatch + 2) ? 1 : 0;
    }
    const [shorter, longer] = term.length < label.length ? [term, label] : [label, term];
    return mismatch < 0 || shorter.slice(mismatch) === longer.slice(mismatch + 1) ? 1 : 0;
  }

  function subjectScore(product, subject) {
    const term = key(subject);
    if (!term) return 0;
    const contains = value => (' ' + key(value) + ' ').includes(' ' + term + ' ');
    const labels = [...product.subjects, ...(product.keywords || [])];
    if (labels.some(value => key(value) === term)) return 3;
    if (labels.some(contains)) return 2;
    return contains(product.title) ? 1 : 0;
  }

  function ranked(products, answers, rules) {
    const sports = answers.sports || [];
    const subjects = answers.subjects || {};
    const preference = answers.preference || '';
    const rows = [];
    for (const product of new Map(products.map(p => [p.id, p])).values()) {
      const scopes = sports.filter(sport => product.sports.includes(sport));
      if (sports.length && !scopes.length) continue;
      const scores = scopes.map(sport => subjectScore(product, subjects[sport]));
      const score = Math.max(0, ...scores);
      if (!rules.allow_broader && !score && scopes.length && scopes.every(sport => subjects[sport])) continue;
      const preferred = product.preferences.some(value => key(value) === key(preference));
      if (!rules.allow_broader && preference && preference !== 'lowest' && !preferred) continue;
      rows.push({product, score, preferred});
    }
    return rows.sort((a, b) =>
      b.score - a.score || Number(b.preferred) - Number(a.preferred)
      || (preference === 'lowest' ? (a.product.next_number ?? Infinity) - (b.product.next_number ?? Infinity) : 0)
      || (b.product.featured || 0) - (a.product.featured || 0)
      || Number(Boolean(b.product.next_number)) - Number(Boolean(a.product.next_number))
      || a.product.id.localeCompare(b.product.id, 'en', {numeric: true})
    ).map(row => row.product);
  }

  const teamSports = new Set(['Baseball','Basketball','Cricket','Football','Ice Hockey','NFL','Rugby League','Rugby Union','AFL']);
  const driving = new Set(['Formula One','Motorsport','NASCAR','V8 Supercars','Rally','Rally Raid','IndyCar','Sports Car Racing','Karting','Drag Racing']);
  const riding = new Set(['MotoGP','Motocross','Motorcycle Road Racing','Superbike','Enduro','Speedway','Motorcycle Endurance','Supermoto']);

  function subjectPrompt(sport) {
    if (teamSports.has(sport)) return 'Which team do you support?';
    if (driving.has(sport)) return 'Which driver or team do you support?';
    if (riding.has(sport)) return 'Which rider or team do you support?';
    if (sport === 'Horse Racing') return 'Which horse or jockey do you follow?';
    if (sport === 'Combat') return 'Which fighter do you follow?';
    if (sport === 'WWE') return 'Which wrestler do you follow?';
    if (['Tennis','Darts','Golf'].includes(sport)) return 'Which player do you follow?';
    return 'Who do you follow?';
  }

  window.SportsCaveQuizRuntime = {ranked, async mount({host, shadow, base, mode, launcher, manifest, config, preview}) {
    const json = async (url, commerce = false, signal = AbortSignal.timeout(10000)) => {
      const response = await fetch(url, {credentials: commerce ? 'same-origin' : 'omit', cache: 'no-cache', signal});
      if (!response.ok) throw Object.assign(Error('Unavailable'), {status: response.status});
      return response.json();
    };
    async function currentCatalogue() {
      const index = preview?.catalogue || await json(base + 'catalogue.json');
      if (!index.sports || !preview && !(Date.now() - Date.parse(index.generated_at) <= 7200000)) throw Error('Catalogue unavailable');
      return index;
    }
    const catalogue = await currentCatalogue();
    const collections = {...catalogue.collections, ...config.collections};
    const sportOptions = {...Object.fromEntries(Object.keys(catalogue.sports).map(sport => [sport, []])), ...catalogue.sport_options};
    const context = collections[host.dataset.collection];
    const root = window.Shopify?.routes?.root || '/';
    const session = crypto.randomUUID();
    const source = mode === 'button' ? 'collection' : (/[?&]utm_(?:source|campaign)=/.test(location.search) ? 'campaign' : 'page');
    const fresh = () => ({step: 'sport', sports: [], subjects: {}, subjectIndex: 0, preference: '', input: context && Object.hasOwn(sportOptions, context) ? context : '', missing: false});
    const history = [];
    let state = fresh(), generation = 0;
    const shardRequests = new Map();

    function event(type, question = '', product = '') {
      if (preview || !manifest.analytics_endpoint || window.Shopify?.customerPrivacy?.analyticsProcessingAllowed?.() !== true) return;
      const payload = {event_id: crypto.randomUUID(), session_id: session, version: manifest.version, type, step: question, source, product_id: product};
      fetch(manifest.analytics_endpoint, {method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload), credentials: 'omit', keepalive: true}).catch(() => {});
    }

    const el = (tag, text, props = {}) => {
      const node = document.createElement(tag);
      if (text !== undefined) node.textContent = text;
      return Object.assign(node, props);
    };
    const css = el('style');
    css.textContent = `
      :host{--gold:${config.appearance.accent};--bg:${config.appearance.background};--ink:${config.appearance.text};display:block;color:var(--ink);font:15px/1.45 system-ui,sans-serif}
      *{box-sizing:border-box}
      dialog,.inline{color:var(--ink);background:var(--bg);border:1px solid #514330;border-radius:14px;padding:clamp(16px,4vw,24px);width:min(430px,calc(100% - 24px));max-height:calc(100dvh - 28px);overflow:auto;margin:auto}
      dialog::backdrop{background:#000b}.inline{width:100%;max-height:none;margin:16px auto}
      header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:12px;border-bottom:1px solid #373127}
      h1,h2{font:500 27px/1.15 Georgia,serif;margin:0}h2{font-size:22px;margin:16px 0 12px}
      p{color:#cdc5b9;margin:0 0 12px}.context{color:var(--gold);font-size:13px;margin:14px 0 -9px}
      button,a,input{font:inherit}button,a.action{min-height:42px;border:1px solid #615136;border-radius:7px;padding:8px 13px;color:var(--ink);background:#181716;cursor:pointer;text-decoration:none}
      button:hover,a.action:hover{border-color:var(--gold);background:#28231c}
      button:focus-visible,a:focus-visible,input:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
      .close{min-width:42px;padding:0;font-size:21px}
      .primary,.action.primary{color:#17130c;background:var(--gold);border-color:var(--gold);font-weight:650}
      .primary:hover,.action.primary:hover{color:var(--ink);background:#28231c}
      .actions,.navigation{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
      .navigation button,.quiet{background:transparent;border-color:transparent;padding-inline:5px;color:#cdc5b9}
      input{width:100%;min-height:44px;background:#161615;border:1px solid #615136;color:var(--ink);padding:8px 11px;border-radius:7px;font-size:16px}
      .suggestions{list-style:none;margin:5px 0 0;padding:3px;max-height:148px;overflow:auto;border:1px solid #514330;border-radius:7px;background:#161615}
      [hidden]{display:none!important}.suggestions li{padding:8px 10px;cursor:pointer;border-radius:4px}
      .suggestions li[aria-selected=true],.suggestions li:hover{background:#33291c;color:var(--ink)}
      .hint{font-size:13px;margin:6px 0 0}.card{display:grid;grid-template-columns:minmax(0,108px) minmax(0,1fr);gap:12px;align-items:start}
      .card img{width:100%;height:auto;max-height:145px;object-fit:contain;background:#171615;border-radius:5px}
      .card h3{font-size:16px;margin:0 0 5px}.card p{font-size:14px;margin-bottom:8px}.card .action{display:inline-flex;align-items:center}
      a{color:var(--gold)}@media(max-width:350px){h1{font-size:23px}.card{grid-template-columns:minmax(0,78px) minmax(0,1fr)}}
    `;
    shadow.append(css);
    const panel = el(mode === 'button' ? 'dialog' : 'section', undefined, {className: mode === 'button' ? '' : 'inline'});
    const headingId = 'quiz-' + session;
    panel.setAttribute('aria-labelledby', headingId);
    const header = el('header');
    header.append(el('h1', title, {id: headingId}));
    if (mode === 'button') {
      const close = el('button', '×', {type: 'button', className: 'close'});
      close.setAttribute('aria-label', 'Close quiz');
      close.onclick = () => panel.close();
      header.append(close);
      panel.addEventListener('close', () => { generation++; event('closed'); launcher.focus(); });
    }
    const content = el('div');
    panel.append(header, content);
    shadow.append(panel);

    function heading(text, focus) {
      const node = el('h2', text, {tabIndex: -1, id: headingId + '-question'});
      content.append(node);
      if (focus) node.focus({preventScroll: true});
      return node;
    }

    function button(text, handler, className = '') {
      const control = el('button', text, {type: 'button', className});
      control.onclick = handler;
      return control;
    }

    function move(step, changes = {}) {
      history.push({...state});
      state = {...state, input: '', ...changes, step};
      event('answered', history.at(-1).step);
      render();
    }

    function navigation() {
      if (!history.length) return;
      const bar = el('div', undefined, {className: 'navigation'});
      bar.append(button('← Back', () => { state = history.pop(); render(); }));
      if (state.step === 'result') {
        bar.append(button('Start again', () => { history.length = 0; state = fresh(); event('started'); render(); }));
      }
      content.append(bar);
    }

    function options(id, values) {
      const overrides = new Map((config.questions.find(q => q.id === id)?.answers || []).map(a => [key(a.value), a]));
      return [...new Map(values.map(value => [key(value), value])).values()]
        .filter(value => overrides.get(key(value))?.enabled !== false)
        .map(value => ({value, label: overrides.get(key(value))?.label
          || (id === 'sport' && value === 'Basketball' ? 'Basketball (NBA)' : value)}))
        .sort((a, b) => a.label.localeCompare(b.label));
    }

    function aliasesFor(value) {
      return Object.entries(config.aliases || {}).filter(([, target]) => key(target) === key(value)).map(([alias]) => alias);
    }

    function search({placeholder, choices, onSubmit, unmatched, skip, typo = false}) {
      const form = el('form');
      const input = el('input', undefined, {type: 'text', value: state.input, placeholder, maxLength: 100, autocomplete: 'off'});
      const list = el('ul', undefined, {id: headingId + '-choices', className: 'suggestions', hidden: true});
      const hint = el('p', '', {className: 'hint', hidden: true});
      hint.setAttribute('role', 'status');
      list.setAttribute('role', 'listbox');
      list.setAttribute('aria-label', 'Suggestions');
      input.setAttribute('role', 'combobox');
      input.setAttribute('aria-labelledby', headingId + '-question');
      input.setAttribute('aria-autocomplete', 'list');
      input.setAttribute('aria-controls', list.id);
      let visible = [], active = -1;

      function highlight(index) {
        active = index;
        [...list.children].forEach((item, i) => item.setAttribute('aria-selected', String(i === active)));
        if (active < 0) input.removeAttribute('aria-activedescendant');
        else {
          input.setAttribute('aria-activedescendant', list.children[active].id);
          list.children[active].scrollIntoView({block: 'nearest'});
        }
      }

      function draw() {
        const term = key(input.value);
        visible = term ? choices.map(choice => ({
          ...choice, score: Math.max(...[choice.label, choice.value, ...(choice.aliases || [])].map(value => searchScore(term, value, typo)))
        })).filter(choice => choice.score).sort((a, b) => b.score - a.score || a.label.localeCompare(b.label)) : [];
        list.replaceChildren(...visible.map((choice, i) => {
          const item = el('li', choice.label, {id: list.id + '-' + i});
          item.setAttribute('role', 'option');
          item.onmousedown = event => event.preventDefault();
          item.onclick = () => onSubmit(choice.value);
          return item;
        }));
        list.hidden = !visible.length;
        input.setAttribute('aria-expanded', String(!list.hidden));
        highlight(-1);
        hint.hidden = !term || !!visible.length || !unmatched;
        hint.textContent = hint.hidden ? '' : 'We don’t have that sport. You can try another or continue.';
        submit.disabled = !term;
      }

      function closeList() {
        list.hidden = true;
        input.setAttribute('aria-expanded', 'false');
        highlight(-1);
      }

      input.oninput = () => { state.input = input.value; draw(); };
      input.onfocus = draw;
      input.onblur = closeList;
      input.onkeydown = event => {
        if (event.key === 'Escape' && !list.hidden) {
          event.preventDefault();
          closeList();
        }
        if (!['ArrowDown','ArrowUp'].includes(event.key) || !visible.length) return;
        event.preventDefault();
        if (list.hidden) draw();
        highlight(active < 0 ? (event.key === 'ArrowDown' ? 0 : visible.length - 1)
          : (active + (event.key === 'ArrowDown' ? 1 : -1) + visible.length) % visible.length);
      };
      form.onsubmit = event => {
        event.preventDefault();
        if (!key(input.value)) return;
        const best = visible[active] || visible[0];
        const exact = best?.score === 5;
        if (unmatched || exact || active >= 0) onSubmit(best?.value || '');
        else onSubmit(input.value.trim());
      };
      const submit = el('button', 'Continue', {type: 'submit', className: 'primary'});
      const actions = el('div', undefined, {className: 'actions'});
      actions.append(submit);
      if (skip) actions.append(button('No favourite', skip, 'quiet'));
      form.append(input, list, hint, actions);
      content.append(form);
      draw();
      if (!state.input) closeList();
    }

    async function loadProducts(sports, index = catalogue) {
      if (preview) return preview.products.filter(p => !sports.length || p.sports.some(sport => sports.includes(sport)));
      const paths = (sports.length ? sports : Object.keys(index.sports))
        .flatMap(sport => [index.sports[sport], ...(index.extra_pages?.[sport] || [])]).filter(Boolean);
      if (!sports.length) paths.push(...(index.unclassified || []));
      const results = [];
      const unique = [...new Set(paths)];
      for (let i = 0; i < unique.length; i += 6) {
        results.push(...await Promise.all(unique.slice(i, i + 6).map(path => {
          if (!/^catalogue\/[a-f0-9]{24}\.json$/.test(path)) throw Error('Invalid catalogue');
          if (!shardRequests.has(path)) {
            shardRequests.set(path, json(base + path).then(data => data.products).catch(error => {
              shardRequests.delete(path);
              throw error;
            }));
          }
          return shardRequests.get(path);
        })));
      }
      return [...new Map(results.flat().map(product => [product.id, product])).values()];
    }

    function browse() {
      const handle = Object.keys(collections).find(value => collections[value] === state.sports[0]) || host.dataset.collection || 'all';
      return root + 'collections/' + (/^[a-z0-9-]+$/.test(handle) ? handle : 'all');
    }

    async function findEdition(products, turn) {
      const candidates = ranked(products, state, config.rules);
      if (preview) return candidates[0] ? {...candidates[0], price: 14900, currency: 'AUD'} : null;
      if (!candidates.length) return null;
      const deadline = AbortSignal.timeout(10000);
      const {currency} = await json(root + 'cart.js', true, deadline);
      if (!/^[A-Z]{3}$/.test(currency)) throw Error('Market unavailable');
      let verificationFailed = false;
      for (let offset = 0; turn === generation && offset < candidates.length; offset += 4) {
        deadline.throwIfAborted();
        const batch = await Promise.all(candidates.slice(offset, offset + 4).map(async product => {
          try {
            const url = root + 'products/' + encodeURIComponent(product.handle);
            const live = await json(url + '.js', true, deadline);
            const prices = (live.variants || []).filter(v => v.available === true && Number.isFinite(v.price) && v.price >= 0).map(v => v.price);
            if (String(live.id) !== product.id.split('/').pop() || live.available !== true || !prices.length) return null;
            return {...product, url, image: live.featured_image || product.image, currency, price: Math.min(...prices)};
          } catch (error) {
            if (![404,410].includes(error.status)) verificationFailed = true;
            return null;
          }
        }));
        const winner = batch.find(Boolean);
        if (winner) return winner;
      }
      if (verificationFailed) throw Error('Availability unavailable');
      return null;
    }

    function result(product, focus) {
      heading(product ? 'We have found your edition' : 'No edition available right now', focus);
      if (!product) {
        content.append(el('p', 'Try another sport or browse the collection.'), el('a', 'Browse editions', {href: browse()}));
        return;
      }
      const card = el('article', undefined, {className: 'card'});
      let image;
      try {
        const url = new URL(product.image, location.href);
        if (preview && product.image || url.protocol === 'https:' && url.hostname === 'cdn.shopify.com') {
          if (url.hostname === 'cdn.shopify.com') url.searchParams.set('width', '360');
          image = el('img', undefined, {src: url.href, alt: ''});
        }
      } catch {}
      if (image) card.append(image);
      else card.style.gridTemplateColumns = '1fr';
      const details = el('div');
      details.append(el('h3', product.title));
      if (Number.isInteger(product.next_number) && Number.isInteger(product.edition_total)
        && product.next_number > 0 && product.next_number <= product.edition_total) {
        details.append(el('p', 'Next edition no. ' + product.next_number + '/' + product.edition_total));
      }
      details.append(el('p', 'From ' + new Intl.NumberFormat(undefined, {style: 'currency', currency: product.currency}).format(product.price / 100)));
      const link = el('a', 'Collect now', {href: preview ? '#' : product.url, className: 'action primary'});
      link.onclick = eventObject => { if (preview) eventObject.preventDefault(); else event('product_click', '', product.id); };
      details.append(link);
      card.append(details);
      content.append(card);
    }

    let lastQuestion = '', completed = false;

    async function render(focus = true) {
      const turn = ++generation;
      content.replaceChildren();
      const question = state.step + ':' + state.subjectIndex + ':' + state.sports.join('|');
      if (state.step !== 'result' && question !== lastQuestion) event('question', state.step);
      lastQuestion = question;
      if (state.step !== 'result') completed = false;

      if (state.step === 'sport') {
        heading('What sports do you support?', false);
        const choices = options('sport', Object.keys(sportOptions).filter(sport => !state.sports.includes(sport)))
          .map(choice => ({...choice, aliases: [...sportOptions[choice.value], ...aliasesFor(choice.value)]}));
        search({placeholder: 'Type a sport or league', choices, unmatched: true, typo: true, onSubmit: sport => {
          move('more', {sports: sport ? [...state.sports, sport] : state.sports, missing: !sport});
        }});
        if (focus) content.querySelector('h2').focus({preventScroll: true});
      } else if (state.step === 'more') {
        heading('Any other favourite sports?', focus);
        if (state.missing) content.append(el('p', 'We don’t have an edition for that sport yet.'));
        const actions = el('div', undefined, {className: 'actions'});
        actions.append(button('Yes', () => move('sport', {missing: false}), 'primary'),
          button('No', () => move(state.sports.length ? 'subject' : 'preference')));
        content.append(actions);
      } else {
        heading(state.step === 'result' ? 'Finding your edition…' : 'Finding available editions…', focus);
        navigation();
        try {
          const index = state.step === 'result' ? await currentCatalogue() : catalogue;
          if (turn !== generation) return;
          const products = await loadProducts(state.sports, index);
          if (turn !== generation) return;
          if (state.step !== 'result') content.replaceChildren();
          if (state.step === 'subject') {
            const sport = state.sports[state.subjectIndex];
            if (state.sports.length > 1) content.append(el('p', sport === 'Basketball' ? 'Basketball (NBA)' : sport, {className: 'context'}));
            heading(subjectPrompt(sport), focus);
            const choices = options('subject', products.filter(p => p.sports.includes(sport)).flatMap(p => p.subjects))
              .map(choice => ({...choice, aliases: aliasesFor(choice.value)}));
            const onSubmit = subject => {
              const subjectIndex = state.subjectIndex + 1;
              move(subjectIndex < state.sports.length ? 'subject' : 'preference',
                {subjects: {...state.subjects, [sport]: subject}, subjectIndex});
            };
            search({placeholder: 'Type a name', choices, onSubmit, skip: () => onSubmit('')});
          } else if (state.step === 'preference') {
            const pool = ranked(products, state, config.rules);
            const matches = pool.filter(p => p.sports.some(sport => subjectScore(p, state.subjects[sport])));
            const relevant = matches.length ? matches : pool;
            const choices = options('preference', relevant.flatMap(p => p.preferences)).slice(0, 4);
            const configured = config.questions.find(q => q.id === 'preference')?.label;
            heading(choices.length ? configured || 'Which story speaks to you?' : 'What matters most in your edition?', focus);
            const actions = el('div', undefined, {className: 'actions'});
            for (const choice of choices) actions.append(button(choice.label, () => move('result', {preference: choice.value})));
            if (!choices.length && relevant.some(p => p.next_number)) {
              actions.append(button('Lowest edition number', () => move('result', {preference: 'lowest'})));
            }
            actions.append(button('Surprise me', () => move('result'), 'primary'));
            content.append(actions);
          } else {
            const product = await findEdition(products, turn);
            if (turn !== generation) return;
            content.replaceChildren();
            result(product, focus);
            if (!completed) event('completed');
            completed = true;
          }
        } catch {
          if (turn !== generation) return;
          content.replaceChildren();
          heading('Availability could not be verified', focus);
          content.append(button('Try again', () => render(), 'primary'), el('p'));
          content.append(el('a', 'Browse editions', {href: browse()}));
        }
      }
      navigation();
    }

    function open() {
      if (mode === 'button' && !panel.open) { panel.showModal(); render(); }
    }
    event('started');
    if (mode === 'inline') { launcher.hidden = true; render(false); }
    else open();
    return {open};
  }};
})();
