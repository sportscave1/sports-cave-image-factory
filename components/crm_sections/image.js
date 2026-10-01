/* Local-only controls. Never emit a Streamlit event, save, send or upload. */
function imageAdvice(source){
 if(!source.trim())return '';
 const doc=new DOMParser().parseFromString(source,'text/html'),images=[...doc.querySelectorAll('img')],issues=new Set();
 if(!images.length)return '⚠ No image found';
 for(const img of images){
  const src=img.getAttribute('src')||'';
  try{const url=new URL(src);if(url.protocol!=='https:'||url.username||url.password||/\s/.test(src))throw Error();}
  catch{issues.add(/^data:/i.test(src)?'Data/base64 images are not supported':'Use a valid HTTPS image URL');}
  if(!img.hasAttribute('alt'))issues.add('Missing alt text');
  else if(!img.alt.trim())issues.add('Add alt text for meaningful images');
  if(!/^\d+$/.test(img.getAttribute('width')||''))issues.add('Consider a numeric width attribute');
  if(img.style.height!=='auto'||!(img.style.width==='100%'||img.style.maxWidth==='100%'))issues.add('Check responsive width and height:auto');
 }
 for(const node of doc.querySelectorAll('table,td,div,img')){
  const fixed=parseFloat(node.style.minWidth)||0;
  const width=parseFloat(node.style.width||node.getAttribute('width'))||0;
  if(fixed>320||(width>320&&!String(node.style.width||node.getAttribute('width')).includes('%')&&node.style.maxWidth!=='100%'))issues.add('Check fixed-width mobile overflow');
 }
 return issues.size?'⚠ '+[...issues].join(' · '):'✓ HTTPS image · Alt text · Responsive';
}
function imageControls(row,prompt){
 const copy=document.createElement('button');copy.type='button';copy.className='image-copy';copy.textContent='Copy prompt';copy.setAttribute('aria-label','Copy image prompt');
 const help=document.createElement('button');help.type='button';help.className='image-help';help.textContent='?';help.setAttribute('aria-label','How to add an image');help.setAttribute('aria-expanded','false');
 const popup=document.createElement('div');popup.className='image-popover';popup.setAttribute('popover','auto');popup.id='image-help-'+crypto.randomUUID();help.setAttribute('aria-controls',popup.id);
 const heading=document.createElement('strong');heading.textContent='How to add an image';popup.append(heading);
 const list=document.createElement('ol');for(const text of ['Click Copy prompt.','Paste the prompt into ChatGPT.','Attach the image you want to use.','ChatGPT will prepare the image for Shopify and return email-ready HTML.','Copy that HTML back into this Image section.','Check the email preview before sending.']){const item=document.createElement('li');item.textContent=text;list.append(item);}popup.append(list);
 const note=document.createElement('p');note.textContent='Sports Cave OS does not upload the image itself. The copied prompt handles the Shopify + ChatGPT workflow.';popup.append(note);
 popup.addEventListener('toggle',()=>help.setAttribute('aria-expanded',String(popup.matches(':popover-open'))));
 const show=()=>{const r=help.getBoundingClientRect();popup.style.top=Math.min(r.bottom+4,Math.max(8,innerHeight-250))+'px';popup.style.left=Math.max(8,Math.min(r.right-300,innerWidth-316))+'px';popup.showPopover();help.setAttribute('aria-expanded','true');};
 help.onclick=()=>{if(popup.matches(':popover-open'))popup.hidePopover();else show();};
 row.addEventListener('keydown',e=>{if(e.key==='Escape'&&popup.matches(':popover-open')){e.preventDefault();popup.hidePopover();help.setAttribute('aria-expanded','false');help.focus({preventScroll:true});}});
 const fallback=document.createElement('div');fallback.className='image-copy-fallback';fallback.hidden=true;
 const message=document.createElement('span');message.textContent='Clipboard unavailable. Select and copy the prompt below.';
 const text=document.createElement('textarea');text.readOnly=true;text.value=prompt;text.setAttribute('aria-label','Image prompt for manual copying');fallback.append(message,text);
 copy.setAttribute('aria-live','polite');
 copy.onclick=async()=>{const copied=await window.scCopyText(prompt);if(copied){fallback.hidden=true;copy.textContent='✓ Prompt copied';setTimeout(()=>{copy.textContent='Copy prompt';},1800);}else{fallback.hidden=false;show();}};
 popup.append(fallback);row.append(copy,help,popup);
}
if(typeof window!=='undefined')window.addEventListener('blur',()=>document.querySelectorAll('.image-popover:popover-open').forEach(p=>p.hidePopover()));
if(typeof module!=='undefined')module.exports={imageAdvice,imageControls};
