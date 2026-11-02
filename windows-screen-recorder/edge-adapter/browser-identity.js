/* Shared semantic identity projection and bounded trusted-click witness.
 * No field value reads or replay. Native hooks remain the capture owner. */
(() => {
  'use strict';
  if (window.__sportsCaveBrowserIdentityV2) return;
  const origins = new Set(['http://127.0.0.1:18962', 'http://127.0.0.1:18963', 'https://sports-cave-image-factory.onrender.com', 'https://chatgpt.com']);
  const downloadOrigins = new Set(['http://127.0.0.1:18962', 'http://127.0.0.1:18963', 'https://sports-cave-image-factory.onrender.com']);
  let host;
  try { host = top; if (!origins.has(host.location.origin)) return; } catch { return; }
  window.__sportsCaveBrowserIdentityV2 = true;
  const prefix = 'Sports Cave browser v2: ';
  const downloadPrefix = 'Sports Cave download v1: ';
  // Page-only builds must never alter links or intercept downloads without a worker.
  const downloadEnabled = typeof chrome !== 'undefined' &&
    chrome.runtime?.getManifest?.().permissions?.includes('downloads') === true;
  const privateText = /password|passwd|credential|secret|token|authorization|one.?time|otp|api.?key|Bearer\s|eyJ[\w-]{12,}/i;
  const clean = text => typeof text === 'string' && text.length <= 180 && !privateText.test(text);
  const selectors = 'button,input:not([type="hidden"]),textarea,select,a[href],summary,[contenteditable="true"][role="textbox"],[role="button"],[role="combobox"],[role="checkbox"],[role="tab"]';
  const originals = new WeakMap();
  const projected = new Set();
  const ephemeral = crypto.randomUUID();
  const mappingWitnessKey='sc-recorder-mapping-gesture-v1';
  function publishGesture(witness) {
    let marker=host.document.getElementById('sc-recorder-button-gesture');
    if(!marker){marker=host.document.createElement('span');marker.id='sc-recorder-button-gesture';marker.setAttribute('role','status');
      marker.setAttribute('aria-label','Sports Cave button gesture');
      marker.style.cssText='position:fixed;bottom:0;right:2px;width:1px;height:1px;overflow:hidden;pointer-events:none;opacity:.01';host.document.body.append(marker);}
    marker.title='Sports Cave button gesture v2: '+encodeURIComponent(JSON.stringify(witness));
  }
  document.addEventListener('pointerdown',event=>{
    if(!event.isTrusted||event.button!==0||!event.isPrimary)return;
    const node=event.target.closest?.('button,[role="button"]');
    if(!node||node.disabled||!key(node)||!clean(label(node)))return;
    const line=(node.getAttribute('title')||'').split('\n').find(value=>value.startsWith(prefix));
    if(!line||line.length>6000)return;
    try {
      const identity=JSON.parse(decodeURIComponent(line.slice(prefix.length)));
      if(identity.profile!==profile||identity.page!==page()||identity.control!==key(node))return;
      const matches=[...document.querySelectorAll(selectors)].filter(candidate=>key(candidate)===identity.control);
      if(matches.length!==1||matches[0]!==node)return;
      let marker=host.document.getElementById('sc-recorder-button-gesture');
      if(!marker){marker=host.document.createElement('span');marker.id='sc-recorder-button-gesture';marker.setAttribute('role','status');
        marker.setAttribute('aria-label','Sports Cave button gesture');
        marker.style.cssText='position:fixed;bottom:0;right:2px;width:1px;height:1px;overflow:hidden;pointer-events:none;opacity:.01';host.document.body.append(marker);}
      const witness={identity,name:label(node),time:Date.now()};
      const downloadLine=(node.getAttribute('title')||'').split('\n').find(value=>value.startsWith(downloadPrefix));
      if(downloadEnabled&&downloadLine&&node.matches('a[download][data-sc-save-as="true"]')) {
        const download=JSON.parse(decodeURIComponent(downloadLine.slice(downloadPrefix.length)));
        const url=new URL(node.href);
        if(download.url!==url.href||download.filename!==node.getAttribute('download')||download.save_as!==true||
           url.origin!==host.location.origin||privateText.test(url.search)||!clean(download.filename))return;
        witness.download=download;
        witness.pointer={x:(event.screenX-host.screenX)*host.devicePixelRatio,y:(event.screenY-host.screenY)*host.devicePixelRatio,
          width:host.outerWidth*host.devicePixelRatio,height:host.outerHeight*host.devicePixelRatio,scale:host.devicePixelRatio};
      }
      marker.title='Sports Cave button gesture v2: '+encodeURIComponent(JSON.stringify(witness));
      // Mapping performs a full-document navigation. Retain only its existing
      // bounded trusted-pointer metadata, in this tab, for at most two seconds.
      if(identity.control==='id:map'&&identity.page===host.location.origin+'/?page=product_uploads') {
        try {host.sessionStorage.setItem(mappingWitnessKey,JSON.stringify(witness));} catch {}
      }
    } catch {}
  },true);
  document.addEventListener('click',event=>{
    if(!downloadEnabled)return;
    const link=event.target.closest?.('a[download][data-sc-save-as="true"]');
    if(!link||!event.isTrusted)return;
    try {
      const url=new URL(link.href);
      if(!downloadOrigins.has(url.origin)||!url.searchParams.has('sc_download'))return;
      event.preventDefault();
      chrome.runtime.sendMessage({kind:'save_as',url:url.href,filename:link.getAttribute('download')});
    } catch {}
  },true);
  let profile;
  try {
    profile = host.localStorage.getItem('sc-recorder-preview-profile-v2');
    if (!/^[0-9a-f-]{36}$/.test(profile || '')) {
      profile = crypto.randomUUID(); host.localStorage.setItem('sc-recorder-preview-profile-v2', profile);
    }
  } catch { return; }
  if(window===host)try {
    const saved=host.sessionStorage.getItem(mappingWitnessKey);
    host.sessionStorage.removeItem(mappingWitnessKey);
    if(saved&&saved.length<=7000&&page()===host.location.origin+'/?page=edition_ops') {
      const witness=JSON.parse(saved),age=Date.now()-witness.time,identity=witness.identity;
      if(Object.keys(witness).sort().join(',')==='identity,name,time'&&age>=0&&age<=2000&&clean(witness.name)&&
          identity?.profile===profile&&identity.control==='id:map'&&identity.page===host.location.origin+'/?page=product_uploads')publishGesture(witness);
    }
  } catch {}
  function page() {
    const url = new URL(host.location.href);
    const query = new URLSearchParams();
    for (const key of ['page', 'upload', 'sync_map']) if (url.searchParams.has(key)) query.set(key, url.searchParams.get(key));
    return url.origin + url.pathname + (query.size ? '?' + query : '');
  }
  function frame() {
    if (window === host) return 'top';
    let current = window, parts = [];
    try {
      while (current !== host && parts.length < 8) {
        const element = current.frameElement;
        if (!element) return null;
        const name = element.getAttribute('data-sc-recorder-frame') || element.title || element.id;
        if (!name || !clean(name)) return null;
        const siblings = [...element.ownerDocument.querySelectorAll('iframe')].filter(e =>
          (e.getAttribute('data-sc-recorder-frame') || e.title || e.id) === name);
        if (siblings.length !== 1) return null;
        const source = new URL(element.getAttribute('src') || 'about:blank', element.ownerDocument.baseURI);
        if (source.origin !== host.location.origin || privateText.test(source.pathname)) return null;
        parts.unshift(name + '@' + source.pathname); current = current.parent;
      }
      const result = parts.join('/'); return current === host && clean(result) ? result : null;
    } catch { return null; }
  }
  function role(node) {
    return node.getAttribute('role') || ({BUTTON:'button',SELECT:'combobox',TEXTAREA:'textbox',A:'link',SUMMARY:'button'}[node.tagName]) ||
      (node.type === 'checkbox' ? 'checkbox' : 'textbox');
  }
  function label(node) {
    return node.getAttribute('aria-label') || (node.labels?.length ? [...node.labels].map(l=>l.textContent.trim()).join(' ') : '') ||
      node.getAttribute('placeholder') || (['BUTTON','A','SUMMARY'].includes(node.tagName) ? node.textContent.trim() : '');
  }
  function key(node) {
    if (node.type === 'password' || /password|one-time-code|username/.test(node.autocomplete || '') ||
        !clean(node.name || '') || !clean(node.id || '') || !clean(label(node))) return null;
    const explicit = node.getAttribute('data-sc-recorder-id');
    const id = explicit || (node.id && !/^(?:[:]|[a-f\d]{12,}|st-)/i.test(node.id) ? node.id : '');
    const result = id ? 'id:' + id : 'label:' + role(node) + ':' + label(node);
    return clean(result) && (id || label(node)) ? result : null;
  }
  function project(node, context) {
    projected.add(node);
    if (!originals.has(node)) originals.set(node, node.getAttribute('title') || '');
    // Keep dropdown selected-value projection intact, whichever adapter ran first.
    let old = (node.getAttribute('title') || '').split('\n').filter(line=>!line.startsWith(prefix)&&!line.startsWith(downloadPrefix)).join('\n');
    if(downloadEnabled && node.tagName==='A' && node.hasAttribute('download')) {
      try {
        const source=new URL(node.href);
        const filename=node.getAttribute('download');
        if(downloadOrigins.has(source.origin)&&clean(filename)&&filename&&!/[\\/]/.test(filename)&&!privateText.test(source.search)) {
          if(!source.searchParams.has('sc_download')){source.searchParams.set('sc_download',crypto.randomUUID());node.href=source.href;}
          old=downloadPrefix+encodeURIComponent(JSON.stringify({url:source.href,filename,save_as:node.dataset.scSaveAs==='true'}))+(old?'\n'+old:'');
        }
      } catch {}
    }
    const composerPrefix='Sports Cave composer v1: ';
    old=old.split('\n').filter(line=>!line.startsWith(composerPrefix)).join('\n');
    if(context.page==='https://chatgpt.com/g/g-p-6a387a17627081918e1700ec2783a12b/project' &&
       node.matches('[contenteditable="true"][role="textbox"]') && label(node)==='New chat in SC Mockups/Uploads') {
      // Only a boolean leaves the DOM. Placeholder text is not editor content.
      old=composerPrefix+(node.textContent===''?'empty':'nonempty')+(old?'\n'+old:'');
    }
    const value = prefix + encodeURIComponent(JSON.stringify({...context,document:ephemeral})) + (old ? '\n' + old : '');
    if (node.getAttribute('title') !== value) node.setAttribute('title',value);
  }
  let scheduled = false;
  function remove(node) {
    if(node.getAttribute('title')?.includes(prefix))
      node.setAttribute('title',node.getAttribute('title').split('\n').filter(line=>!line.startsWith(prefix)).join('\n'));
    projected.delete(node);
  }
  function sync() {
    scheduled = false;
    const path = frame(), url = page();
    if (!path || url.length > 500 || privateText.test(url) || /login|signin|oauth|\/auth(?:\/|$)/i.test(host.location.pathname)) {
      for(const node of projected)remove(node); return;
    }
    const base = {profile,page:url,frame:path};
    const contexts=host.document.querySelectorAll('#sc-recorder-context');
    // Streamlit changes the URL before removing the previous upload context.
    // Do not publish a destination identity made from two different pages.
    if (contexts.length && new URL(url).searchParams.get('page') !== 'product_uploads') {
      for (const node of projected) remove(node);
      return;
    }
    if(contexts.length>1) {for(const node of projected)remove(node);return;}
    if(contexts.length===1) {
      const product = globalThis.SportsCavePreparedContext?.read(contexts[0],schedule);
      if(contexts[0].dataset.ready==='true'&&!product) {
        for(const node of projected)remove(node);return;
      }
      if(product) base.product=product;
    }
    const nodes = [...document.querySelectorAll(selectors)];
    if (nodes.length > 2000) {for(const node of projected)remove(node);return;}
    const groups = new Map();
    for (const node of nodes) { const id = key(node); if (id) { if(!groups.has(id))groups.set(id,[]);groups.get(id).push(node); } }
    const retained=new Set();
    for (const [control, group] of groups) {
      if (group.length === 1) {project(group[0],{...base,control});retained.add(group[0]);}
    }
    for(const node of projected)if(node.id!=='sc-recorder-document'&&!retained.has(node))remove(node);
    if (window === host && document.body) {
      let marker = document.getElementById('sc-recorder-document');
      if (!marker) {
        marker=document.createElement('span');marker.id='sc-recorder-document';marker.setAttribute('role','status');
        marker.setAttribute('aria-label','Sports Cave preview browser identity');
        marker.style.cssText='position:fixed;bottom:0;right:0;width:1px;height:1px;overflow:hidden;pointer-events:none;opacity:.01';
        document.body.append(marker);
      }
      project(marker,{...base,control:'document'});
    }
  }
  function schedule(){if(!scheduled){scheduled=true;queueMicrotask(sync);}}
  new MutationObserver(schedule).observe(document,{subtree:true,childList:true,characterData:true,attributes:true,
    attributeFilter:['id','aria-label','aria-expanded','disabled','type','autocomplete','data-sc-recorder-id',
      'data-ready','data-context','data-product-sha256']});
  host.addEventListener('popstate',schedule);host.addEventListener('hashchange',schedule);
  // pushState does not dispatch popstate; bounded polling updates page identity
  // and rerendered frames without wrapping or changing application navigation.
  setInterval(schedule,500);sync();
})();
