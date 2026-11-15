/* Derive identity from the application's complete prepared-context contract.
 * This never changes application readiness or fills missing identity fields. */
(() => {
  'use strict';
  const fields = ['category','kind','name','revision','source','source_id','workflow'];
  function canonical(dataset) {
    if (dataset.ready !== 'true' || typeof dataset.context !== 'string' || dataset.context.length > 4096) return null;
    let value;
    try { value = JSON.parse(dataset.context); } catch { return null; }
    if (!value || Array.isArray(value) || Object.keys(value).sort().join() !== fields.join()) return null;
    if (fields.some(key => typeof value[key] !== 'string' || !value[key] || value[key].length > 180 || /[\u0000-\u001f]/.test(value[key]))) return null;
    if (value.kind !== 'product_uploads' || value.name !== value.name.trim() ||
        !/^[a-f0-9-]{36}$/.test(value.workflow) || !/^id:[A-Za-z0-9_-]+$/.test(value.category) ||
        !/^id:[A-Za-z0-9_-]+$/.test(value.source_id) || !/^[a-f0-9]{64}$/.test(value.source) ||
        !/^[a-f0-9]{9,64}$/.test(value.revision)) return null;
    return JSON.stringify(Object.fromEntries(fields.map(key => [key,value[key]])));
  }
  const cache = new WeakMap();
  // Streamlit can replace a marker with identical data. Reuse only a digest
  // already verified for those exact canonical bytes and supplied hash.
  const verified = new Map();
  function read(node, changed) {
    const serialized = canonical(node.dataset);
    if (!serialized) { cache.delete(node); return null; }
    const supplied = node.dataset.productSha256;
    if (supplied !== undefined && !/^[a-f0-9]{64}$/.test(supplied)) return null;
    const key = serialized + '\n' + (supplied || '');
    if (verified.has(key)) return verified.get(key);
    const prior = cache.get(node);
    if (prior?.key === key) return prior.digest;
    const pending = {key,digest:null}; cache.set(node,pending);
    crypto.subtle.digest('SHA-256',new TextEncoder().encode(serialized)).then(bytes => {
      if (cache.get(node) !== pending || canonical(node.dataset) !== serialized || node.dataset.productSha256 !== supplied) return;
      const digest = Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
      if (supplied === undefined || supplied === digest) {
        pending.digest = digest;
        verified.set(key,digest);
        if (verified.size > 32) verified.delete(verified.keys().next().value);
      }
      changed();
    }).catch(()=>{});
    return null;
  }
  globalThis.SportsCavePreparedContext = {canonical,read};
})();
