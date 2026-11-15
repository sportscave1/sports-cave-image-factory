(()=>{
 if(window.scCampaignTestSections)return;
 window.scCampaignTestSections=true;
 document.addEventListener('keydown',e=>{
  if(e.key!=='Escape'||!e.target.closest('[data-testid="stPopoverBody"]'))return;
  // Let the native popover close; restore keyboard focus without moving the page.
  setTimeout(()=>{
   const trigger=[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('Send test')&&!b.closest('[data-testid="stPopoverBody"]'));
   trigger?.focus({preventScroll:true});
  },150);
 },true);
 document.addEventListener('click',async e=>{
  const action=e.target.closest('[data-crm-section]');if(!action)return;
  e.preventDefault();e.stopPropagation();
  const id=action.dataset.crmSection;
  const trigger=[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('Send test')&&!b.closest('[data-testid="stPopoverBody"]'));
  trigger?.click();
  const editorTab=[...document.querySelectorAll('[role="tab"]')].find(t=>t.textContent.trim()==='Editor');editorTab?.click();
  const started=Date.now();
  const go=()=>{
   if(window.scCampaignGoToSection?.(id))return;
   // Avoid a literal less-than in inline script HTML.
   if(3000>Date.now()-started)setTimeout(go,40);
  };go();
 },true);
})();
