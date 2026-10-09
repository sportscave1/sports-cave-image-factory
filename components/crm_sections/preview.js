/* Shared browser composition. Data comes from the draft; no sends or fetches. */
(function(global){
'use strict';
const clone=v=>JSON.parse(JSON.stringify(v));
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#x27;'}[c]));
function channel(scope){const host=parent;host.scEmailDrafts??=new Map();if(!host.scEmailDrafts.has(scope))host.scEmailDrafts.set(scope,{sections:null,revision:0,listeners:new Set()});return host.scEmailDrafts.get(scope);}
function publish(scope,sections,dirty=false){const state=channel(scope);state.sections=clone(sections);state.dirty=dirty;state.revision++;for(const fn of state.listeners)fn(state.sections);}
function imageUrl(value){try{const u=new URL(value);if(u.protocol!=='https:'||u.username||u.password||u.port&&u.port!=='443'||!u.hostname.includes('.')||/^(localhost|127\.|10\.|192\.168\.|169\.254\.)/.test(u.hostname)||/\.(local|internal)$/.test(u.hostname))return '';if([...u.searchParams.keys()].some(k=>/^(token|signature|expires|x-amz-signature|x-goog-signature|se|sig)$/i.test(k)))return '';if(/\.(png|jpe?g)$/i.test(u.pathname)||u.hostname==='cdn.shopify.com'&&u.searchParams.get('format')==='jpg')return value;if(u.hostname==='cdn.shopify.com'&&/\.webp$/i.test(u.pathname)){u.searchParams.set('format','png');return u.href;}}catch{}return '';}
function sanitize(source,model){
 const template=document.createElement('template');template.innerHTML=source;const parsed=template.content;
 parsed.querySelectorAll('script,style,head,iframe,object,embed,svg,math,form,template,link,meta,base').forEach(n=>n.remove());
 const tags=new Set(model.tags),css=new Set(model.css);
 for(const n of [...parsed.querySelectorAll('*')]){
  if(!tags.has(n.localName)){n.replaceWith(...n.childNodes);continue;}
  for(const a of [...n.attributes]){
   const k=a.name,v=a.value;let keep=false;
   if(k==='style'){n.setAttribute('style',v.split(';').filter(d=>{const i=d.indexOf(':'),key=d.slice(0,i).trim().toLowerCase(),value=d.slice(i+1).trim();return i>0&&css.has(key)&&/^[a-zA-Z0-9#.,% ()"'\-]+$/.test(value)&&!/url|expression|var\(|calc\(|-\d/i.test(value)}).join(';'));continue;}
   if(['width','height','cellpadding','cellspacing','colspan','rowspan','border'].includes(k))keep=/^\d{1,4}%?$/.test(v);
   if(['align','valign','alt','title','role'].includes(k))keep=true;
   if(k==='class')keep=/^sc-(?:cart-[\w-]+|stack|cat-item sc-cat-[234])$/.test(v);
   if(['bgcolor','color'].includes(k))keep=/^(#[a-f0-9]{3}(?:[a-f0-9]{3})?|[a-z]{1,25})$/i.test(v);
   if(k==='face'&&n.localName==='font')keep=/^[a-z0-9 ,'"-]{1,200}$/i.test(v);
   if(k==='size'&&n.localName==='font')keep=/^[1-7]$/.test(v);
   if(k==='src'&&n.localName==='img'){const url=imageUrl(v);if(url&&Number(n.getAttribute('width')||99)>1&&Number(n.getAttribute('height')||99)>1){n.setAttribute('src',url);continue;}}
   // All anchors are intentionally inert, including unsubscribe/recovery links.
   if(!keep)n.removeAttribute(k);
  }
 }
 return template.innerHTML;
}
function visual(s,model){
 const c=s.settings,k=c.kind,dynamic=new Set(['product_image','lifestyle','edition','product_name','variant','dimensions','quantity','price','details']);
 let items=dynamic.has(k)||['wall','product'].includes(c.action)?(c.product===0?model.items:model.items.slice(c.product-1,c.product)):[{}];
 const style=`color:${c.color};background-color:${c.background};font-size:${c.size}px;font-weight:${c.weight};text-align:${c.align};padding:${c.padding}px;border:${c.border}px solid ${c.border_color};margin:0;line-height:1.5`;
 return items.map(item=>{let text=c.text,image='';
  if(k==='product_image')image=item.image;else if(k==='image')image=c.image_url;else if(k==='lifestyle')image=item.gallery?.[c.position-1]||'';
  else if(k==='product_name')text=item.title;else if(k==='quantity')text='Qty '+item.quantity;else if(['edition','variant','dimensions','price'].includes(k))text=item[k];else if(k==='details')text=[item.title,item.variant,item.dimensions,'Qty '+item.quantity,item.price].filter(Boolean).join('\n');
  let body='';if(['image','product_image','lifestyle'].includes(k)){if(!imageUrl(image))return '';body=`<img src="${esc(image)}" alt="${esc(item.title||c.alt)}" width="${c.width}" style="display:block;width:100%;max-width:${c.width}px;height:auto;border:0">`;}
  else if(k==='divider')body=`<hr style="border:0;border-top:1px solid ${c.border_color}">`;
  else if(k==='spacer')body=`<div style="height:${c.spacing}px">&#160;</div>`;
  else {if(!String(text||'').trim())return '';if(dynamic.has(k)&&!['product_name','details'].includes(k)&&items.length>1)text=item.title+' — '+text;body=esc(text).replaceAll('\n','<br>');if(k==='headline')body='<strong>'+body+'</strong>';if(k==='edition'&&c.edition_style!=='plain')body=`<span style="display:inline-block;padding:4px 8px;border:1px solid ${c.border_color}${c.edition_style==='collector'?';letter-spacing:2px;font-weight:bold':''}">${body}</span>`;}
  if(k==='button')body=`<span style="display:inline-block;${style}">${body}</span>`;
  return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr><td align="${c.align}" style="${k==='button'?'text-align:'+c.align:style};padding-bottom:${c.spacing}px">${body}</td></tr></table>`;
 }).join('');
}
function catalogue(s){
 const c=s.settings,d=c.display,products=s.products.filter(p=>p.status==='ACTIVE'&&p.title.trim()&&/^https:\/\//.test(p.url)&&(!d.image||imageUrl(p.image))&&(!d.price||(p.price!==''&&p.price!=null&&p.currency))),single=products.length===1;if(!products.length)return '';
 const p=(t,style)=>`<p style="margin:0 0 8px;${style}">${t}</p>`;
 const money=v=>v.price==null?'':`${v.currency==='AUD'?'A$':v.currency==='USD'?'US$':v.currency==='GBP'?'£':v.currency+' '}${Number(v.price).toFixed(2)}`;
 const cards=products.map(v=>{let info='',image='';if(d.image)image=`<tr><td align="center" bgcolor="#151515" style="padding:0"><img src="${esc(v.image)}" alt="${esc(v.image_alt||v.title)}" width="${single?552:260}" border="0" style="display:block;width:100%;max-width:100%;height:auto;border:0"></td></tr>`;
  if(d.title)info+=p(esc(v.title),`color:#faf6eb;font-size:${single?(v.title.length<80?21:18):14}px;line-height:${single?27:19}px;font-weight:700;word-wrap:break-word`);
  const e=v.edition;if(e){if(d.limit)info+=p('LIMITED TO '+e.limit+(single?' WORLDWIDE':''),'color:#d4b77d;font-size:11px;line-height:16px');const next=d.next&&e.remaining>0&&e.next>=1&&e.next<=e.limit;if(next)info+=p('#'+String(e.next).padStart(3,'0')+' / '+e.limit,`color:#faf6eb;font-size:${single?24:16}px;line-height:28px;font-weight:700`);const status=next&&single?['NEXT AVAILABLE']:[];if(d.remaining)status.push(e.remaining?e.remaining+' REMAINING':'SOLD OUT');if(status.length)info+=p(status.join(' · '),'color:#d6d0c4;font-size:11px;line-height:16px');}
  if(d.price)info+=p('From '+esc(money(v))+(Number(v.compare_at)>Number(v.price)?' <s>'+esc(money({...v,price:v.compare_at}))+'</s>':''),'color:#d6d0c4;font-size:13px;line-height:18px');
  if(d.cta)info+=`<span style="display:inline-block;background:${single?'#d4b77d;color:#111111':'#151515;color:#eed9ad'};border:1px solid #d4b77d;padding:${single?'12px 18px':'10px 6px'};font-size:${single?13:11}px;line-height:18px;font-weight:700;text-decoration:none;text-transform:uppercase;word-wrap:break-word">${esc(c.cta)}</span>`;
  const card=`<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;table-layout:fixed">${image}<tr><td align="${single?'center':'left'}" bgcolor="#151515" style="padding:${single?'20px 16px':'12px 8px'};font-family:Arial,Helvetica,sans-serif">${info}</td></tr></table>`;
  const columns=products.length<=2?2:[3,5,6].includes(products.length)?3:Math.max(...products.map(p=>p.title.length))<=65?4:products.length===4?2:3;
  return single?card:`<table class="sc-cat-item sc-cat-${columns}" role="presentation" width="50%" style="display:inline-block;width:50%;vertical-align:top;border-collapse:collapse;table-layout:fixed"><tr><td style="padding:4px">${card}</td></tr></table>`;
 });
 const heading=(c.headline?p(esc(c.headline),'color:#eed9ad;font-size:24px;line-height:29px;font-family:Georgia,serif'):'')+(c.subtext?p(esc(c.subtext),'color:#d6d0c4;font-size:13px;line-height:19px'):'');
 return `<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#111111" style="background:#111111;border-collapse:collapse;table-layout:fixed">${heading?'<tr><td align="center" style="padding:16px 12px 8px">'+heading+'</td></tr>':''}<tr><td align="left" style="padding:8px;font-size:0">${cards.join('')}</td></tr></table>`;
}
function sectionHtml(s,model,sections=[]){
 const signature=v=>JSON.stringify([v.type,v.html??null,v.settings??null,v.products??null,v.offer??null]);
 if(model.error_sections?.[s.id]&&signature(model.error_sections[s.id])===signature(s))throw Error(model.errors[s.id]);
 const known=Object.values(model.resolved).find(r=>signature(r.section)===signature(s));
 if(known)return sanitize(known.html,model);
 if(s.type==='checkout_element')return sanitize(visual(s,model),model);
 if(s.type==='catalogue')return sanitize(catalogue(s),model);
 if(s.type==='abandoned_checkout_products')return sanitize(model.replacements['<!--SC_ABANDONED_CHECKOUT-->']||'',model);
 let source=s.html||'';
 if(s.type==='discount'){
  if(!/{{\s*discount_code\s*}}/.test(source))throw Error('Keep {{discount_code}} in this offer section.');
  source=source.replace(/{{\s*discount_(code|value)\s*}}/g,(_,k)=>esc(s.offer[k]));
 }
 const offer=sections.find(v=>v.type==='discount'&&v.visible)?.offer||(!model.managed_offer?model.offer:null);
 source=source.replace(/{{\s*discount_(code|value)\s*}}/g,(_,k)=>{if(!offer)throw Error('Select a verified discount before using discount variables.');return esc(offer[k]);});
 for(const [token,value]of Object.entries(model.replacements))source=source.split(token).join(value);
 if(/{{|{%|SC_FRAME_BANNER_/.test(source))throw Error('Unresolved template variable. Correct this section; the draft is retained.');
 const template=document.createElement('template');template.innerHTML=source;const parsed=template.content;
 const theme=clone(model.theme||{});
 for(const style of parsed.querySelectorAll('style'))for(const m of style.textContent.matchAll(/\.([\w-]+)\s*\{([^}]+)\}/g)){if(!m[1].startsWith('sc-cart-'))continue;theme[m[1]]??={};for(const d of m[2].split(';')){const i=d.indexOf(':');if(i>0)theme[m[1]][d.slice(0,i).trim()]=[d.slice(i+1).trim().replace(/!important/g,''),false];}}
 for(const n of parsed.querySelectorAll('[class]'))for(const cls of n.classList)for(const [key,v]of Object.entries(theme[cls]||{}))if(!n.style.getPropertyValue(key)||v[1])n.style.setProperty(key,v[0]);
 return sanitize(template.innerHTML,model);
}
function mount(payload){
 const {scope}=payload,state=channel(scope);if(!state.model){setTimeout(()=>mount(payload),25);return;}let model=state.model;
 document.open();document.write(model.shell);document.close();
 // No forms, scripts or active links are installed into the email canvas.
 document.querySelectorAll('a').forEach(n=>{n.removeAttribute('href');n.removeAttribute('target')});
 let root=document.getElementById('sc-local-sections'),shell=model.shell;if(!root)return;
 const render=sections=>{
  const started=performance.now();model=state.model;
  if(shell!==model.shell){shell=model.shell;const parsed=new DOMParser().parseFromString(shell,'text/html');document.body.innerHTML=parsed.body.innerHTML;document.querySelectorAll('a').forEach(n=>n.removeAttribute('href'));root=document.getElementById('sc-local-sections');}
  const keep=new Set(sections.filter(s=>s.visible).map(s=>s.id));
  for(const child of [...root.children])if(!keep.has(child.dataset.sectionId))child.remove();
  const nodes=new Map([...root.children].map(n=>[n.dataset.sectionId,n]));let position=0;
  const offer=sections.find(s=>s.type==='discount'&&s.visible)?.offer||(!model.managed_offer?model.offer:null);
  for(const s of sections){if(!s.visible)continue;let node=nodes.get(s.id);if(!node){node=document.createElement('div');node.dataset.sectionId=s.id;root.append(node);}
   const signature=JSON.stringify([s,model.context_token,offer,model.errors?.[s.id]]);
   if(node._signature!==signature){let html;try{html=sectionHtml(s,model,sections);node.removeAttribute('role');}catch(error){html='<div style="padding:14px;border:1px solid #b94a32;color:#8d2918">'+esc(s.name||'Section')+': '+esc(error.message)+'</div>';node.setAttribute('role','alert');}
    if(node._html!==html){node.innerHTML=html;node._html=html;}node._signature=signature;
   }
   if(root.children[position]!==node){if(root.moveBefore)root.moveBefore(node,root.children[position]||null);else root.insertBefore(node,root.children[position]||null);}position++;
  }
  state.lastRenderMs=performance.now()-started;state.renderedRevision=state.revision;
 };
 state.listeners.add(render);addEventListener('pagehide',()=>state.listeners.delete(render),{once:true});render(state.sections);
}
global.SCPreview={channel,publish,mount,sectionHtml,sanitize,clone};
})(globalThis);
