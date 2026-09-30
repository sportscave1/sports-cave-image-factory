/* Dependency-free middle-only sorting. Header/Footer never enter this component. */
function moveId(ids,id,target){const result=[...ids],a=result.indexOf(id),b=result.indexOf(target);if(a<0||b<0)return result;result.splice(a,1);result.splice(b,0,id);return result;}
if(typeof module!=='undefined')module.exports={moveId};
if(typeof document!=='undefined'){
let args={sections:[]},opened={},pending=false,inFlight=null,drag=null,typing=null,drafts={},queue=[],settingsDrafts={};
const root=document.getElementById('sections');
const areas=new Map(),histories=new Map();let historyScope='',deleted=null,deleteTimer=null;

const height=()=>parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:document.body.scrollHeight+4},'*');
const emit=(type,extra={})=>{if(pending){if(type!=='html')queue.push([type,{...extra,edits:{...drafts,...extra.edits}}]);return;}pending=true;inFlight=crypto.randomUUID();parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{event:inFlight,base:args.sections.map(s=>s.id),type,...extra,edits:Object.fromEntries(Object.entries({...extra.edits,...drafts}).filter(([id])=>args.sections.some(s=>s.id===id)))}},'*');};
// Send test must wait for the server acknowledgement, not merely textarea blur.
const flushSections=()=>new Promise((resolve,reject)=>{
 const started=Date.now(),scope=historyScope;
 const check=()=>{
  if(scope!==historyScope||Date.now()-started>10000)return reject(new Error('Section changes could not be synchronized. Retry after saving.'));
  for(const area of areas.values())clearTimeout(area.saveTimer);
  const entry=Object.entries(drafts)[0];
  if(!pending&&entry)emit('html',{id:entry[0],html:entry[1]});
  if(!pending&&!entry&&!queue.length&&!Object.keys(settingsDrafts).length)return resolve();
  setTimeout(check,30);
 };check();
});
parent.scCampaignFlushSections=flushSections;
addEventListener('pagehide',()=>{if(parent.scCampaignFlushSections===flushSections)delete parent.scCampaignFlushSections;});
const el=(tag,text='',cls='')=>{let n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
function button(text,label,fn,cls=''){let n=el('button',text,cls);n.type='button';n.title=label;n.setAttribute('aria-label',label);n.onclick=fn;return n;}
function placeCards(ids){ids.forEach((id,index)=>{const card=[...root.children].find(c=>c.dataset.id===id);if(card&&root.children[index]!==card){if(root.moveBefore)root.moveBefore(card,root.children[index]||null);else root.insertBefore(card,root.children[index]||null);}});}
function historyFor(id,value){if(!histories.has(id)){let saved;try{saved=JSON.parse(sessionStorage.getItem('sc-section-history:'+historyScope+':'+id));}catch{}histories.set(id,new SectionHistory(value,saved));}return histories.get(id);}
function remember(id,value){const history=historyFor(id,value);history.record(value);try{sessionStorage.setItem('sc-section-history:'+historyScope+':'+id,JSON.stringify(history));}catch{}return history;}
function syncArea(s){const area=areas.get(s.id);if(!area)return;const value=drafts[s.id]??s.html;historyFor(s.id,value);if(area.value!==value){remember(s.id,area.value);area.value=value;remember(s.id,value);}}
function recover(id,redo){const area=areas.get(id);if(!area)return;const history=historyFor(id,area.value),value=redo?history.redo():history.undo(area.value);if(value===area.value)return;area.value=value;area.focus({preventScroll:true});area.dispatchEvent(new Event('input',{bubbles:true}));try{sessionStorage.setItem('sc-section-history:'+historyScope+':'+id,JSON.stringify(history));}catch{}}
function visibleBottom(){try{return Math.min(innerHeight,parent.innerHeight-frameElement.getBoundingClientRect().top);}catch{return innerHeight;}}
function deleteControl(s){
 const trash=button('','Delete section',()=>{const r=trash.getBoundingClientRect();popup.style.top=Math.max(8,Math.min(r.bottom+4,visibleBottom()-100))+'px';popup.style.left=Math.max(8,r.right-200)+'px';popup.showPopover();cancel.focus({preventScroll:true});},'section-delete');
 trash.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7"/></svg>';
 const popup=el('div','','section-confirm');popup.setAttribute('popover','auto');popup.setAttribute('role','dialog');popup.setAttribute('aria-label','Delete this section?');popup.append(el('div','Delete this section?'));
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
  if(!deleted)return;const saved=deleted;deleted=null;clearTimeout(deleteTimer);toast.remove();root.insertBefore(saved.node,root.children[saved.position]||null);emit('restore_section',{section:saved.section,position:saved.position});height();
 }));document.body.append(toast);deleteTimer=setTimeout(()=>{toast.remove();deleted=null;},8000);
}
function reorder(section,id,target,after=null){if(section){const s=args.sections.find(s=>s.id===section);emit('product_order',{id:section,ids:moveId(s.products.map(p=>p.id),id,target)});}else {const ids=after===null?moveId(args.sections.map(s=>s.id),id,target):insertAt(args.sections.map(s=>s.id),id,target,after);emit('order',{ids});placeCards(ids);}}
function handle(row,id,section=null){let h=button('⋮⋮','Drag to reorder section; Alt + Up or Down',()=>{},'handle');h.dataset.drag=id;h.dataset.section=section||'';
 h.onkeydown=e=>{if(e.altKey&&['ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const ids=section?args.sections.find(s=>s.id===section).products.map(p=>p.id):args.sections.map(s=>s.id),i=ids.indexOf(id),j=i+(e.key==='ArrowUp'?-1:1);if(j>=0&&j<ids.length)reorder(section,id,ids[j]);}};row.append(h);}
function changeSettings(s,patch){const current=settingsDrafts[s.id]||s.settings;const next={...current,...patch,display:{...current.display,...(patch.display||{})}};settingsDrafts[s.id]=next;emit('settings',{id:s.id,settings:next});}
function renderTemplates(){
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
function render(){renderTemplates();const focus=document.activeElement,label=focus?.getAttribute('aria-label'),sectionId=focus?.closest('.section')?.dataset.id,dragId=focus?.dataset.drag,action=focus?.dataset.action,start=focus?.selectionStart,end=focus?.selectionEnd,scroll=focus?.scrollTop;for(const card of [...root.children])if(!args.sections.some(s=>s.id===card.dataset.id))card.remove();args.sections.forEach((s,index)=>{
 const name=s.type==='html'?'HTML Section '+s.html_number:s.type==='image'?'Image':'Catalogue';if(opened[s.id]===undefined)opened[s.id]=s.html_number===1||s.type==='image';
 const signature=JSON.stringify({...s,html:undefined,open:opened[s.id],prompt:s.type==='image'?args.image_prompt:undefined});
 const existing=[...root.children].find(c=>c.dataset.id===s.id);
 if(existing?.dataset.signature===signature){syncArea(s);return;}
 let card=el('section','','section');card.dataset.id=s.id;card.dataset.signature=signature;if(s.type==='catalogue')card.classList.add('catalogue');let row=el('div','','row');handle(row,s.id);
 let visibility=button('',s.visible?'Visible section — click to hide':'Hidden section — click to show',()=>emit('visible',{id:s.id,visible:!s.visible}),'visibility');
 visibility.dataset.action='visibility';visibility.setAttribute('aria-pressed',String(s.visible));visibility.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'+(s.visible?'':'<path d="m3 3 18 18"/>')+'</svg>';row.append(visibility);
 card.classList.toggle('is-hidden',!s.visible);card.classList.toggle('is-open',!!opened[s.id]);
 let title=button(name,'Edit '+name,()=>{opened[s.id]=!opened[s.id];render();},'title');title.setAttribute('aria-expanded',!!opened[s.id]);row.append(title);
 if(s.type==='image')imageControls(row,args.image_prompt||'');
 row.append(deleteControl(s),el('span',opened[s.id]?'⌃':'⌄','chevron'));card.append(row);
 if(opened[s.id]){let content=el('div','','content');if(s.type==='html'||s.type==='image'){
 let area=areas.get(s.id);
 if(!area){area=document.createElement('textarea');area.value=drafts[s.id]??s.html;area.placeholder='Paste campaign HTML here…';area.setAttribute('aria-label',name+' HTML');areas.set(s.id,area);}
 syncArea(s);
 const advice=el('div',s.type==='image'?imageAdvice(area.value):'','warning');advice.setAttribute('aria-live','polite');
 const update=()=>{clearTimeout(area.saveTimer);remember(s.id,area.value);const current=args.sections.find(v=>v.id===s.id);if(current&&area.value!==current.html){drafts[s.id]=area.value;emit('html',{id:s.id,html:area.value});}};
 area.oninput=()=>{if(s.type==='image')advice.textContent=imageAdvice(area.value);parent.dispatchEvent(new CustomEvent('sc-campaign-pending',{detail:{id:s.id,html:area.value}}));drafts[s.id]=area.value;clearTimeout(area.saveTimer);area.saveTimer=setTimeout(update,750);};area.onblur=update;
 const historyTools=el('div','','history-tools');historyTools.append(button('↶','Undo last edit',()=>recover(s.id,false),'history-button'),button('↷','Redo last edit',()=>recover(s.id,true),'history-button'));
 content.append(historyTools,area);if(s.type==='image')content.append(advice);
 }else{
 const tools=el('div','','tools');tools.append(button('Select products','Select products for '+name,()=>emit('picker',{id:s.id})),button('↻','Refresh current Shopify and Edition Ops facts',()=>emit('refresh',{id:s.id})));content.append(tools);
 s.products.forEach(p=>{let pr=el('div','','product');pr.dataset.product=p.id;pr.dataset.parent=s.id;handle(pr,p.id,s.id);let info=el('div','','product-info');info.append(el('span',p.title));if(!p.edition)info.append(el('div','Edition data not connected','warning'));pr.append(info,button('×','Remove '+p.title,()=>emit('product_remove',{id:s.id,product_id:p.id})));content.append(pr);});
 let layout=document.createElement('select');layout.setAttribute('aria-label','Catalogue layout');for(let n of [1,2]){let opt=el('option',n+' column'+(n===2?'s':''));opt.value=n;opt.selected=s.settings.columns===n;layout.append(opt);}layout.onchange=()=>changeSettings(s,{columns:Number(layout.value)});content.append(layout);
 const labels={image:'Product image',title:'Product title',price:'Price',limit:'Limited to',next:'Next available',remaining:'Remaining',cta:'CTA'},fields=el('div','','fields');for(let [key,label] of Object.entries(labels)){let l=el('label'),c=document.createElement('input');c.type='checkbox';c.checked=s.settings.display[key];c.onchange=()=>changeSettings(s,{display:{[key]:c.checked}});l.append(c,el('span',label));fields.append(l);}content.append(fields);
 const cta=document.createElement('input');cta.type='text';cta.value=s.settings.cta;cta.maxLength=60;cta.setAttribute('aria-label','Catalogue CTA');let ctaTimer;const commitCta=()=>{clearTimeout(ctaTimer);if(cta.value.trim())changeSettings(s,{cta:cta.value});};cta.oninput=()=>{parent.dispatchEvent(new CustomEvent('sc-campaign-pending',{detail:{id:s.id,cta:cta.value}}));clearTimeout(ctaTimer);ctaTimer=setTimeout(commitCta,750);};cta.onchange=commitCta;content.append(cta);
 for(const warning of (args.warnings||{})[s.id]||[])content.append(el('div',warning,'warning'));
 }
 card.append(content);}if(existing)existing.replaceWith(card);else root.append(card);
 });placeCards(args.sections.map(s=>s.id));if(label&&document.activeElement!==focus){const next=[...root.querySelectorAll('[aria-label]')].find(n=>(action?n.dataset.action===action:n.getAttribute('aria-label')===label)&&n.closest('.section')?.dataset.id===sectionId&&(!dragId||n.dataset.drag===dragId));if(next){next.focus({preventScroll:true});if(next.tagName==='TEXTAREA'){next.setSelectionRange(start,end);next.scrollTop=scroll;}}}height();}
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
addEventListener('message',e=>{if(e.source!==parent||e.data.type!=='streamlit:render')return;args=e.data.args;if(historyScope!==args.history_scope){historyScope=args.history_scope;for(const area of areas.values())clearTimeout(area.saveTimer);histories.clear();areas.clear();drafts={};queue=[];settingsDrafts={};opened={};pending=false;deleted=null;clearTimeout(deleteTimer);document.getElementById('section-deleted')?.remove();root.replaceChildren();}for(const id of Object.keys(settingsDrafts)){const s=args.sections.find(s=>s.id===id);if(!s||JSON.stringify(s.settings)===JSON.stringify(settingsDrafts[id]))delete settingsDrafts[id];else s.settings=settingsDrafts[id];}if(args.ack===inFlight)pending=false;for(const id of Object.keys(drafts)){const s=args.sections.find(s=>s.id===id);if(!s||s.html===drafts[id])delete drafts[id];}if(!drag&&!pending&&!queue.length&&!Object.keys(drafts).length)render();const entry=Object.entries(drafts)[0];if(entry)emit('html',{id:entry[0],html:entry[1]});else if(queue.length){const [type,extra]=queue.shift();emit(type,extra);}});
new ResizeObserver(height).observe(document.body);
parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
}
