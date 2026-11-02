(()=>{
  const b=document.querySelector('[role="dialog"] .st-key-crm-review-submit button');
  if(!b||b.dataset.acceptFeedback)return;
  b.dataset.acceptFeedback='true';
  b.addEventListener('click',event=>{
    if(b.dataset.submitting){event.preventDefault();event.stopImmediatePropagation();return;}
    b.dataset.submitting='true';
    b.setAttribute('aria-busy','true');b.style.opacity='.65';
    const note=document.createElement('small');note.textContent='Submitting…';
    note.setAttribute('role','status');b.after(note);
    // React's delegated handler must receive the first enabled click before
    // disabling the native control. Microtasks can run between event listeners.
    setTimeout(()=>{if(b.isConnected)b.disabled=true;},0);
  },true);
})();
