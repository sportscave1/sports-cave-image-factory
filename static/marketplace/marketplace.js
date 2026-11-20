'use strict';
(() => {
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
