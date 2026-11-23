// One bounded cache per mounted account; never shared or persisted across users.
export function createCollectionPairCache({now = Date.now, ttl = 30000, maxEntries = 16} = {}) {
  const entries = new Map();
  return {
    get(key) {
      const entry = entries.get(key);
      if (!entry || now() >= entry.expires) {
        entries.delete(key);
        return undefined;
      }
      entries.delete(key);
      entries.set(key, entry);
      return entry.products;
    },
    put(key, products) {
      entries.delete(key);
      entries.set(key, {products, expires: now() + (products.length ? ttl : Math.min(ttl, 10000))});
      while (entries.size > maxEntries) entries.delete(entries.keys().next().value);
    },
  };
}
