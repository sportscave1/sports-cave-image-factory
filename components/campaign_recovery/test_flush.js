/* Local submission barrier. Never sends or saves directly; waits for existing bridges. */
(()=>{
 if(window.scCampaignTestFlush)return;
 window.scCampaignTestFlush=true;
 let busy=false,allowed=null;
 const intercept=async e=>{
  const form=e.target.closest('[data-testid="stForm"],form');
  if(!form?.querySelector('input[aria-label="Send test email"]'))return;
  if(e.type==='keydown'&&(e.key!=='Enter'||e.isComposing||e.shiftKey))return;
  const button=e.type==='click'?e.target.closest('button[type="submit"],button[data-testid$="FormSubmit"]'):(e.submitter||form.querySelector('button[type="submit"],button[data-testid$="FormSubmit"]'));
  if(e.type==='click'&&!button)return;
  if(allowed===form)return;
  e.preventDefault();e.stopImmediatePropagation();
  if(busy)return;
  busy=true;
  const input=form.querySelector('input[aria-label="Send test email"]');
  const inputId=input.id,recipient=input.value;
  let status=form.querySelector('[data-test-sync]');
  if(!status){status=document.createElement('div');status.dataset.testSync='';status.setAttribute('role','status');form.append(status);}
  status.textContent='Checking latest edits…';
  try{
   // Existing blur handlers flush catalogue controls; content waits for ack below.
   document.activeElement?.blur();
   await window.scCampaignFlushSections?.();
   await window.scCampaignFlushRecovery?.();
   const currentInput=document.getElementById(inputId);
   const currentForm=currentInput?.closest('[data-testid="stForm"],form');
   const currentButton=currentForm?.querySelector('button[type="submit"],button[data-testid$="FormSubmit"]');
   if(!currentForm||currentInput.value!==recipient||!currentButton||currentButton.disabled)throw new Error('Test control changed.');
   status.textContent='';allowed=currentForm;
   try{currentButton.click();}
   finally{allowed=null;}
  }catch{status.textContent='Latest edits could not be synchronized. Reopen Send test and retry; no test was sent.';}
  finally{busy=false;}
 };
 document.addEventListener('click',intercept,true);
 document.addEventListener('submit',intercept,true);
 document.addEventListener('keydown',intercept,true);
})();
