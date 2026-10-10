/* Dependency-free middle-only sorting. Header/Footer never enter this component. */
function moveId(ids,id,target){const result=[...ids],a=result.indexOf(id),b=result.indexOf(target);if(a<0||b<0)return result;result.splice(a,1);result.splice(b,0,id);return result;}
if(typeof module!=='undefined')module.exports={moveId};
if(typeof document!=='undefined'){
let args={sections:[]},opened={},pending=false,inFlight=null,drag=null,typing=null,drafts={},queue=[],settingsDrafts={};
const root=document.getElementById('sections');
// Optional same-origin OS hooks must never prevent the Streamlit handshake.
const withParent=fn=>{try{return fn(parent);}catch{return undefined;}};
const signalPending=detail=>withParent(p=>p.dispatchEvent(new CustomEvent('sc-campaign-pending',{detail:{...detail,local_editor:true}})));
const pendingCopyInputs=new Map();
const goToSection=id=>{
 if(!args.sections.some(s=>s.id===id))return false;
 opened[id]=true;render();
 requestAnimationFrame(()=>{
  const card=[...root.children].find(c=>c.dataset.id===id);
  card?.scrollIntoView({block:'center'});
  card?.querySelector('.title')?.focus({preventScroll:true});
 });return true;
};
withParent(p=>p.scCampaignGoToSection=goToSection);
addEventListener('pagehide',()=>{withParent(p=>{if(p.scCampaignGoToSection===goToSection)delete p.scCampaignGoToSection;});});
const areas=new Map(),histories=new Map();let historyScope='',deleted=null,deleteTimer=null;

const height=()=>parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:document.body.scrollHeight+4},'*');
let changes=[],sent=[],unpersisted=[],saveTimer,saveError='',saveAttempts=0,external=[],previewTimer;
const copy=v=>JSON.parse(JSON.stringify(v));
const localPreview=()=>{clearTimeout(previewTimer);if(args.preview_scope)SCPreview.publish(args.preview_scope,args.sections,!!(pending||changes.length||Object.keys(drafts).length||saveError));};
const saveStatus=text=>{let n=document.getElementById('local-save-status');if(!n){n=el('div','','local-save-status');n.id='local-save-status';n.setAttribute('role','status');document.body.append(n);}n.textContent=text;withParent(p=>{const status=p.document.getElementById('sc-campaign-save-status');if(status)status.textContent=text;});height();};
function transmit(type,extra={}){pending=true;inFlight=crypto.randomUUID();saveStatus('Saving…');parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{event:inFlight,base:args.sections.map(s=>s.id),type,...extra}},'*');}
function sendChanges(){clearTimeout(saveTimer);if(pending)return;if(changes.length){sent=changes.splice(0);transmit('batch',{base:sent[0].base,events:sent});}else if(external.length){const [type,extra]=external.shift();transmit(type,extra);}else if(saveError){transmit('persist');}}
function rememberDraft(){try{sessionStorage.setItem('sc-local-draft:'+historyScope,JSON.stringify({sections:args.sections,changes:[...unpersisted,...sent,...changes],version:args.draft_version}));}catch{}}
const dirty=()=>{saveError='';saveAttempts=0;saveStatus('Unsaved · Unpublished changes');withParent(p=>{const size=p.document.querySelector('.st-key-crm-composer-preview .sc-email-size');if(size){size.dataset.lastMeasured??=size.innerHTML;size.textContent='Email size · Recalculates after draft save';}});rememberDraft();clearTimeout(saveTimer);saveTimer=setTimeout(sendChanges,650);signalPending({local:true});};
function emit(type,extra={}){
 if(!['html','settings'].includes(type))for(const commit of [...pendingCopyInputs.values()])commit();
 const local=['html','settings','visible','order','rename','duplicate','remove','restore_section','product_order','product_remove'].includes(type)||(type==='add'&&(['html','image','discount','catalogue','visual','flexible_checkout'].includes(extra.kind)||extra.kind==='checkout'&&args.checkout_template||extra.kind==='template'&&args.templates.some(t=>t.id===extra.template_id&&typeof t.html==='string')));
 if(!local){external.push([type,extra]);sendChanges();return;}
 const event={type,...copy(extra),base:args.sections.map(s=>s.id),edits:copy(drafts)};
 for(const s of args.sections)if(Object.hasOwn(drafts,s.id)){s.html=drafts[s.id];s.css_version=1;}
 const s=args.sections.find(v=>v.id===extra.id),index=args.sections.indexOf(s);
 if(type==='html'&&s){s.html=extra.html;s.css_version=1;}
 if(type==='settings'&&s)s.settings=copy(extra.settings);
 if(type==='visible'&&s)s.visible=extra.visible;
 if(type==='rename'&&s)s.name=extra.reset?'':extra.name;
 if(type==='order')args.sections=extra.ids.map(id=>args.sections.find(s=>s.id===id));
 if(type==='remove')args.sections.splice(index,1);
 if(type==='restore_section')args.sections.splice(Math.min(extra.position,args.sections.length),0,copy(extra.section));
 if(type==='duplicate'){const duplicated=copy(s);event.new_id=crypto.randomUUID();duplicated.id=event.new_id;if(s.type==='html')duplicated.html_number=Math.max(...args.sections.map(v=>v.html_number||0))+1;args.sections.splice(index+1,0,duplicated);}
 if(type==='product_remove'&&s)s.products=s.products.filter(v=>v.id!==extra.product_id);
 if(type==='product_order'&&s)s.products=extra.ids.map(id=>s.products.find(p=>p.id===id));
 if(type==='add'){
  event.new_id=crypto.randomUUID();const created={id:event.new_id,type:extra.kind==='visual'?'checkout_element':extra.kind,visible:true};
  if(extra.kind==='html'){created.html_number=Math.max(extra.reserved_html_number||0,...args.sections.map(s=>s.html_number||0))+1;created.html='';}
  if(extra.kind==='image')created.html='';
  if(extra.kind==='discount'){created.html=args.discount_html;created.offer=copy(args.discount_offer||null);}
  if(extra.kind==='catalogue'){created.products=[];created.settings={headline:'',subtext:'',columns:2,display:Object.fromEntries(['image','title','price','limit','next','remaining','cta'].map(k=>[k,k!=='price'])),cta:'Claim Your Edition'};}
  if(extra.kind==='visual')created.settings=copy(args.element_defaults);
  if(extra.kind==='template'||extra.kind==='checkout'){
   const template=extra.kind==='checkout'?{...args.checkout_template,name:'Abandoned Checkout',builtin:true}:args.templates.find(t=>t.id===extra.template_id);
   created.type='html';created.html=template.html;created.html_number=Math.max(0,...args.sections.map(s=>s.html_number||0))+1;if(template.builtin)created.name=template.name;
   if(args.sections.length===1&&args.sections[0].type==='html'&&!args.sections[0].html.trim()){
    if(extra.kind==='template'){created.id=args.sections[0].id;created.html_number=args.sections[0].html_number;}
    else created.html_number=1;
    args.sections=[];
   }
  }
  if(extra.kind==='flexible_checkout'){const starter=copy(args.starter_sections);event.new_ids=starter.map(s=>s.id=crypto.randomUUID());args.sections.push(...starter);}
  else if(extra.kind==='template'&&Array.isArray(args.templates.find(t=>t.id===extra.template_id)?.sections)){
   const incoming=copy(args.templates.find(t=>t.id===extra.template_id).sections);let number=Math.max(0,...args.sections.map(s=>s.html_number||0));
   event.new_ids=incoming.map(part=>{part.id=crypto.randomUUID();if(part.type==='html')part.html_number=++number;if(part.type==='discount')part.offer=copy(args.discount_offer||null);if(Object.hasOwn(part,'html'))part.css_version=1;return part.id;});args.sections.push(...incoming);
  }
  else{if(Object.hasOwn(created,'html'))created.css_version=1;args.sections.push(created);opened[created.id]=true;}
 }
 // Supersede field edits within the same structure. This also lets a corrected
 // invalid field recover without replaying its obsolete invalid intermediate.
 const supersedes=['html','settings','visible','rename'].includes(type)?changes.findLastIndex(v=>v.type===type&&v.id===event.id&&JSON.stringify(v.base)===JSON.stringify(event.base)):-1;
 if(supersedes>=0)changes[supersedes]=event;else changes.push(event);
 drafts={};settingsDrafts={};localPreview();render();dirty();
}
addEventListener('beforeunload',event=>{if(pending||changes.length||Object.keys(drafts).length||saveError){rememberDraft();event.preventDefault();event.returnValue='';}});
// Send test must wait for the server acknowledgement, not merely textarea blur.
const flushSections=()=>new Promise((resolve,reject)=>{
 const started=Date.now(),scope=historyScope;
 const check=()=>{
  if(scope!==historyScope||Date.now()-started>10000)return reject(new Error('Section changes could not be synchronized. Retry after saving.'));
  const invalid=root.querySelector('.visual-fields input:invalid,.visual-fields textarea:invalid');if(invalid){invalid.reportValidity();return reject(new Error('Correct invalid element settings before saving or sending.'));}
  for(const commit of [...pendingCopyInputs.values()])commit();
  for(const area of areas.values())clearTimeout(area.saveTimer);
  const entry=Object.entries(drafts)[0];
  if(entry)emit('html',{id:entry[0],html:entry[1]});
  if(saveError&&!pending)return reject(new Error(saveError));
  sendChanges();
  if(!pending&&!changes.length&&!entry&&!external.length&&!Object.keys(settingsDrafts).length)return resolve();
  setTimeout(check,30);
 };check();
});
withParent(p=>p.scCampaignFlushSections=flushSections);
addEventListener('pagehide',()=>{withParent(p=>{if(p.scCampaignFlushSections===flushSections)delete p.scCampaignFlushSections;});});
// Internal navigation does not fire beforeunload. Flush before unmounting the
// authoring component; a failed save leaves it open with its local state intact.
let replayNavigation=false;
const navigationGuard=async e=>{
 if(replayNavigation||!(pending||changes.length||Object.keys(drafts).length||saveError))return;
 const target=e.target.closest('a,button,[role="tab"],[role="option"]');if(!target)return;
 const text=target.textContent.trim();
 if(!(target.matches('a')||target.getAttribute('role')==='option'||target.getAttribute('role')==='tab'||['Flow','← Automations'].includes(text)))return;
 e.preventDefault();e.stopImmediatePropagation();
 try{await flushSections();replayNavigation=true;target.click();}catch(error){saveStatus(error.message);}finally{replayNavigation=false;}
};
withParent(p=>p.document.addEventListener('click',navigationGuard,true));
addEventListener('pagehide',()=>withParent(p=>p.document.removeEventListener('click',navigationGuard,true)));
const el=(tag,text='',cls='')=>{let n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
function button(text,label,fn,cls=''){let n=el('button',text,cls);n.type='button';n.title=label;n.setAttribute('aria-label',label);n.onclick=fn;return n;}
function placeCards(ids){ids.forEach((id,index)=>{const card=[...root.children].find(c=>c.dataset.id===id);if(card&&root.children[index]!==card){if(root.moveBefore)root.moveBefore(card,root.children[index]||null);else root.insertBefore(card,root.children[index]||null);}});}
function historyFor(id,value){if(!histories.has(id)){let saved;try{saved=JSON.parse(sessionStorage.getItem('sc-section-history:'+historyScope+':'+id));}catch{}histories.set(id,new SectionHistory(value,saved));}return histories.get(id);}
function remember(id,value){const history=historyFor(id,value);history.record(value);try{sessionStorage.setItem('sc-section-history:'+historyScope+':'+id,JSON.stringify(history));}catch{}return history;}
function syncArea(s){const area=areas.get(s.id);if(!area)return;const value=drafts[s.id]??s.html;historyFor(s.id,value);if(area.value!==value){remember(s.id,area.value);area.value=value;remember(s.id,value);}}
function recover(id,redo){const area=areas.get(id);if(!area)return;const history=historyFor(id,area.value),value=redo?history.redo():history.undo(area.value);if(value===area.value)return;area.value=value;area.focus({preventScroll:true});area.dispatchEvent(new Event('input',{bubbles:true}));try{sessionStorage.setItem('sc-section-history:'+historyScope+':'+id,JSON.stringify(history));}catch{}}
function visibleBottom(){try{return Math.min(innerHeight,parent.innerHeight-frameElement.getBoundingClientRect().top);}catch{return innerHeight;}}
function renameControl(s,name){
 const wrap=el('span','','section-name-control'),menu=el('div','','section-name-menu'),form=el('form','','section-name-editor');
 menu.setAttribute('popover','auto');menu.setAttribute('role','menu');
 form.setAttribute('popover','auto');form.setAttribute('aria-label','Rename section');
 const place=(popup)=>{const r=trigger.getBoundingClientRect();popup.style.left=Math.max(4,Math.min(r.left,innerWidth-260))+'px';popup.style.top=Math.max(4,Math.min(r.bottom+4,visibleBottom()-145))+'px';popup.showPopover();};
 const trigger=button('⋮','Section options',()=>{place(menu);rename.focus();},'section-options');trigger.setAttribute('aria-haspopup','menu');trigger.setAttribute('aria-expanded','false');
 menu.addEventListener('toggle',()=>trigger.setAttribute('aria-expanded',String(menu.matches(':popover-open'))));
 const input=document.createElement('input');input.type='text';input.maxLength=80;input.required=true;input.setAttribute('aria-label','Section name');
 const close=()=>{form.hidePopover();trigger.focus({preventScroll:true});};
 const rename=button('Rename','Rename',()=>{menu.hidePopover();input.value=name;input.setCustomValidity('');place(form);input.focus();input.select();});rename.setAttribute('role','menuitem');menu.append(rename);
 form.append(input,button('Save','Save section name',()=>form.requestSubmit()),button('Cancel','Cancel rename',close),button('Reset to default','Reset section name to default',()=>{emit('rename',{id:s.id,name:'',reset:true});close();},'section-name-reset'));
 form.onsubmit=e=>{e.preventDefault();if(!input.value.trim()){input.setCustomValidity('Enter a section name.');input.reportValidity();return;}emit('rename',{id:s.id,name:input.value.trim()});close();};
 input.oninput=()=>input.setCustomValidity('');
 form.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();close();}};
 menu.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();menu.hidePopover();trigger.focus();}};
 wrap.append(trigger,menu,form);return wrap;
}
function deleteControl(s){
 const trash=button('','Delete section',()=>{const r=trash.getBoundingClientRect();popup.style.top=Math.max(8,Math.min(r.bottom+4,visibleBottom()-100))+'px';popup.style.left=Math.max(8,r.right-200)+'px';popup.showPopover();cancel.focus({preventScroll:true});},'section-delete');
 trash.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7"/></svg>';
 const popup=el('div','','section-confirm');popup.setAttribute('popover','auto');popup.setAttribute('role','dialog');popup.setAttribute('aria-label','Delete this section?');popup.append(el('div','Delete this section?'));
 if(s.type==='discount')popup.append(el('div','Deletes this presentation. Use Disconnect checkout discount to remove the associated offer.'));
 const cancel=button('Cancel','Cancel delete',()=>{popup.hidePopover();trash.focus({preventScroll:true});});
 popup.append(cancel,button('Delete','Confirm delete section',()=>{
  popup.hidePopover();const snapshot=JSON.parse(JSON.stringify(args.sections.find(v=>v.id===s.id)||s));if(areas.has(s.id))snapshot.html=areas.get(s.id).value;
  const node=trash.closest('.section');deleted={section:snapshot,position:args.sections.findIndex(v=>v.id===s.id),top:node.getBoundingClientRect().top,node};
  clearTimeout(areas.get(s.id)?.saveTimer);emit('remove',{id:s.id,confirmed:true});delete drafts[s.id];node.remove();showDeleted();height();
 }));
 const wrap=el('span','','delete-control');wrap.append(trash,popup);return wrap;
}
function showDeleted(){
 clearTimeout(deleteTimer);let toast=document.getElementById('section-deleted');if(toast)toast.remove();toast=el('div','','section-toast');toast.id='section-deleted';toast.style.top=Math.max(4,Math.min(deleted.top,visibleBottom()-48,document.body.scrollHeight-44))+'px';toast.setAttribute('role','status');toast.append(el('span','Section deleted'),button('Undo','Undo delete section',()=>{
  if(!deleted)return;const saved=deleted;deleted=null;clearTimeout(deleteTimer);toast.remove();emit('restore_section',{section:saved.section,position:saved.position});height();
 }));document.body.append(toast);deleteTimer=setTimeout(()=>{toast.remove();deleted=null;},8000);
}
function reorder(section,id,target,after=null){if(section){const s=args.sections.find(s=>s.id===section);emit('product_order',{id:section,ids:moveId(s.products.map(p=>p.id),id,target)});}else {const ids=after===null?moveId(args.sections.map(s=>s.id),id,target):insertAt(args.sections.map(s=>s.id),id,target,after);emit('order',{ids});placeCards(ids);}}
function handle(row,id,section=null){let h=button('⋮⋮','Drag to reorder section; Alt + Up or Down',()=>{},'handle');h.dataset.drag=id;h.dataset.section=section||'';
 h.onkeydown=e=>{if(e.altKey&&['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const ids=section?args.sections.find(s=>s.id===section).products.map(p=>p.id):args.sections.map(s=>s.id),i=ids.indexOf(id),j=i+(e.key==='ArrowUp'?-1:1);if(j>=0&&j<ids.length)reorder(section,id,ids[j]);}};row.append(h);}
function changeSettings(s,patch){const current=settingsDrafts[s.id]||s.settings;const next={...current,...patch};if(s.type==='catalogue')next.display={...current.display,...(patch.display||{})};if(JSON.stringify(current)===JSON.stringify(next))return;settingsDrafts[s.id]=next;emit('settings',{id:s.id,settings:next});}
function renderTemplates(){
 let association=document.getElementById('checkout-discount-association');
 if(!association){association=el('div','','discount-summary');association.id='checkout-discount-association';root.after(association);}
 association.replaceChildren();association.hidden=!args.discount_offer;
 if(args.discount_offer){association.append(el('span','Checkout offer: '+args.discount_offer.code+' · '+args.discount_offer.value+' · independent of visible content'),button('Disconnect','Disconnect checkout discount',()=>emit('discount_disconnect')));}
 const container=document.getElementById('saved-templates');container.replaceChildren();
 if((args.templates||[]).length)container.append(el('hr'));
 for(const template of args.templates||[]){
  const item=button(template.name,'Insert '+template.name,()=>{
   document.getElementById('add').open=false;
   emit('add',{kind:'template',template_id:template.id,version:template.version});
  });
  item.dataset.add='template';container.append(item);
 }
}
function render(){renderTemplates();renderDiscountPicker(document.getElementById('discount-picker'),args.discount,emit);for(const b of document.querySelectorAll('[data-add=visual],[data-add=flexible_checkout]'))b.hidden=!args.automation;const focus=document.activeElement,label=focus?.getAttribute('aria-label'),sectionId=focus?.closest('.section')?.dataset.id,dragId=focus?.dataset.drag,action=focus?.dataset.action,start=focus?.selectionStart,end=focus?.selectionEnd,scroll=focus?.scrollTop;for(const card of [...root.children])if(!args.sections.some(s=>s.id===card.dataset.id))card.remove();args.sections.forEach((s,index)=>{
 const name=s.name||(s.type==='discount'?'Discount':s.type==='html'?'HTML Section '+s.html_number:s.type==='image'?'Image':s.type==='abandoned_checkout_products'?'Abandoned Checkout':s.type==='checkout_element'?s.settings.kind.replaceAll('_',' '):'Catalogue');if(opened[s.id]===undefined)opened[s.id]=s.html_number===1||s.type==='image'||s.type==='discount';
 const signature=JSON.stringify({...s,html:undefined,open:opened[s.id],prompt:s.type==='image'?args.image_prompt:undefined});
 const existing=[...root.children].find(c=>c.dataset.id===s.id);
 if(existing?.dataset.signature===signature){syncArea(s);return;}
 let card=el('section','','section');card.dataset.id=s.id;card.dataset.signature=signature;if(s.type==='catalogue')card.classList.add('catalogue');let row=el('div','','row');handle(row,s.id);
 let visibility=button('',s.visible?'Visible section — click to hide':'Hidden section — click to show',()=>{emit('visible',{id:s.id,visible:!s.visible});},'visibility');
 visibility.dataset.action='visibility';visibility.setAttribute('aria-pressed',String(s.visible));visibility.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'+(s.visible?'':'<path d="m3 3 18 18"/>')+'</svg>';row.append(visibility);
 row.append(renameControl(s,name));
 card.classList.toggle('is-hidden',!s.visible);card.classList.toggle('is-open',!!opened[s.id]);
 let title=button(name,'Edit '+name,()=>{opened[s.id]=!opened[s.id];render();},'title');title.setAttribute('aria-expanded',!!opened[s.id]);row.append(title);
 if(s.type==='image')imageControls(row,args.image_prompt||'');
 if(s.type==='discount')row.append(button(args.discount_offer?'Change':'Connect',args.discount_offer?'Change Shopify discount':'Connect Shopify discount',()=>emit('discount_open',{id:s.id})));
 row.append(button('⧉','Duplicate section',()=>emit('duplicate',{id:s.id})));
 row.append(deleteControl(s),el('span',opened[s.id]?'⌃':'⌄','chevron'));card.append(row);
 if(opened[s.id]){let content=el('div','','content');if(s.type==='html'||s.type==='image'||s.type==='discount'){
 if(s.type==='discount')content.append(el('div',args.discount_offer?args.discount_offer.code+' · '+args.discount_offer.value:'Presentation only · no checkout discount connected','discount-summary'));
 if(s.type==='discount')content.append(el('small','Write any supported HTML. Code and amount placeholders are optional. Checkout offer changes use Connect, Change or Disconnect.'));
 let area=areas.get(s.id);
 if(!area){area=document.createElement('textarea');area.value=drafts[s.id]??s.html;area.placeholder='Paste campaign HTML here…';area.setAttribute('aria-label',name+' HTML');areas.set(s.id,area);}
 area.setAttribute('aria-label',name+' HTML');syncArea(s);
 const advice=el('div',s.type==='image'?imageAdvice(area.value):'','warning');advice.setAttribute('aria-live','polite');
 const update=()=>{clearTimeout(area.saveTimer);remember(s.id,area.value);const current=args.sections.find(v=>v.id===s.id);if(current&&area.value!==current.html){drafts[s.id]=area.value;emit('html',{id:s.id,html:area.value});}else if(current){delete drafts[s.id];localPreview();if(!pending&&!changes.length&&!Object.keys(drafts).length&&!saveError){saveStatus('Saved · Draft');try{sessionStorage.removeItem('sc-local-draft:'+historyScope);}catch{}}}};
 area.oninput=()=>{if(s.type==='image')advice.textContent=imageAdvice(area.value);signalPending({id:s.id,html:area.value});drafts[s.id]=area.value;SCPreview.channel(args.preview_scope).dirty=true;clearTimeout(previewTimer);previewTimer=setTimeout(()=>{const current=args.sections.map(v=>Object.hasOwn(drafts,v.id)?{...v,html:drafts[v.id],css_version:1}:v);SCPreview.publish(args.preview_scope,current,true);},80);saveStatus('Unsaved · Unpublished changes');clearTimeout(area.saveTimer);area.saveTimer=setTimeout(update,180);};area.onblur=update;
 const historyTools=el('div','','history-tools');historyTools.append(button('↶','Undo last edit',()=>recover(s.id,false),'history-button'),button('↷','Redo last edit',()=>recover(s.id,true),'history-button'));
 if(args.automation&&s.html.includes('<!--SC_ABANDONED_CHECKOUT-->'))content.append(button('Separate checkout elements','Separate checkout into optional visual elements',()=>emit('separate_checkout',{id:s.id})));content.append(historyTools,area);if(s.type==='image')content.append(advice);
 }else if(s.type==='checkout_element'){
 visualControls(s,content,{el,change:patch=>changeSettings(s,patch),debounce:(input,field,commit)=>{
  let timer;const inputKey=s.id+':'+field;const save=()=>{clearTimeout(timer);pendingCopyInputs.delete(inputKey);commit();};
  input.oninput=()=>{signalPending({id:s.id,[field]:input.value});pendingCopyInputs.set(inputKey,save);clearTimeout(timer);timer=setTimeout(save,80);};input.onchange=save;
 }});
 }else if(s.type==='abandoned_checkout_products'){
 if(args.automation)content.append(button('Separate checkout elements','Separate checkout into optional visual elements',()=>emit('separate_checkout',{id:s.id})));content.append(el('div','Products, variants, quantities, prices and recovery link resolve from each customer’s own checkout.','warning'));
 }else{
 const tools=el('div','','tools');tools.append(button('Select products','Select products for '+name,()=>emit('picker',{id:s.id})),button('↻','Refresh current Shopify and Edition Ops facts',()=>emit('refresh',{id:s.id})));content.append(tools);
 s.products.forEach(p=>{let pr=el('div','','product');pr.dataset.product=p.id;pr.dataset.parent=s.id;handle(pr,p.id,s.id);let info=el('div','','product-info');info.append(el('span',p.title));if(!p.edition)info.append(el('div','Edition data not connected','warning'));pr.append(info,button('×','Remove '+p.title,()=>emit('product_remove',{id:s.id,product_id:p.id})));content.append(pr);});
 const copyFields=el('div','','fields');for(const [field,limit] of [['headline',80],['subtext',180]]){const input=document.createElement('input');input.type='text';input.value=s.settings[field]||'';input.maxLength=limit;input.placeholder=field==='headline'?'Headline (optional)':'Subtext (optional)';input.setAttribute('aria-label','Catalogue '+field);let timer;const inputKey=s.id+':'+field;const commit=()=>{clearTimeout(timer);pendingCopyInputs.delete(inputKey);changeSettings(s,{[field]:input.value});};input.oninput=()=>{pendingCopyInputs.set(inputKey,commit);signalPending({id:s.id,[field]:input.value});clearTimeout(timer);timer=setTimeout(commit,100);};input.onchange=commit;copyFields.append(input);}content.append(copyFields);

 const labels={image:'Product image',title:'Product title',price:'Price',limit:'Limited to',next:'Next available',remaining:'Remaining',cta:'CTA'},fields=el('div','','fields');for(let [key,label] of Object.entries(labels)){let l=el('label'),c=document.createElement('input');c.type='checkbox';c.checked=s.settings.display[key];c.onchange=()=>changeSettings(s,{display:{[key]:c.checked}});l.append(c,el('span',label));fields.append(l);}content.append(fields);
 const cta=document.createElement('input');cta.type='text';cta.value=s.settings.cta;cta.maxLength=60;cta.setAttribute('aria-label','Catalogue CTA');let ctaTimer;const commitCta=()=>{clearTimeout(ctaTimer);if(cta.value.trim())changeSettings(s,{cta:cta.value});};cta.oninput=()=>{signalPending({id:s.id,cta:cta.value});clearTimeout(ctaTimer);ctaTimer=setTimeout(commitCta,100);};cta.onchange=commitCta;content.append(cta);
 for(const warning of (args.warnings||{})[s.id]||[])content.append(el('div',warning,'warning'));
 }
 card.append(content);}if(existing)existing.replaceWith(card);else root.append(card);
 });placeCards(args.sections.map(s=>s.id));if(label&&document.activeElement!==focus){const next=[...root.querySelectorAll('[aria-label]')].find(n=>(action?n.dataset.action===action:n.getAttribute('aria-label')===label)&&n.closest('.section')?.dataset.id===sectionId&&(!dragId||n.dataset.drag===dragId));if(next){next.focus({preventScroll:true});if(start!==null&&start!==undefined&&['TEXTAREA','INPUT'].includes(next.tagName)){next.setSelectionRange(start,end);next.scrollTop=scroll;}}}height();}
document.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{document.getElementById('add').open=false;emit('add',{kind:b.dataset.add,reserved_html_number:deleted?.section.html_number||0});});
const addMenu=document.getElementById('add'),addTrigger=addMenu.querySelector('summary');
 addMenu.ontoggle=()=>{addTrigger.setAttribute('aria-expanded',String(addMenu.open));height();};
 const closeAdd=()=>{addMenu.open=false;};
 document.addEventListener('click',e=>{if(!addMenu.contains(e.target))closeAdd();});
 addEventListener('blur',closeAdd);
 addMenu.addEventListener('keydown',e=>{
  const items=[...addMenu.querySelectorAll('[data-add]')];
  if(e.key==='Escape'){e.preventDefault();closeAdd();addTrigger.focus();}
  else if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();addMenu.open=true;const i=items.indexOf(document.activeElement);items[(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}
 });
function clearDrag(){document.querySelectorAll('.drop-before,.drop-after,.drag-active').forEach(n=>n.classList.remove('drop-before','drop-after','drag-active'));}
function dropTarget(e){
 const candidates=[...root.querySelectorAll(drag.section?'.product':'.section')].filter(n=>drag.section?n.dataset.parent===drag.section&&n.dataset.product!==drag.id:n.dataset.id!==drag.id);
 if(!candidates.length)return null;
 const node=candidates.find(n=>e.clientY<n.getBoundingClientRect().bottom)||candidates.at(-1),rect=node.getBoundingClientRect();
 return {node,id:drag.section?node.dataset.product:node.dataset.id,after:e.clientY>rect.top+rect.height/2};
}
root.addEventListener('pointerdown',e=>{const h=e.target.closest('[data-drag]');if(!h||e.button!==0)return;drag={id:h.dataset.drag,section:h.dataset.section||null,x:e.clientX,y:e.clientY,moved:false};root.setPointerCapture(e.pointerId);e.preventDefault();h.focus({preventScroll:true});});
root.addEventListener('pointermove',e=>{if(!drag)return;drag.moved ||= Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>7;if(!drag.moved)return;clearDrag();const source=[...root.querySelectorAll(drag.section?'.product':'.section')].find(n=>drag.section?n.dataset.product===drag.id:n.dataset.id===drag.id);source?.classList.add('drag-active');drag.target=dropTarget(e);drag.target?.node.classList.add(drag.target.after?'drop-after':'drop-before');});
root.addEventListener('pointerup',e=>{if(!drag)return;const d=drag;drag=null;clearDrag();if(root.hasPointerCapture(e.pointerId))root.releasePointerCapture(e.pointerId);if(d.moved&&d.target)reorder(d.section,d.id,d.target.id,d.target.after);else render();});
const cancelDrag=()=>{drag=null;clearDrag();};
root.addEventListener('pointercancel',cancelDrag);addEventListener('blur',cancelDrag);
document.addEventListener('visibilitychange',()=>{cancelDrag();if(document.hidden){clearTimeout(typing);const entry=Object.entries(drafts)[0];if(entry)emit('html',{id:entry[0],html:entry[1]});}});
addEventListener('message',e=>{
 if(e.source!==parent||e.data.type!=='streamlit:render')return;
 const incoming=e.data.args,changedScope=historyScope!==incoming.history_scope;
 if(!changedScope&&Number(incoming.draft_version)<Number(args.draft_version))return;
 if(changedScope){
  pendingCopyInputs.clear();for(const area of areas.values())clearTimeout(area.saveTimer);
  histories.clear();areas.clear();drafts={};queue=[];settingsDrafts={};opened={};pending=false;deleted=null;changes=[];sent=[];unpersisted=[];external=[];saveError='';clearTimeout(saveTimer);clearTimeout(deleteTimer);root.replaceChildren();
  historyScope=incoming.history_scope;args=incoming;
  let recovery;try{recovery=JSON.parse(sessionStorage.getItem('sc-local-draft:'+historyScope));}catch{}
  if(recovery?.changes?.length){
   if(recovery.version===incoming.draft_version){args.sections=recovery.sections;changes=recovery.changes;dirty();}
   else {saveError='A saved draft changed while this browser was closed. Your recovery copy is retained; review it before replacing saved work.';saveStatus(saveError);}
  }
 }else{
  const localSections=args.sections;
  if(pending&&incoming.ack===inFlight){
   pending=false;
   if(incoming.edit_error){changes=[...sent,...changes];saveError=incoming.edit_error;}
   else {saveError=incoming.save_status==='Save failed'?(incoming.save_error||'Save failed. Your local edits are retained.'):'';unpersisted=saveError?[...unpersisted,...sent]:[];sent=[];}
   if(!saveError&&!changes.length&&!Object.keys(drafts).length){try{sessionStorage.removeItem('sc-local-draft:'+historyScope);}catch{}}
  }
  args={...incoming,sections:pending||changes.length||Object.keys(drafts).length||saveError?localSections:incoming.sections};
 }
 if(args.clipboard_script&&!window.scCopyText){const script=document.createElement('script');script.textContent=args.clipboard_script;document.head.appendChild(script);}
 if(!drag)render();localPreview();
 if(saveError){saveStatus('Save failed · '+saveError);rememberDraft();if(!incoming.edit_error&&saveAttempts++<3){clearTimeout(saveTimer);saveTimer=setTimeout(sendChanges,Math.min(1000*2**saveAttempts,8000));}}
 else if(changes.length){saveStatus('Unsaved · Unpublished changes');if(!pending){clearTimeout(saveTimer);saveTimer=setTimeout(sendChanges,650);}}
 else if(!pending){saveStatus('Saved · Draft');withParent(p=>{const size=p.document.querySelector('.st-key-crm-composer-preview .sc-email-size');if(size?.dataset.lastMeasured){size.innerHTML=size.dataset.lastMeasured;delete size.dataset.lastMeasured;}});if(external.length)sendChanges();}
});
new ResizeObserver(height).observe(document.body);
parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
}
