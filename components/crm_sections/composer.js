/* Dependency-free middle-only sorting. Header/Footer never enter this component. */
function moveId(ids,id,target){const result=[...ids],a=result.indexOf(id),b=result.indexOf(target);if(a<0||b<0)return result;result.splice(a,1);result.splice(b,0,id);return result;}
if(typeof module!=='undefined')module.exports={moveId};
if(typeof document!=='undefined'){
let args={sections:[]},opened={},pending=false,inFlight=null,drag=null,typing=null,drafts={},queue=[],settingsDrafts={};
const root=document.getElementById('sections');
const height=()=>parent.postMessage({isStreamlitMessage:true,type:'streamlit:setFrameHeight',height:document.body.scrollHeight+4},'*');
const emit=(type,extra={})=>{if(pending){if(type!=='html')queue.push([type,extra]);return;}pending=true;inFlight=crypto.randomUUID();parent.postMessage({isStreamlitMessage:true,type:'streamlit:setComponentValue',value:{event:inFlight,base:args.sections.map(s=>s.id),type,...extra}},'*');};
const el=(tag,text='',cls='')=>{let n=document.createElement(tag);n.textContent=text;n.className=cls;return n;};
function button(text,label,fn,cls=''){let n=el('button',text,cls);n.type='button';n.title=label;n.setAttribute('aria-label',label);n.onclick=fn;return n;}
function reorder(section,id,target){if(section){const s=args.sections.find(s=>s.id===section);emit('product_order',{id:section,ids:moveId(s.products.map(p=>p.id),id,target)});}else emit('order',{ids:moveId(args.sections.map(s=>s.id),id,target)});}
function handle(row,id,section=null){let h=button('⋮⋮','Drag to reorder; Alt + Up or Down',()=>{},'handle');h.dataset.drag=id;h.dataset.section=section||'';
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
function render(){renderTemplates();const focus=document.activeElement,label=focus?.getAttribute('aria-label'),sectionId=focus?.closest('.section')?.dataset.id,dragId=focus?.dataset.drag,action=focus?.dataset.action,start=focus?.selectionStart,end=focus?.selectionEnd,scroll=focus?.scrollTop;root.replaceChildren();args.sections.forEach((s,index)=>{
 const name=s.type==='html'?'HTML Section '+s.html_number:'Catalogue';if(opened[s.id]===undefined)opened[s.id]=s.html_number===1;
 let card=el('section','','section');card.dataset.id=s.id;if(s.type==='catalogue')card.classList.add('catalogue');let row=el('div','','row');handle(row,s.id);
 let visibility=button('',(s.visible?'Hide ':'Show ')+name,()=>emit('visible',{id:s.id,visible:!s.visible}),'visibility');
 visibility.dataset.action='visibility';visibility.setAttribute('aria-pressed',String(s.visible));visibility.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'+(s.visible?'':'<path d="m3 3 18 18"/>')+'</svg>';row.append(visibility);
 card.classList.toggle('is-hidden',!s.visible);card.classList.toggle('is-open',!!opened[s.id]);
 let title=button(name,'Edit '+name,()=>{opened[s.id]=!opened[s.id];render();},'title');title.setAttribute('aria-expanded',!!opened[s.id]);row.append(title);
 row.append(el('small',!s.visible?'Hidden':s.type==='catalogue'?s.products.length+' products':''),el('span',opened[s.id]?'⌃':'⌄','chevron'));card.append(row);
 if(opened[s.id]){let content=el('div','','content');if(s.type==='html'){
 let area=document.createElement('textarea');area.value=drafts[s.id]??s.html;area.placeholder='Paste campaign HTML here…';area.setAttribute('aria-label',name+' HTML');
 const update=()=>{clearTimeout(typing);if(area.value!==s.html){drafts[s.id]=area.value;emit('html',{id:s.id,html:area.value});}};area.oninput=()=>{drafts[s.id]=area.value;clearTimeout(typing);typing=setTimeout(update,180);};area.onblur=update;content.append(area);
 }else{
 const tools=el('div','','tools');tools.append(button('Select products','Select products for '+name,()=>emit('picker',{id:s.id})),button('↻','Refresh current Shopify and Edition Ops facts',()=>emit('refresh',{id:s.id})));content.append(tools);
 s.products.forEach(p=>{let pr=el('div','','product');pr.dataset.product=p.id;pr.dataset.parent=s.id;handle(pr,p.id,s.id);let info=el('div','','product-info');info.append(el('span',p.title));if(!p.edition)info.append(el('div','Edition data not connected','warning'));pr.append(info,button('×','Remove '+p.title,()=>emit('product_remove',{id:s.id,product_id:p.id})));content.append(pr);});
 let layout=document.createElement('select');layout.setAttribute('aria-label','Catalogue layout');for(let n of [1,2]){let opt=el('option',n+' column'+(n===2?'s':''));opt.value=n;opt.selected=s.settings.columns===n;layout.append(opt);}layout.onchange=()=>changeSettings(s,{columns:Number(layout.value)});content.append(layout);
 const labels={image:'Product image',title:'Product title',price:'Price',limit:'Limited to',next:'Next available',remaining:'Remaining',cta:'CTA'},fields=el('div','','fields');for(let [key,label] of Object.entries(labels)){let l=el('label'),c=document.createElement('input');c.type='checkbox';c.checked=s.settings.display[key];c.onchange=()=>changeSettings(s,{display:{[key]:c.checked}});l.append(c,el('span',label));fields.append(l);}content.append(fields);
 const cta=document.createElement('input');cta.type='text';cta.value=s.settings.cta;cta.maxLength=60;cta.setAttribute('aria-label','Catalogue CTA');let ctaTimer;const commitCta=()=>{clearTimeout(ctaTimer);if(cta.value.trim())changeSettings(s,{cta:cta.value});};cta.oninput=()=>{clearTimeout(ctaTimer);ctaTimer=setTimeout(commitCta,180);};cta.onchange=commitCta;content.append(cta);
 for(const warning of (args.warnings||{})[s.id]||[])content.append(el('div',warning,'warning'));
 }
 if(s.html_number!==1)content.append(button('Remove section','Remove '+name,()=>{if(confirm('Remove '+name+' and its content?'))emit('remove',{id:s.id,confirmed:true});},'remove'));
 card.append(content);}root.append(card);
 });if(label){const next=[...root.querySelectorAll('[aria-label]')].find(n=>(action?n.dataset.action===action:n.getAttribute('aria-label')===label)&&n.closest('.section')?.dataset.id===sectionId&&(!dragId||n.dataset.drag===dragId));if(next){next.focus({preventScroll:true});if(next.tagName==='TEXTAREA'){next.setSelectionRange(start,end);next.scrollTop=scroll;}}}height();}
document.querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>{document.getElementById('add').open=false;emit('add',{kind:b.dataset.add});});
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
document.addEventListener('pointerdown',e=>{const h=e.target.closest('[data-drag]');if(!h)return;drag={id:h.dataset.drag,section:h.dataset.section||null,x:e.clientX,y:e.clientY,moved:false};h.setPointerCapture(e.pointerId);});
document.addEventListener('pointermove',e=>{if(!drag)return;drag.moved ||= Math.abs(e.clientX-drag.x)+Math.abs(e.clientY-drag.y)>7;document.querySelectorAll('.drop').forEach(n=>n.classList.remove('drop'));if(drag.moved){const target=document.elementFromPoint(e.clientX,e.clientY)?.closest(drag.section?'.product':'.section');if(target)target.classList.add('drop');}});
document.addEventListener('pointerup',e=>{if(!drag)return;const d=drag;drag=null;document.querySelectorAll('.drop').forEach(n=>n.classList.remove('drop'));if(!d.moved)return;const target=document.elementFromPoint(e.clientX,e.clientY)?.closest(d.section?'.product':'.section');if(!target||d.section&&target.dataset.parent!==d.section)return;reorder(d.section,d.id,d.section?target.dataset.product:target.dataset.id);});
addEventListener('message',e=>{if(e.source!==parent||e.data.type!=='streamlit:render')return;args=e.data.args;for(const id of Object.keys(settingsDrafts)){const s=args.sections.find(s=>s.id===id);if(!s||JSON.stringify(s.settings)===JSON.stringify(settingsDrafts[id]))delete settingsDrafts[id];else s.settings=settingsDrafts[id];}if(args.ack===inFlight)pending=false;for(const id of Object.keys(drafts)){const s=args.sections.find(s=>s.id===id);if(!s||s.html===drafts[id])delete drafts[id];}render();const entry=Object.entries(drafts)[0];if(entry)emit('html',{id:entry[0],html:entry[1]});else if(queue.length){const [type,extra]=queue.shift();emit(type,extra);}});
new ResizeObserver(height).observe(document.body);
parent.postMessage({isStreamlitMessage:true,type:'streamlit:componentReady',apiVersion:1},'*');
}
