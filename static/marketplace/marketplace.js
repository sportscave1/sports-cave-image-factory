'use strict';
(() => {
  for (const gallery of document.querySelectorAll('[data-gallery]')) {
    const panels = Array.from(gallery.querySelectorAll('[data-media-panel]'));
    const links = Array.from(gallery.querySelectorAll('[data-media-target]'));
    const caption = gallery.querySelector('[data-media-caption]');
    const photos = panels.filter(panel => !panel.querySelector('video')).length;
    function show(index) {
      panels.forEach((panel, i) => {
        panel.hidden = i !== index;
        const video = panel.querySelector('video');
        if (video && i !== index) video.pause();
        if (i === index) links[i].setAttribute('aria-current', 'true');
        else links[i].removeAttribute('aria-current');
      });
      caption.textContent = panels[index].querySelector('video') ? 'Recorded item video' : `Photo ${index + 1} of ${photos}`;
    }
    links.forEach((link, index) => {
      link.addEventListener('click', event => { event.preventDefault(); show(index); });
      link.addEventListener('keydown', event => {
        let target = index;
        if (event.key === 'ArrowRight') target = (index + 1) % links.length;
        else if (event.key === 'ArrowLeft') target = (index + links.length - 1) % links.length;
        else if (event.key === 'Home') target = 0;
        else if (event.key === 'End') target = links.length - 1;
        else return;
        event.preventDefault();
        show(target);
        links[target].focus();
      });
    });
    show(0);
  }
  const videoInput = document.querySelector('#video');
  if (videoInput) videoInput.addEventListener('change', () => {
    const file = videoInput.files[0];
    videoInput.setCustomValidity(file && file.size > 15000000 ? 'Choose a video up to 15 MB.' : '');
    document.querySelector('#video-selection').textContent = file
      ? `${file.name} · ${(file.size / 1000000).toFixed(1)} MB${file.size > 15000000 ? ' — choose a smaller clip.' : ''}` : '';
  });
  const price = document.querySelector('#price');
  if (price) price.addEventListener('input', () => {
    const value = Number(price.value);
    const quote = document.querySelector('#fee-quote');
    if (!Number.isFinite(value) || value < 10 || value > 50000) {
      quote.textContent = 'Founding offer: free listings. Planned seller fee: 5% on a completed sale.';
      return;
    }
    const cents = Math.round(value * 100);
    const fee = Math.round(cents * 5 / 100);
    const fmt = n => 'A$' + (n / 100).toLocaleString('en-AU', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    quote.textContent = `Indicative: ${fmt(cents)} sale − ${fmt(fee)} seller fee = ${fmt(cents - fee)} to you, plus postage.`;
  });

  function readPhoto(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',')[1]);
      reader.onerror = () => reject(new Error('A photograph could not be read. Please select it again.'));
      reader.readAsDataURL(file);
    });
  }

  for (const form of document.querySelectorAll('form[data-endpoint]')) {
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = form.querySelector('button[type=submit]');
      const status = form.querySelector('.form-status');
      if (button.disabled) return;
      button.disabled = true;
      status.textContent = 'Sending…';
      status.removeAttribute('data-error');
      try {
        const data = Object.fromEntries(new FormData(form).entries());
        data.consent = form.elements.consent.checked;
        if (form.id === 'seller-form') {
          const photos = Array.from(form.elements.photos.files);
          if (photos.length < 2 || photos.length > 4) throw new Error('Choose 2–4 photographs.');
          if (photos.some(file => file.size > 2000000 || !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
            throw new Error('Use JPG, PNG or WebP photographs, up to 2 MB each.');
          }
          data.photos = await Promise.all(photos.map(readPhoto));
          const video = form.elements.video.files[0];
          if (video && video.size > 15000000) throw new Error('Choose a video up to 15 MB and 60 seconds.');
          data.video = video ? await readPhoto(video) : '';
          status.textContent = video ? 'Uploading and preparing your video… This can take a minute.' : 'Sending your photographs…';
        }
        const response = await fetch(form.dataset.endpoint, {method: 'POST', credentials: 'omit',
          headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Please try again shortly.');
        const panel = document.createElement('section');
        panel.className = 'success-panel';
        panel.setAttribute('role', 'status');
        const title = document.createElement('h2');
        title.textContent = form.id === 'seller-form' ? 'You’re in the review queue.' : 'Enquiry received.';
        const text = document.createElement('p');
        text.textContent = form.id === 'seller-form'
          ? 'Sports Cave will review your item and contact you using the email you supplied. Nothing is public until approved.'
          : 'Sports Cave will review your question with the seller. This enquiry does not reserve the item.';
        const reference = document.createElement('p');
        reference.textContent = 'Reference: ' + result.reference;
        const back = document.createElement('a');
        back.href = '/marketplace';
        back.textContent = 'Back to the marketplace';
        panel.append(title, text, reference, back);
        form.replaceWith(panel);
        panel.tabIndex = -1;
        panel.focus();
      } catch (error) {
        status.dataset.error = 'true';
        status.textContent = error instanceof TypeError
          ? 'Connection interrupted. Check your connection before trying again; your submission may have arrived.'
          : error.message;
        button.disabled = false;
      }
    });
  }
})();
