// Methods inserted into the existing theme review class; its layout stays intact.
class NativeReviewMethods {
  async nativeFeed() {
    const owner = this.constructor;
    if (!owner.nativeRequest || owner.nativeUntil < Date.now()) {
      owner.nativeUntil = Date.now() + 30000;
      owner.nativeRequest = (async () => {
        const endpoint = 'https://sports-cave-os-webhooks.onrender.com/reviews/public';
        const rows = [], seen = new Set();
        let offset = 0, summary;
        for (let page = 0; page < 250; page++) {
          const url = new URL(endpoint);
          url.searchParams.set('offset', String(offset));
          const response = await fetch(url.href, {credentials: 'omit', signal: AbortSignal.timeout(20000)});
          if (!response.ok) throw new Error('Reviews unavailable');
          const data = await response.json();
          if (!Array.isArray(data.reviews)) throw new Error('Invalid reviews');
          summary = data.summary;
          for (const review of data.reviews) {
            if (seen.has(review.id)) continue;
            seen.add(review.id);
            const owned = value => {
              try {
                const url = new URL(value);
                return url.origin === new URL(endpoint).origin && /^\/reviews\/media\/[a-f0-9-]+$/.test(url.pathname) ? url.href : '';
              } catch { return ''; }
            };
            rows.push({id: review.id, name: review.reviewer_name, title: review.title,
              body: review.body, rating: review.rating, date: review.created_at,
              product: review.product_title, verified: review.verified_purchase,
              media: (review.media || []).map(media => ({full: owned(media.url),
                thumb: owned(media.thumbnail_url), poster: owned(media.poster_url),
                video: media.kind === 'video', width: media.width, height: media.height
              })).filter(media => media.full && media.thumb)});
          }
          if (data.next_offset == null) return {rows, summary};
          if (!Number.isInteger(data.next_offset) || data.next_offset <= offset) throw new Error('Invalid review pagination');
          offset = data.next_offset;
        }
        throw new Error('Review pagination limit');
      })().catch(error => { owner.nativeRequest = null; throw error; });
    }
    return owner.nativeRequest;
  }

  startFeaturedReviews() { this.syncProvider(); }

  syncProvider() {
    // Judge.me remains available for its existing write-review form during cutover.
    const write = this.directory()?.querySelector('.jdgm-write-rev-link');
    const invitation = this.querySelector('[data-review-invitation]');
    if (invitation) invitation.hidden = !write || write.hidden;
    const button = this.querySelector('[data-review-write]');
    if (button && !invitation) button.hidden = !write || write.hidden;
    if (!this.nativeStarted) {
      this.nativeStarted = true;
      this.loadCarousel();
      if (this.archive) this.loadArchiveBatch();
    }
  }

  async loadCarousel() {
    this.setAttribute('aria-busy', 'true');
    try {
      const {rows, summary} = await this.nativeFeed();
      if (!this.controller || this.controller.signal.aborted) return;
      this.archiveHasSummary = true;
      if (summary?.count) this.summary(Number(summary.average).toFixed(2), String(summary.count));
      this.renderCarousel(this.dataset.layout === 'carousel' ? rows.filter(review => review.media.length).slice(0,30) : rows);
      const histogram = this.querySelector('[data-review-histogram]');
      if (histogram && rows.length) this.renderHistogram([5,4,3,2,1].map(rating => [rating, rows.filter(row => row.rating === rating).length]), rows.length);
    } catch {
      if (!this.list.children.length) {
        this.list.textContent = this.querySelector('[data-review-empty]')?.textContent || '';
        this.inner.hidden = false;
      }
    } finally { this.removeAttribute('aria-busy'); }
  }

  async loadArchiveBatch() {
    const more = this.querySelector('[data-review-more]');
    if (!this.archive || more?.disabled) return;
    more.disabled = true;
    try {
      const {rows} = await this.nativeFeed();
      if (!this.controller || this.controller.signal.aborted) return;
      this.archiveReviews = rows;
      this.archiveLimit = this.archive.children.length + 5;
      this.archiveSources.forEach(source => { source.done = true; });
      this.archiveFailed = false;
      this.renderArchive();
    } catch {
      this.archiveFailed = true;
      this.renderArchive();
      more.hidden = false;
    } finally { more.disabled = false; }
  }

  renderMedia() {
    const current = this.current.media[this.mediaIndex];
    const target = this.querySelector('[data-review-media]');
    target.querySelectorAll('video').forEach(video => { video.pause(); video.removeAttribute('src'); video.load(); });
    target.replaceChildren();
    target.parentElement.hidden = !current;
    if (!current) return;
    const element = document.createElement(current.video ? 'video' : 'img');
    if (current.video) {
      element.controls = true;
      element.playsInline = true;
      element.preload = 'none';
      element.poster = current.poster || current.thumb;
    } else {
      element.alt = this.current.title || '';
      element.decoding = 'async';
    }
    element.style.cssText = 'display:block;max-width:100%;width:auto;height:auto;max-height:65dvh;object-fit:contain;margin:auto';
    element.src = current.full;
    target.append(element);
    const count = this.current.media.length;
    this.querySelector('[data-review-media-controls]').hidden = count < 2;
    this.querySelector('[data-review-media-count]').textContent = (this.mediaIndex + 1) + ' / ' + count;
  }
}
