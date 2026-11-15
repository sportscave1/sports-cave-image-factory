/* Local editing only. Native input/blur remains the save authority. */
window.scInstallPersonalisation = function(keys) {
 const choices=[['First name','first_name'],['Product name','product_name'],['Short product name','short_product_name'],['Sport / category','sport_category'],['Edition number','edition_number'],['Discount code','discount_code'],['Discount value','discount_value']];
 for(const key of keys){
  const root=document.querySelector('.'+CSS.escape('st-key-'+key)),input=root?.querySelector('input');
  if(!input||root.querySelector('[data-personalise]'))continue;
  const button=document.createElement('button'),menu=document.createElement('div');
  button.type='button';button.textContent='+ Personalise';button.dataset.personalise='true';button.className='sc-personalise-trigger';
  button.setAttribute('aria-label','Personalise '+(input.getAttribute('aria-label')||'email field'));button.setAttribute('aria-haspopup','menu');button.setAttribute('aria-expanded','false');
  menu.className='sc-personalise-menu';menu.setAttribute('popover','auto');menu.setAttribute('role','menu');
  let selection=[input.value.length,input.value.length];
  const remember=()=>{selection=[input.selectionStart,input.selectionEnd];};
  for(const name of ['select','keyup','click','input','blur'])input.addEventListener(name,remember);
  button.onpointerdown=e=>{if(document.activeElement===input)remember();e.preventDefault();};
  menu.addEventListener('toggle',()=>button.setAttribute('aria-expanded',String(menu.matches(':popover-open'))));
  const close=()=>{menu.hidePopover();input.focus({preventScroll:true});input.setSelectionRange(...selection);};
  button.onclick=()=>{if(menu.matches(':popover-open')){close();return;}const r=button.getBoundingClientRect();menu.style.left=Math.max(4,Math.min(r.left,innerWidth-210))+'px';menu.style.top=Math.max(4,Math.min(r.bottom+3,innerHeight-265))+'px';menu.showPopover();menu.firstElementChild.focus();};
  for(const [label,variable] of choices){const item=document.createElement('button');item.type='button';item.textContent=label;item.setAttribute('role','menuitem');
   if(variable==='edition_number')item.title='Before purchase use: Next available edition: {{edition_number}}';
   item.onpointerdown=e=>e.preventDefault();item.onclick=()=>{const token='{{'+variable+'}}';if(input.maxLength>0&&input.value.length-(selection[1]-selection[0])+token.length>input.maxLength){input.setCustomValidity('Not enough room for this variable. Shorten the field first.');input.reportValidity();return;}
    close();input.setCustomValidity('');document.execCommand('insertText',false,token);remember();};menu.append(item);}
  menu.onkeydown=e=>{const items=[...menu.children],index=items.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();close();}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();items[e.key==='Home'?0:e.key==='End'?items.length-1:(index+(e.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}};
  root.style.position='relative';root.append(button,menu);
 }
};
