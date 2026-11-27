(() => {
  if (customElements.get('sc-customer-reviews')) return;

  const rivalsReviewId = '4c91276a-636b-4eae-944a-d9912d65900e';
  const sixForTheKingReviewId = '013c8326-eeb9-41c0-8a3a-07ee648bcf2a';
  const cantStopTryingReviewId = '3cea26d2-792c-42c7-a283-48e1d8cf5c54';
  const haalandReviewId = '82212abb-7957-46ff-a819-fea0c3ab6e5e';
  const curryReviewId = 'd69b0463-04bc-412c-948a-1636353b3528';
  const mixedEditionsReviewId = 'f0a533af-ce9f-4114-845d-dc003032c337';
  const usFeaturedReviewIds = [
    curryReviewId,
    sixForTheKingReviewId,
    mixedEditionsReviewId,
    haalandReviewId,
    cantStopTryingReviewId
  ];

  // Initial reviews are supplied by the OS feed.
  const featuredPhotoReviews = [];

  const archiveBackup = [];

  const usArtworkReviewIds = new Set([
    curryReviewId, sixForTheKingReviewId, cantStopTryingReviewId,
    'c1fc64d3-bd69-4401-b510-24e30112cc97' // Muhammad Ali photo
  ]);
  const usArtwork = /\b(?:nba|wnba|nfl|mlb|nhl|nascar|basketball|baseball|super bowl|kyle larson|don mattingly|babe ruth|shohei ohtani|aaron judge|ohtani|kobe|jordan|stephen curry|steph curry|lebron|wilt chamberlain|muhammad ali|mike tyson|tiger woods|tom brady|patrick mahomes|inter miami)\b/i;
  const usArtworkReview = review => review.id !== mixedEditionsReviewId && (
    usArtworkReviewIds.has(review.id) || usArtwork.test(review.product || review.title + ' ' + review.body)
  );

  const takeReview = (reviews, id) => {
    const index = reviews.findIndex(review => review.id === id);
    return index === -1 ? [] : reviews.splice(index, 1);
  };

  // This Shop-synced review is excluded from the draft storefront display.
  const excludedReviewId = '0af86c4c-bda9-5e9a-9070-0414339b5cd8';

  const node = (tag, className, text) => {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text) element.textContent = text;
    return element;
  };
  customElements.define('sc-customer-reviews', class extends HTMLElement {
    connectedCallback() {
      if (this.controller) return;
      this.controller = new AbortController();
      const options = { signal: this.controller.signal };
      this.inner = this.querySelector('.sc-reviews__inner');
      this.list = this.querySelector('[data-review-list]');
      this.archive = this.querySelector('[data-review-archive]');
      this.archiveLimit = 5;
      this.archiveReviews = [];
      this.archivePages = new Map();
      this.archiveIsBackup = false;
      this.archive?.replaceChildren();
      this.archiveSources = [
        { type: 'product-reviews', page: 1 },
        { type: 'shop-reviews', page: 1 }
      ];
      this.dialog = this.querySelector('[data-review-dialog]');
      this.formDialog = this.querySelector('[data-review-form-dialog]');
      this.formDialog?.addEventListener('close', () => {
        this.querySelector('[data-review-form-host]')?.replaceChildren();
        this.querySelector('[data-review-write]').focus({ preventScroll: true });
      }, options);
      this.addEventListener('click', event => this.handleClick(event), options);
      this.sizeObserver = new ResizeObserver(() => {
        this.updateArrows();
        this.updateReadMore();
      });
      this.sizeObserver.observe(this.list);
      if (this.dataset.layout === 'carousel') {
        this.list.addEventListener('scroll', () => {
          this.updateArrows();
          clearTimeout(this.loopTimer);
          this.loopTimer = setTimeout(() => this.wrapCarousel(), 150);
        }, { ...options, passive: true });
      }
      this.dialog.addEventListener('keydown', event => {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        event.stopPropagation();
        this.dialog.close();
      }, options);
      this.dialog.addEventListener('close', () => {
        this.querySelector('[data-review-media]').replaceChildren();
        this.opener?.focus({ preventScroll: true });
      }, options);
      if (this.dataset.layout === 'carousel' && this.dataset.shop === 'sportscave-nb.myshopify.com') {
        if (this.formDialog) {
          this.startFeaturedReviews();
        } else {
          this.reviewStart = new IntersectionObserver(([entry]) => {
            if (!entry.isIntersecting) return;
            this.reviewStart.disconnect();
            this.startFeaturedReviews();
          }, { rootMargin: '700px 0px' });
          this.reviewStart.observe(this);
        }
      } else {
        if (this.dataset.layout === 'carousel') this.loadCarousel();
        if (this.formDialog || this.dataset.layout !== 'carousel') this.syncProvider();
        if (this.archive) this.loadArchiveBatch();
      }
    }

    disconnectedCallback() {
      this.controller?.abort();
      this.controller = null;
      this.observer?.disconnect();
      this.sizeObserver?.disconnect();
      this.reviewStart?.disconnect();
      this.reviewViewport?.disconnect();
      clearTimeout(this.loopTimer);
      cancelAnimationFrame(this.frame);
      this.frame = null;
    }

    renderCarousel(photoReviews) {
      if (this.dataset.country === 'US') {
        const priority = review => {
          const featuredIndex = usFeaturedReviewIds.indexOf(review.id);
          if (featuredIndex !== -1) return featuredIndex;
          return usFeaturedReviewIds.length + (review.country === 'US' ? 0 : 1);
        };
        photoReviews.sort((a, b) => priority(a) - priority(b));
        const rivals = takeReview(photoReviews, rivalsReviewId);
        photoReviews.splice(6, 0, ...rivals);
      } else if (this.dataset.country === 'AU') {
        const rivals = takeReview(photoReviews, rivalsReviewId);
        const sixForTheKing = takeReview(photoReviews, sixForTheKingReviewId);
        photoReviews.splice(2, 0, ...rivals, ...sixForTheKing);
      }
      this.render(photoReviews);
    }


    renderHistogram(rows, total) {
      const breakdown = this.querySelector('[data-review-histogram]');
      breakdown.replaceChildren(...rows.map(([rating, count]) => {
        const item = node('li');
        const stars = node('span', 'sc-reviews__histogram-stars', '★'.repeat(rating) + '☆'.repeat(5 - rating));
        stars.setAttribute('aria-label', rating + ' stars');
        const bar = node('span', 'sc-reviews__histogram-bar');
        bar.style.setProperty('--share', (100 * count / total) + '%');
        bar.setAttribute('aria-hidden', 'true');
        item.append(stars, bar, node('span', '', count.toLocaleString(this.dataset.locale)));
        return item;
      }));
      breakdown.hidden = false;
    }

    renderArchive() {
      const reviews = this.archiveReviews;
      const visible = Math.min(this.archiveLimit, reviews.length);
      const more = this.querySelector('[data-review-more]');
      for (let index = this.archive.children.length; index < visible; index++) {
        const review = reviews[index];
        const row = node('article', 'sc-reviews__row');
        this.addReviewCopy(row, review);
        if (this.dataset.country !== 'US' && review.date) {
          const date = new Date(review.date.replace(' UTC', 'Z').replace(' ', 'T'));
          if (Number.isFinite(date.getTime())) {
            const time = node('time', 'sc-reviews__date', new Intl.DateTimeFormat(this.dataset.locale, { dateStyle: 'medium', timeZone: 'UTC' }).format(date));
            time.dateTime = date.toISOString();
            row.append(time);
          }
        }
        const open = node('button', 'sc-reviews__read-more sc-reviews__row-open', 'Read more');
        open.type = 'button';
        open.dataset.archiveIndex = index;
        open.hidden = true;
        row.querySelector('.sc-reviews__read-more')?.replaceWith(open);
        const picture = review.media[0];
        if (picture) {
          const image = node('img');
          image.alt = '';
          image.loading = 'lazy';
          if (picture.srcset) {
            image.sizes = '68px';
            image.srcset = picture.srcset;
          }
          image.src = picture.thumb;
          const thumbnail = node('button', 'sc-reviews__row-photo');
          thumbnail.type = 'button';
          thumbnail.dataset.archiveIndex = index;
          thumbnail.dataset.archivePhoto = String(review.media.indexOf(picture));
          thumbnail.setAttribute('aria-label', picture.video ? 'View review video' : 'View review photo');
          thumbnail.append(image);
          row.append(thumbnail);
        }
        if (!picture && review.productThumb) {
          const thumbnail = node(review.productUrl ? 'a' : 'span', 'sc-reviews__row-photo');
          if (review.productUrl) thumbnail.href = review.productUrl;
          const image = node('img');
          image.src = review.productThumb; image.alt = 'Product reviewed: ' + (review.product || 'Sports Cave edition');
          image.width = 68; image.height = 68; image.loading = 'lazy'; image.decoding = 'async'; image.style.objectFit = 'contain';
          thumbnail.append(image); row.append(thumbnail);
        }
        this.archive.append(row);
      }

      const empty = this.querySelector('[data-review-empty]');
      if (empty) empty.hidden = visible > 0 || !this.archiveSources.every(source => source.done);
      if (!this.archive.parentElement.hidden) {
        this.inner.hidden = false;
        this.classList.add('sc-reviews--ready');
      }
      more.hidden = visible >= reviews.length && this.archiveSources.every(source => source.done);
      this.updateReadMore();
      this.querySelector('[data-review-status]').textContent = visible ? visible + ' reviews shown' : this.archiveFailed ? 'Reviews are temporarily unavailable.' : 'No matching reviews.';
    }

    summary(rating, count) {
      if (!rating || count == null) return;
      const element = this.querySelector('[data-review-summary]');
      const summary = rating + '/' + count;
      if (element.dataset.value === summary) return;
      element.dataset.value = summary;
      const score = node('strong', '', rating + ' / 5');
      const stars = node('span', 'sc-reviews__summary-star', '★★★★★');
      const fill = node('span', 'sc-reviews__summary-fill', '★★★★★');
      const fraction = Math.min(5, Math.max(0, Number(rating.replace(',', '.')) || 0)) / 5;
      fill.style.inlineSize = fraction * 100 + '%';
      stars.append(fill);
      stars.setAttribute('aria-hidden', 'true');
      element.replaceChildren(stars, score, document.createTextNode(count + ' reviews'));
      element.hidden = false;
    }

    updateReadMore() {
      const changes = [];
      for (const body of this.inner.querySelectorAll('.sc-reviews__list .sc-reviews__body, .sc-reviews__row .sc-reviews__body')) {
        const more = body.nextElementSibling;
        if (!more?.matches('.sc-reviews__read-more')) continue;
        const title = body.previousElementSibling;
        const titleClipped = title?.matches('.sc-reviews__title') && title.scrollWidth > title.clientWidth + 1;
        const hidden = !titleClipped && body.scrollHeight <= body.clientHeight + 1;
        if (more.hidden !== hidden) changes.push([more, hidden]);
      }
      for (const [more, hidden] of changes) more.hidden = hidden;
    }

    updateArrows() {
      if (this.dataset.layout !== 'carousel') return;
      const scrollable = this.list.scrollWidth - this.list.clientWidth > 8;
      this.querySelector('[data-review-step="-1"]').hidden = !scrollable || (!this.hasWrapped && Math.abs(this.list.scrollLeft) < 8);
      this.querySelector('[data-review-step="1"]').hidden = !scrollable;
    }

    carouselGeometry() {
      const first = this.list.firstElementChild;
      const repeat = this.list.querySelector('[data-review-repeat]');
      if (!repeat || !first) return null;
      return {
        cycle: Math.abs(repeat.offsetLeft - first.offsetLeft),
        step: first.getBoundingClientRect().width + parseFloat(getComputedStyle(this.list).columnGap),
        direction: getComputedStyle(this.list).direction === 'rtl' ? -1 : 1
      };
    }

    wrapCarousel() {
      const geometry = this.carouselGeometry();
      const offset = Math.abs(this.list.scrollLeft);
      if (!geometry?.cycle || offset < geometry.cycle - 2) return;
      this.hasWrapped = true;
      this.list.scrollTo({ left: Math.max(0, offset - geometry.cycle) * geometry.direction, behavior: 'instant' });
      this.updateArrows();
    }

    render(reviews) {
      const key = JSON.stringify(reviews.map(({ country, ...review }) => review));
      if (key === this.reviewKey) return;
      const focusedIndex = document.activeElement?.dataset.reviewIndex;
      this.reviewKey = key;
      this.reviews = reviews;
      const cards = reviews.map((review, index) => {
        const card = node('button', 'sc-reviews__card');
        card.type = 'button';
        card.dataset.reviewIndex = index;
        const first = review.media[0];
        if (first) {
          const preview = node('div', 'sc-reviews__thumbnail');
          // This landscape photo shows two framed editions near the outer edges.
          if (review.id === '813945ea-267e-4f52-ab71-3a2c528ce98f' || first.full.includes('__1777871865832-ultimatemancavedecor__')) {
            preview.classList.add('sc-reviews__thumbnail--full');
          }
          if (review.id === rivalsReviewId) preview.classList.add('sc-reviews__thumbnail--rivals');
          if (first.thumb || !first.video) {
            const image = node('img');
            image.alt = '';
            const lead = this.formDialog && index === 0;
            image.loading = lead ? 'eager' : 'lazy';
            if (lead) image.fetchPriority = 'high';
            image.decoding = 'async';
            if (first.srcset) {
              image.sizes = lead ? '(max-width: 767px) 82vw, 340px' : 'auto, (max-width: 767px) 82vw, 400px';
              image.srcset = first.srcset;
            }
            image.src = first.thumb || first.full;
            preview.append(image);
          }
          if (first.video) preview.append(node('span', 'sc-reviews__video-label', '▶ Play video'));
          card.append(preview);
        }
        const copy = node('div', 'sc-reviews__card-copy');
        this.addReviewCopy(copy, review);
        card.append(copy);
        return card;
      });
      this.list.replaceChildren(...(cards.length ? cards : [node('p', 'sc-reviews__empty', 'No matching reviews on this page.')]));
      this.inner.hidden = false;
      this.classList.add('sc-reviews--ready');
      if (this.dataset.layout === 'carousel' && cards.length > 1) {
        const columns = Number(getComputedStyle(this).getPropertyValue('--scr-columns'));
        for (const card of cards.slice(0, Math.max(2, columns + 1))) {
          const repeat = card.cloneNode(true);
          repeat.dataset.reviewRepeat = '';
          repeat.tabIndex = -1;
          repeat.setAttribute('aria-hidden', 'true');
          this.list.append(repeat);
        }
      }
      this.updateReadMore();
      this.updateArrows();
      if (focusedIndex !== undefined) this.list.children[Number(focusedIndex)]?.focus({ preventScroll: true });
    }

    addReviewCopy(container, review, expanded = false) {
      const rating = Math.max(0, Math.min(5, Math.round(Number(review.rating) || 0)));
      if (rating) {
        const stars = node('span', 'sc-reviews__stars', '★'.repeat(rating) + '☆'.repeat(5 - rating));
        stars.setAttribute('role', 'img');
        stars.setAttribute('aria-label', rating + ' out of 5 stars');
        container.append(stars);
      }
      if (review.title) container.append(node(expanded ? 'h3' : 'strong', 'sc-reviews__title', review.title));
      if (review.body) {
        container.append(node('p', 'sc-reviews__body', review.body));
        if (!expanded) {
          const more = node('span', 'sc-reviews__read-more', 'Read more');
          more.hidden = true;
          container.append(more);
        }
      }
      const credit = node('div', 'sc-reviews__credit');
      credit.append(node('strong', 'sc-reviews__name', review.name));
      const verified = node('span', 'sc-reviews__verified');
      const tick = node('span', 'sc-reviews__tick', '✓');
      tick.setAttribute('aria-hidden', 'true');
      verified.append(tick, document.createTextNode('Verified buyer'));
      if (review.verified || review.shopVerified) credit.append(verified);
      container.append(credit);
    }

    handleClick(event) {
      const button = event.target.closest('button');
      if (this.formDialog && (event.target === this.formDialog || button?.matches('[data-review-form-close]'))) {
        this.formDialog.close();
        return;
      }
      if (!button || !this.inner.contains(button)) {
        if (event.target === this.dialog) this.dialog.close();
        return;
      }
      const { reviewIndex, archiveIndex, archivePhoto, reviewStep, mediaStep } = button.dataset;
      if (reviewIndex !== undefined || archiveIndex !== undefined) {
        this.opener = button;
        this.current = archiveIndex === undefined ? this.reviews[Number(reviewIndex)] : this.archiveReviews[Number(archiveIndex)];
        this.mediaIndex = Number(archivePhoto ?? 0);
        const detail = this.querySelector('[data-review-detail]');
        detail.replaceChildren();
        this.addReviewCopy(detail, this.current, true);
        if (archiveIndex !== undefined && archivePhoto === undefined) {
          this.querySelector('[data-review-media]').parentElement.hidden = true;
        } else {
          this.renderMedia();
        }
        this.dialog.showModal();
      } else if (reviewStep) {
        const geometry = this.carouselGeometry();
        if (!geometry) return;
        const { cycle, step, direction } = geometry;
        const offset = Math.abs(this.list.scrollLeft);
        const backAcrossStart = Number(reviewStep) < 0 && this.hasWrapped && offset < 8;
        const target = backAcrossStart ? cycle - step : offset + Number(reviewStep) * step;
        this.list.scrollTo({
          left: target * direction,
          behavior: backAcrossStart || matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'
        });
      } else if (mediaStep) {
        const count = this.current.media.length;
        this.mediaIndex = (this.mediaIndex + Number(mediaStep) + count) % count;
        this.renderMedia();
      } else if (button.matches('.sc-reviews__close')) {
        this.dialog.close();
      } else if (button.matches('[data-review-more]')) {
        if (this.archive) this.loadArchiveBatch();
      } else if (button.matches('[data-review-write]')) {
        const url = new URL('https://sports-cave-image-factory.onrender.com/reviews/write');
        if (this.dataset.product) url.searchParams.set('product', this.dataset.product);
        if (!this.formDialog) { window.location.assign(url.href); return; }
        const frame = document.createElement('iframe');
        frame.title = 'Write your Sports Cave review'; frame.src = url.href;
        frame.style.cssText = 'display:block;width:100%;height:65dvh;border:0';
        const status = node('p', '', 'Loading review form…');
        status.setAttribute('role', 'status');
        frame.addEventListener('load', () => { status.hidden = true; }, {once:true});
        this.querySelector('[data-review-form-host]').replaceChildren(status, frame);
        this.formDialog.showModal();
        this.querySelector('[data-review-form-close]').focus({preventScroll:true});
      }
    }

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
    const data = await entry.request;
    this.nativeSummary(data.summary);
    return data;
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
      date: review.created_at, product: review.product_title, productThumb: /^https:\/\/(cdn\.shopify\.com|www\.sportscaveshop\.com|sportscaveshop\.com)\//.test(review.product_thumbnail_url || '') ? review.product_thumbnail_url : '', productUrl: /^https:\/\/(www\.)?sportscaveshop\.com\//.test(review.product_url || '') ? review.product_url : '', shopVerified: review.shop_verified === true, verified: review.verified_purchase || review.source_verified,
      media: (review.media || []).filter(media => media.kind === 'image' || media.kind === 'video').map(media => ({
        full: owned(media.url), video: media.kind === 'video', thumb: owned(media.thumbnail_url), width: media.width, height: media.height,
        srcset: owned(media.carousel_url) ? `${owned(media.thumbnail_url)} 320w, ${owned(media.carousel_url)} 640w` : `${owned(media.thumbnail_url)} 320w`
      })).filter(media => media.full && media.thumb)}));
  }

  nativeSummary(summary) {
    if (!Number.isSafeInteger(summary?.count) || summary.count < 0) return;
    document.querySelectorAll('sc-customer-reviews').forEach(widget => widget.summary(Number(summary.average || 0).toFixed(2), String(summary.count)));
    document.querySelectorAll('.scx-review-text').forEach(target => {
      const rating = target.querySelector('strong'), count = target.querySelector('span:last-child');
      if (rating) rating.textContent = Number(summary.average || 0).toFixed(1);
      if (count) count.textContent = `${summary.count} reviews`;
    });
  }

  nativeApply(data, append = false) {
    if (!this.controller || this.controller.signal.aborted) return;
    this.nativeSummary(data.summary);
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

  });
})();

// One small first-page request supplies badge data and primes the below-fold widget.
// Remaining pages wait until the review section approaches the viewport.
customElements.whenDefined('sc-customer-reviews').then(() => {
  document.querySelector('sc-customer-reviews')?.nativeFeed().catch(() => {});
});
