"""Bounded DOM facts for source resolution; never reads field values."""
INSPECT = r'''({x,y}) => {
 let hit=document.elementFromPoint(x,y),offsetX=0,offsetY=0;
 if(!hit)return {supported:false,reason:'No element at this position'};
 // Inspect same-origin HTML component content; cross-origin frames remain honest fallbacks.
 if(hit.tagName==='IFRAME')try{
   const rect=hit.getBoundingClientRect(),inside=hit.contentDocument?.elementFromPoint(x-rect.x,y-rect.y);
   if(inside){hit=inside;offsetX=rect.x;offsetY=rect.y;}
 }catch{}
 let node=hit.closest('button,input,textarea,select,h1,h2,h3,h4,.sc-section-title,[role="heading"],[role="button"],[role="grid"],table,[data-testid="stDataFrame"],form')||hit;
 let component=null;
 if(document.querySelector('.sc-login-title'))for(const [name,selector] of [['title','.sc-login-title'],['brand','.sc-login-kicker'],['description','.sc-login-copy'],['submit','[data-testid="stFormSubmitButton"] button'],['panel','.sc-login-wrap']]){
   const found=hit.closest(selector);if(found){component=name;node=found;break;}
 }
 const parents=[];for(let n=node;n&&parents.length<12;n=n.parentElement)parents.push(n);
 const keys=parents.flatMap(n=>[...n.classList].filter(c=>c.startsWith('st-key-')).map(c=>c.slice(7))),keyed=keys[0]||null;
 const tag=node.tagName.toLowerCase(),kind=/^h[1-6]$/.test(tag)||node.matches('.sc-section-title,[role="heading"]')?'heading':node.matches('input,textarea,select')?'input':node.matches('button,[role="button"]')?'button':node.matches('table,[role="grid"],[data-testid="stDataFrame"]')?'table':'section';
 const r=node.getBoundingClientRect();
 return {supported:false,component,tag,kind,streamlit_key:keyed,streamlit_keys:keys,element_id:node.id.slice(0,120),
   classes:[...node.classList].filter(c=>!c.startsWith('st-emotion-cache')).slice(0,12),
   text:kind==='input'?(node.getAttribute('aria-label')||node.getAttribute('placeholder')||'').slice(0,160):(node.innerText||'').slice(0,160),
   rect:{x:Math.max(0,r.x+offsetX),y:Math.max(0,r.y+offsetY),width:Math.min(r.width,innerWidth),height:Math.min(r.height,innerHeight)}};
}'''

TARGETS = r'''() => {
 const seen=new Set(),result=[];
 for(const selector of ['.sc-login-title','.sc-login-wrap','[class*="st-key-"] input','[data-testid="stDataFrame"]','.sc-section-title','[role="heading"]','h1','h2','h3','button']){
  for(const n of document.querySelectorAll(selector)){
   if(seen.has(n))continue;seen.add(n);const r=n.getBoundingClientRect();
   if(r.width>0&&r.height>0&&r.y>=0&&r.bottom<=innerHeight&&r.x>=0&&r.right<=innerWidth)
    result.push({component:n.matches('.sc-login-title')?'title':n.matches('.sc-login-wrap')?'panel':null,
     tag:n.tagName.toLowerCase(),text:(n.matches('input')?n.getAttribute('aria-label')||n.getAttribute('placeholder'):n.innerText||'').slice(0,120),
     x:Math.floor(r.x+r.width/2),y:Math.floor(r.y+r.height/2)});
   if(result.length>=80)return result;
  }
 }return result;
}'''
