// One loader per mounted account. Never persist customer data across accounts.
export function createFrameOfferLoader({bootstrap, prices, now = Date.now, ttl = 60000}) {
  function resource(load) {
    let entry;
    return () => {
      if (entry && (entry.pending || now() < entry.expires)) return entry.promise;
      const current = {pending: true, expires: 0};
      entry = current;
      current.promise = Promise.resolve().then(load).then(value => {
        current.pending = false;
        current.expires = now() + ttl;
        return value;
      }, error => {
        if (entry === current) entry = undefined;
        throw error;
      });
      return current.promise;
    };
  }
  const loadBootstrap = resource(bootstrap);
  const markets = new Map();
  return {
    bootstrap: loadBootstrap,
    context(country) {
      if (!markets.has(country)) {
        markets.set(country, resource(async () => {
          const payload = await loadBootstrap();
          const product = payload.frame_product;
          return {...payload, frame_product: product?.available ? await prices(product, country) : product};
        }));
      }
      return markets.get(country)();
    },
  };
}
