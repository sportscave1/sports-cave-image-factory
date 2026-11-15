"""Fixed inspector program: evaluated only inside the network-isolated renderer."""
INSPECT = r'''({x,y}) => {
 const hit=document.elementFromPoint(x,y);
 if(!hit)return {supported:false,reason:'No element at this position'};
 let key=null,node=hit;
 const login=!!document.querySelector('.sc-login-title');
 const map=[['title','.sc-login-title'],['description','.sc-login-copy'],['brand','.sc-login-kicker'],['submit','div[data-testid="stFormSubmitButton"] > button'],[innerWidth<760?'mobile_panel':'panel','.sc-login-wrap']];
 if(login)for(const [id,selector] of map){const el=hit.closest(selector);if(el){key=id;node=el;break;}}
 const r=node.getBoundingClientRect(),style=getComputedStyle(node);
 return {supported:!!key,component:key,tag:node.tagName.toLowerCase(),text:node.matches('input,textarea')?'':(node.innerText||node.getAttribute('aria-label')||'').slice(0,160),
 rect:{x:Math.max(0,r.x),y:Math.max(0,r.y),width:Math.min(r.width,innerWidth),height:Math.min(r.height,innerHeight)},
 styles:{color:style.color,fontSize:style.fontSize,padding:style.padding,borderRadius:style.borderRadius},
 reason:key?'Explicit source mapping':'Read-only: no verified source mapping for this element'};
}'''

# Fixed metadata for visible, explicitly mapped components only. No caller selectors.
TARGETS = r'''() => {
 if(!document.querySelector('.sc-login-title'))return [];
 return [['title','.sc-login-title'],['description','.sc-login-copy'],['brand','.sc-login-kicker'],['submit','div[data-testid="stFormSubmitButton"] > button'],[innerWidth<760?'mobile_panel':'panel','.sc-login-wrap']].flatMap(([component,selector])=>{
 const node=document.querySelector(selector);if(!node)return [];const r=node.getBoundingClientRect();
 return r.width>0&&r.height>0&&r.x>=0&&r.y>=0&&r.x<innerWidth&&r.y<innerHeight?[{component,x:Math.floor(r.x+r.width/2),y:Math.floor(r.y+r.height/2)}]:[];
 });
}'''
