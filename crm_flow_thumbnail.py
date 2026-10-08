"""Lazy, inert email miniatures. No recipient/provider lookups or editor mounts."""
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
import json,re,hashlib
from urllib.parse import urlsplit
import streamlit as st

class InertEmail(HTMLParser):
    tags={'div','span','p','table','tbody','thead','tr','td','th','img','br','strong','b','em','i','h1','h2','h3','hr','ul','ol','li','a','center'}
    styles={'color','background','background-color','font-family','font-size','font-weight','font-style','line-height','text-align','text-decoration','width','height','max-width','min-width','padding','padding-top','padding-bottom','padding-left','padding-right','margin','margin-top','margin-bottom','border','border-top','border-bottom','border-radius','border-collapse','vertical-align','display','letter-spacing'}
    def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style','iframe','object','svg','form','head'):self.skip+=1;return
        if self.skip or tag not in self.tags:return
        clean=[]
        for k,v in attrs:
            if not v:continue
            if k=='style':
                declarations=[]
                for part in v.split(';'):
                    name,_,value=part.partition(':')
                    if name.strip().lower() in self.styles and not re.search(r'url|expression|@|[<>\\]',value,re.I):declarations.append(name+':'+value)
                clean.append(('style',';'.join(declarations)))
            elif k in ('width','height','colspan','cellpadding','cellspacing','align','valign','bgcolor','alt'):clean.append((k,v))
            elif tag=='img' and k=='src':
                # Only a CDN that supports bounded image transforms. Never load
                # tracking pixels or full-resolution arbitrary remote artwork.
                if urlsplit(v).hostname=='cdn.shopify.com':
                    from crm_catalogue import picker_thumbnail
                    clean.extend([('src',picker_thumbnail(v)),('loading','lazy'),('referrerpolicy','no-referrer')])
        self.out.append('<'+tag+''.join(' '+k+'="'+escape(v,quote=True)+'"' for k,v in clean)+'>')
    def handle_endtag(self,tag):
        if tag in ('script','style','iframe','object','svg','form','head'):
            self.skip=max(0,self.skip-1);return
        if not self.skip and tag in self.tags and tag not in ('img','br','hr'):self.out.append('</'+tag+'>')
    def handle_data(self,data):
        if not self.skip:self.out.append(escape(data))

@lru_cache(maxsize=64)
def miniature(source,settings):
    doc=json.loads(source);cfg=json.loads(settings)
    from crm_checkout_preview import needs_checkout,document,sample
    if needs_checkout(doc):doc,_=document(doc,sample(doc))
    from crm_email_size import render_production
    html=render_production(doc,cfg)['html']
    parser=InertEmail();parser.feed(html)
    return ''.join(parser.out)

@st.fragment
def thumbnail(store,step):
    from crm_preview_cache import presentation_document
    source=json.dumps(presentation_document(step['document']),sort_keys=True,default=str)
    digest=hashlib.sha256(source.encode()).hexdigest()[:20]
    key='flow-thumb-'+step['step_id']+'-'+digest
    with st.container(key=key):
        if st.button('Load email thumbnail',key=key+'load') or st.session_state.get(key):
            st.session_state[key]=True
            try:
                # Rendering settings are shared per route; no repeated default
                # reads for every visible card. Authored sections own their copy.
                cfg=st.session_state.get('_flow_thumbnail_settings')
                if cfg is None:cfg=store.render_settings();st.session_state['_flow_thumbnail_settings']=cfg
                value=miniature(source,json.dumps(cfg,sort_keys=True,default=str))
                st.html('<div id="'+key+'" class="sc-flow-thumbnail" role="button" tabindex="0" data-email="'+escape(value,quote=True)+'" data-preview="flow-preview-'+step['step_id']+'" aria-label="Preview saved email design"></div>')
            except (ValueError,RuntimeError):st.caption('Preview unavailable')
        else:st.html('<div class="sc-flow-thumb-trigger" data-key="'+key+'" style="width:76px;height:100px;background:#f3f1ec" aria-label="Email thumbnail loading"></div>')

SCRIPT='''<script>(()=>{
 if(window.scFlowThumbObserver)return;

 const seen=new WeakSet();const queue=[];let active=null;
 const pump=()=>{if(active?.isConnected)return;active=null;while(queue.length){const e=queue.shift();if(!e.isConnected)continue;active=e;document.querySelector('.st-key-'+e.dataset.key+'load button')?.click();break;}};
 const preview=e=>{const host=e.target.closest?.('.sc-flow-thumbnail');if(host&&(e.type==='click'||['Enter',' '].includes(e.key))){e.preventDefault();document.querySelector('.st-key-'+host.dataset.preview+' button')?.click();}};document.addEventListener('click',preview);document.addEventListener('keydown',preview);
 const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;observer.unobserve(entry.target);queue.push(entry.target);pump();}},{rootMargin:'100px'});
 const scan=()=>{const root=document.querySelector('.st-key-crm-automation-editor');if(!root){observer.disconnect();queue.length=0;active=null;return;}root.querySelectorAll('.sc-flow-thumbnail:not([data-mounted])').forEach(e=>{e.dataset.mounted='1';const shadow=e.attachShadow({mode:'open'});const style=document.createElement('style');style.textContent=':host{display:block;width:76px;height:100px;overflow:hidden;background:white}.email{width:600px;transform:scale(.1266);transform-origin:top left;pointer-events:none;color:#222;font:14px Arial}';const email=document.createElement('div');email.className='email';email.innerHTML=e.dataset.email;shadow.append(style,email);delete e.dataset.email;});root.querySelectorAll('.sc-flow-thumb-trigger').forEach(e=>{if(!seen.has(e)){seen.add(e);observer.observe(e);}});pump()};
 let queued=false;const mutations=new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(()=>{queued=false;scan()})}});
 mutations.observe(document.body,{childList:true,subtree:true});window.scFlowThumbObserver=observer;scan();
})()</script>'''
