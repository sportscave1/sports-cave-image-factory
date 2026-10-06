/* App privacy only. Native capture exclusion is separate. */
(() => {
  const policy=SC_POLICY;
  const name=SC_NAME;
  const doc=document;
  if(window.__scAppPrivacy){window.__scAppPrivacy.update(policy,name);return;}
  let cfg=policy,user=name,lastActivity=Date.now(),lastSent=0,locked=false,idleDeadline;
  const editable=t => t instanceof Element && t.closest('input,textarea,select,[contenteditable="true"],[role="textbox"]');
  const protectedTarget=t => t instanceof Element && t.closest('[data-sc-protected],.sc-protected-artwork');
  const style=doc.createElement('style');style.id='sc-app-privacy-style';doc.head.appendChild(style);
  const shade=doc.createElement('div');shade.id='sc-app-privacy-shade';shade.hidden=false;
  shade.style.cssText='position:fixed;inset:0;background:#171714;z-index:2147483600;display:none;align-items:center;justify-content:center;color:#f7f4ee;font:16px sans-serif';
  shade.textContent='Sports Cave OS · Protected content';doc.body.appendChild(shade);
  const watermark=doc.createElement('div');watermark.style.cssText='position:fixed;inset:0;pointer-events:none;z-index:2147483500;opacity:.08;display:none;overflow:hidden';doc.body.appendChild(watermark);
  function markArtwork(){
    doc.querySelectorAll('[data-testid="stImage"] img').forEach(image=>{
      if(!image.closest('.st-key-files-explorer'))image.setAttribute('data-sc-protected','');
    });
  }
  let marking;
  new MutationObserver(records=>{if(records.some(record=>record.addedNodes.length)){clearTimeout(marking);marking=setTimeout(markArtwork,150);}}).observe(doc.body,{childList:true,subtree:true});
  markArtwork();
  function armIdle(){clearTimeout(idleDeadline);if(cfg.autoLockMinutes && !locked)idleDeadline=setTimeout(lock,Math.max(0,cfg.autoLockMinutes*60000-(Date.now()-lastActivity)));}
  function update(value,displayName){
    cfg=value;user=displayName;armIdle();
    style.textContent=(cfg.appSelection?'[data-sc-protected],.sc-protected-artwork{user-select:none}':'')+(cfg.appPrinting?'@media print{[data-sc-protected],.sc-protected-artwork{visibility:hidden!important}}':'');
    watermark.style.display=cfg.appWatermark?'grid':'none';watermark.style.gridTemplateColumns='repeat(3,1fr)';
    watermark.replaceChildren();
    if(cfg.appWatermark)for(let i=0;9>i;i++){const line=doc.createElement('span');line.textContent=`SPORTS CAVE OS • ${user} • ${new Date().toLocaleString()}`;line.style.transform='rotate(-25deg)';watermark.appendChild(line);}
  }
  function obscure(){shade.style.display=(locked || (cfg.blurOnFocusLoss && (doc.hidden || !doc.hasFocus())))?'flex':'none';}
  function lock(){if(locked)return;locked=true;clearTimeout(idleDeadline);obscure();fetch('/api/os/security/session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"action":"lock"}'}).catch(()=>{});shade.replaceChildren();const box=doc.createElement('form');
    const label=doc.createElement('p');label.textContent='Session locked · Verify your password';
    const input=doc.createElement('input');input.type='password';input.autocomplete='current-password';input.setAttribute('aria-label','Current password');
    const button=doc.createElement('button');button.type='submit';button.textContent='Unlock';box.append(label,input,button);shade.appendChild(box);
    box.addEventListener('submit',async e => {e.preventDefault();button.disabled=true;try{
      const response=await fetch('/api/os/security/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'reauth',password:input.value})});input.value='';
      const result=await response.json();if(!response.ok)throw new Error(result.error || 'Verification unavailable.');locked=false;lastActivity=Date.now();armIdle();obscure();
    }catch(error){label.textContent=error.message;}finally{button.disabled=false;}});
    input.focus();
  }
  for(const event of ['pointerdown','keydown','wheel'])doc.addEventListener(event,()=>{if(!locked){lastActivity=Date.now();armIdle();}},{passive:true});
  doc.addEventListener('contextmenu',e => {if(cfg.appRightClick && !editable(e.target) && protectedTarget(e.target))e.preventDefault();});
  doc.addEventListener('dragstart',e => {if(cfg.appImageDragging && !editable(e.target) && protectedTarget(e.target))e.preventDefault();});
  doc.addEventListener('copy',e=>{if(cfg.appCopyDeterrence && !editable(e.target) && protectedTarget(e.target))e.preventDefault();});
  doc.addEventListener('visibilitychange',obscure);window.addEventListener('blur',obscure);window.addEventListener('focus',obscure);
  setInterval(async () => {
    if(locked)return;
    if(cfg.autoLockMinutes && Date.now()-lastActivity>=cfg.autoLockMinutes*60000){lock();return;}
    if(doc.hidden || lastActivity===lastSent)return;
    lastSent=lastActivity;
    try {const response=await fetch('/api/os/security/session',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"action":"activity"}'});if(response.status===423)lock();}catch(_){}
  },30000);
  window.__scAppPrivacy={update};update(cfg,user);
})();
