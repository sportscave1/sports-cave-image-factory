// OS_REVIEW_SUMMARY_SYNC_V1: one published snapshot for every visible total.
(() => {
  customElements.whenDefined('sc-customer-reviews').then(() => {
    const Type = customElements.get('sc-customer-reviews');
    if (Type.osSummarySync) return;
    Type.osSummarySync = true;
    let latest = null, pending = null, controller = null, timer = null, failures = 0;
    const widgets = () => [...document.querySelectorAll('sc-customer-reviews')];
    const valid = s => Number.isSafeInteger(s?.count) && s.count >= 0 &&
      (s.count === 0 ? s.average == null || Number(s.average) === 0 :
        typeof s.average === 'number' && Number.isFinite(s.average) && s.average >= 1 && s.average <= 5);
    const apply = (summary, asOf) => {
      if (!valid(summary)) return false;
      const stamp = asOf ? Date.parse(asOf) : 0;
      if (!Number.isFinite(stamp) || (latest?.stamp && (!stamp || stamp < latest.stamp))) return false;
      const received = latest && stamp === latest.stamp ? latest.received : Date.now();
      latest = {summary, stamp, received, histogram: latest?.stamp === stamp ? latest.histogram : null};
      const average = Number(summary.average || 0), label = `${summary.count} ${summary.count === 1 ? 'review' : 'reviews'}`;
      widgets().forEach(widget => {
        widget.summary(average.toFixed(2), String(summary.count));
        widget.querySelector('[data-review-summary]')?.setAttribute('aria-busy', 'false');
      });
      document.querySelectorAll('.scx-review-text').forEach(target => {
        const rating = target.querySelector('strong'), count = target.querySelector('span:last-child');
        if (rating && rating.textContent !== average.toFixed(1)) rating.textContent = average.toFixed(1);
        if (count && count.textContent !== label) count.textContent = label;
        const button = target.closest('.scx-review-inline');
        if (!button) return;
        button.setAttribute('aria-busy', 'false');
        button.setAttribute('aria-label', `Jump to customer reviews: ${average.toFixed(1)} out of 5, ${label}`);
        const stars = button.querySelector('.scx-stars');
        if (stars) {
          stars.style.opacity = '1';
          stars.style.backgroundImage = `linear-gradient(to right, var(--sc-brand-gold,#d4a54c) ${average / 5 * 100}%, #ffffff40 0)`;
          stars.style.backgroundClip = 'text';
          stars.style.webkitBackgroundClip = 'text';
          stars.style.color = 'transparent';
        }
      });
      return true;
    };
    const applyData = data => {
      if (!apply(data?.summary, data?.as_of)) return false;
      if (Array.isArray(data.histogram) && data.histogram.length === 5 && data.histogram.every(r =>
        Array.isArray(r) && Number.isInteger(r[0]) && r[0] >= 1 && r[0] <= 5 && Number.isSafeInteger(r[1]) && r[1] >= 0)) {
        latest.histogram = data.histogram;
        widgets().forEach(widget => {
          if (widget.querySelector('[data-review-histogram]')) widget.renderHistogram(data.histogram, data.summary.count);
        });
      }
      return true;
    };
    Type.prototype.nativeSummary = apply;
    const applyRows = Type.prototype.nativeApply;
    Type.prototype.nativeApply = function(data, append = false) {
      const accepted = applyData(data);
      applyRows.call(this, data, append);
      if (!accepted && latest?.histogram && this.querySelector('[data-review-histogram]')) {
        this.renderHistogram(latest.histogram, latest.summary.count);
      }
    };
    const pause = () => { clearTimeout(timer); timer = null; controller?.abort(); };
    const schedule = () => {
      clearTimeout(timer);
      if (document.visibilityState !== 'hidden' && widgets().length) {
        timer = setTimeout(refresh, Math.min(120000, 30000 * 2 ** failures));
      }
    };
    async function refresh() {
      if (pending) return pending;
      if (document.visibilityState === 'hidden' || !widgets().length) return;
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 8000);
      pending = (async () => {
        try {
          const response = await fetch('https://sports-cave-image-factory.onrender.com/reviews/widget?summary=1',
            {credentials: 'omit', cache: 'no-cache', signal: controller.signal});
          if (!response.ok || !applyData(await response.json())) throw new Error('Invalid summary');
          failures = 0;
        } catch { failures = Math.min(2, failures + 1); }
        finally { clearTimeout(timeout); pending = null; controller = null; schedule(); }
      })();
      return pending;
    }
    const resume = () => {
      if (document.visibilityState === 'hidden') return pause();
      if (!latest || Date.now() - latest.received >= 30000) refresh();
      else schedule();
    };
    document.addEventListener('visibilitychange', resume);
    window.addEventListener('pageshow', resume);
    window.addEventListener('pagehide', pause);
    document.addEventListener('shopify:section:load', () => {
      if (latest) apply(latest.summary, latest.stamp ? new Date(latest.stamp).toISOString() : null);
      resume();
    });
    const first = widgets()[0];
    if (first) first.nativeFeed().then(data => { applyData(data); schedule(); }).catch(() => { refresh(); });
  });
})();
