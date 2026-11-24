class DraftReviewMethods {
  async nativePage(offset) {
    const url = new URL('https://sports-cave-image-factory.onrender.com/reviews/widget');
    url.searchParams.set('country', this.dataset.country === 'US' ? 'US' : 'AU');
    url.searchParams.set('offset', String(offset));
    const response = await fetch(url.href, {credentials: 'omit', signal: AbortSignal.timeout(12000)});
    if (!response.ok) throw new Error('Reviews unavailable');
    const data = await response.json();
    if (!Array.isArray(data.reviews) || !Array.isArray(data.featured) || !Number.isSafeInteger(data.summary?.count) ||
        data.summary.count < 0 || (data.next_offset != null &&
          (!Number.isSafeInteger(data.next_offset) || data.next_offset !== offset + data.reviews.length || data.next_offset <= offset))) {
      throw new Error('Invalid review page');
    }
    return data;
  }

  async nativeFeed() {
    const owner = this.constructor, country = this.dataset.country === 'US' ? 'US' : 'AU';
    owner.nativeRequests ||= new Map();
    let entry = owner.nativeRequests.get(country);
    if (!entry || entry.until < Date.now()) {
      entry = {until: Date.now() + 30000, request: this.nativePage(0)};
      owner.nativeRequests.set(country, entry);
      entry.request.catch(() => { if (owner.nativeRequests.get(country) === entry) owner.nativeRequests.delete(country); });
    }
    return entry.request;
  }

  nativeRows(reviews, featured = false) {
    const owned = value => {
      try {
        const url = new URL(value);
        return url.origin === 'https://sports-cave-image-factory.onrender.com' &&
          /^\/reviews\/media\/[a-f0-9-]+$/.test(url.pathname) && ['320','640','1280','original'].includes(url.searchParams.get('size')) ? url.href : '';
      } catch { return ''; }
    };
    return reviews.map(review => ({id: featured ? review.legacy_id || review.id : review.id,
      name: review.reviewer_name, title: review.title, body: review.body, rating: review.rating,
      date: review.created_at, product: review.product_title, productThumb: /^https:\/\/(cdn\.shopify\.com|www\.sportscaveshop\.com|sportscaveshop\.com)\//.test(review.product_thumbnail_url || '') ? review.product_thumbnail_url : '', productUrl: /^https:\/\/(www\.)?sportscaveshop\.com\//.test(review.product_url || '') ? review.product_url : '', verified: review.verified_purchase || review.source_verified,
      media: (review.media || []).filter(media => media.kind === 'image' || media.kind === 'video').map(media => ({
        full: owned(media.url), video: media.kind === 'video', thumb: owned(media.thumbnail_url), width: media.width, height: media.height,
        srcset: owned(media.carousel_url) ? `${owned(media.thumbnail_url)} 320w, ${owned(media.carousel_url)} 640w` : `${owned(media.thumbnail_url)} 320w`
      })).filter(media => media.full && media.thumb)}));
  }

  nativeApply(data, append = false) {
    if (!this.controller || this.controller.signal.aborted) return;
    if (data.summary.count) this.summary(Number(data.summary.average).toFixed(2), String(data.summary.count));
    document.querySelectorAll('.scx-review-text').forEach(target => {
      const rating = target.querySelector('strong'), count = target.querySelector('span:last-child');
      if (rating) rating.textContent = Number(data.summary.average || 0).toFixed(1);
      if (count) count.textContent = `${data.summary.count} reviews`;
    });
    if (!append) {
      this.renderCarousel(this.nativeRows(data.featured, true));
      if (this.querySelector('[data-review-histogram]')) this.renderHistogram(data.histogram, data.summary.count);
      this.archive?.replaceChildren();
      this.archiveReviews = [];
    }
    this.nativeNext = data.next_offset;
    const seen = new Set(this.archiveReviews.map(row => row.id));
    this.archiveReviews.push(...this.nativeRows(data.reviews).filter(row => !seen.has(row.id)));
    this.archiveLimit = this.archiveReviews.length;
    this.archiveSources.forEach(source => { source.done = this.nativeNext == null; });
    this.archiveFailed = false;
    if (this.archive) this.renderArchive();
    const more = this.querySelector('[data-review-more]');
    if (more) more.textContent = 'Load more';
    this.inner.hidden = false;
    this.classList.add('sc-reviews--ready');
    this.removeAttribute('aria-busy');
  }

  async loadCarousel() {
    if (this.nativeLoading) return this.nativeLoading;
    this.nativeStarted = true;
    this.setAttribute('aria-busy', 'true');
    this.nativeLoading = (async () => {
      try { this.nativeApply(await this.nativeFeed()); this.nativeReady = true; }
      catch {
        this.archiveFailed = true;
        const more = this.querySelector('[data-review-more]');
        if (more) { more.hidden = false; more.textContent = 'Retry loading reviews'; }
        const status = this.querySelector('[data-review-status]');
        if (status) status.textContent = 'Reviews are temporarily unavailable. Please try again.';
      } finally { this.removeAttribute('aria-busy'); this.nativeLoading = null; }
    })();
    return this.nativeLoading;
  }

  async loadArchiveBatch() {
    if (!this.nativeReady) return this.loadCarousel();
    const more = this.querySelector('[data-review-more]');
    if (!this.archive || more?.disabled || this.nativeNext == null) return;
    if (more) more.disabled = true;
    try { this.nativeApply(await this.nativePage(this.nativeNext), true); }
    catch {
      this.archiveFailed = true;
      if (more) { more.hidden = false; more.textContent = 'Retry loading reviews'; }
      const status = this.querySelector('[data-review-status]');
      if (status) status.textContent = 'More reviews could not load. Please try again.';
    } finally { if (more) more.disabled = false; }
  }

  startFeaturedReviews() { this.syncProvider(); }

  syncProvider() {
    const invitation = this.querySelector('[data-review-invitation]');
    if (invitation) invitation.hidden = false;
    const button = this.querySelector('[data-review-write]');
    if (button) button.hidden = false;
    if (!this.nativeStarted) this.loadCarousel();
  }
}
