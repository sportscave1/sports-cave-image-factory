/* Compact controls for the existing section bridge; no fetches or dependencies. */
const visualAppearanceOpen={};
function visualControls(s, content, api) {
 const {el, change, debounce} = api, cfg = s.settings;
 let fields = el('div','','visual-fields'); content.append(fields);
 function input(key,label,type='text',limits={}) {
  const wrap=el('label',label), multiline=key==='text'&&cfg.kind==='text', n=document.createElement(multiline?'textarea':'input');if(!multiline)n.type=type;else{n.rows=3;wrap.className='visual-wide';}n.value=cfg[key];
  n.setAttribute('aria-label',label);Object.assign(n,limits);wrap.append(n);fields.append(wrap);
  const commit=()=>{if(n.reportValidity())change({[key]:type==='number'?Number(n.value):n.value});};
  if(type==='color')n.onchange=commit;else debounce(n,key,commit);
 }
 function select(key,label,options) {
  const wrap=el('label',label),n=document.createElement('select');n.setAttribute('aria-label',label);
  for(const [value,text] of options){const o=el('option',text);o.value=value;n.append(o);}n.value=cfg[key];
  n.onchange=()=>change(key==='kind'?{kind:n.value,action:['button','image','product_image','lifestyle'].includes(n.value)?'recovery':'none'}:{[key]:n.value});wrap.append(n);fields.append(wrap);
 }
 select('kind','Element',Object.entries({headline:'Headline',text:'Text / collector story',button:'Button',image:'Custom image',product_image:'Checkout product image',lifestyle:'Lifestyle image',edition:'Edition label',product_name:'Product name',variant:'Frame / variant',dimensions:'Dimensions',quantity:'Quantity',price:'Price',details:'Product details',divider:'Divider',spacer:'Spacing'}));
 if(['headline','text','button'].includes(cfg.kind))input('text','Text','text',{maxLength:8000});
 if(['image','button','product_image','lifestyle'].includes(cfg.kind)){
  select('action','Action',[['recovery','Recover Checkout'],['wall','See It On Your Wall'],['product','Product Page'],['custom','Custom HTTPS URL'],['none','No Link']]);
  if(cfg.action==='custom')input('url','Custom HTTPS URL','url');
 }
 if(cfg.kind==='image'){input('image_url','Image URL','url');input('alt','Image description');}
 if(cfg.kind==='lifestyle')input('position','Shopify gallery position','number',{min:2,max:4});
 if(!['headline','text','divider','spacer','image'].includes(cfg.kind)||['wall','product'].includes(cfg.action))input('product','Checkout item (0 = all)','number',{min:0,max:500});
 if(cfg.kind==='edition')select('edition_style','Edition appearance',[['plain','Plain text'],['badge','Compact badge'],['collector','Collector label']]);
 const appearance=el('details','','visual-appearance');appearance.open=!!visualAppearanceOpen[s.id];appearance.ontoggle=()=>visualAppearanceOpen[s.id]=appearance.open;appearance.append(el('summary','Appearance'));fields=el('div','','visual-fields');appearance.append(fields);content.append(appearance);
 select('align','Alignment',[['left','Left'],['center','Centre'],['right','Right']]);
 if(['image','product_image','lifestyle'].includes(cfg.kind))input('width','Image width (px)','number',{min:40,max:600});
 else {input('size','Font size (px)','number',{min:8,max:64});select('weight','Weight',[['normal','Normal'],['bold','Bold']]);}
 input('color','Text colour','color');input('background','Background','color');
 input('border','Border (px)','number',{min:0,max:8});input('border_color','Border colour','color');
 input('padding','Padding (px)','number',{min:0,max:80});input('spacing','Space below (px)','number',{min:0,max:100});
 if(cfg.kind==='edition')content.append(el('div','Read-only Edition Ops facts. Next available is not a reservation. Missing edition facts are omitted.','warning'));
 if(cfg.action==='recovery')content.append(el('div','Uses this customer’s original verified checkout. Disabled in samples and test emails.','warning'));
}
